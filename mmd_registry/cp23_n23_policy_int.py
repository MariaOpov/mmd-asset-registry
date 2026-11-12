"""CP23 B4 V2: narrow process-global CPython audit-event policy.

Installed hooks are process-global, cannot be removed, and are NOT an OS sandbox.
Only explicit phases are admitted; unknown operations fail closed during scope.
"""
from __future__ import annotations

import ntpath
import os
import threading
import sys

class AuditHold(PermissionError):
    pass

def deny(reason):
    raise AuditHold('CP23_AUDIT_' + reason)

def winpath(p):
    if type(p) is not str or '\x00' in p or len(p) < 4 or '/' in p:
        deny('PATH_SHAPE')
    if p.startswith('\\\\') or p.startswith('\\?') or p.startswith('\\.'):
        deny('DEVICE_UNC')
    drive, tail = ntpath.splitdrive(p)
    if len(drive) != 2 or drive[1] != ':' or not drive[0].isalpha() or not tail.startswith('\\'):
        deny('PATH_NOT_DRIVE_ABSOLUTE')
    parts = tail.split('\\')[1:]
    if not parts or any(not x or x in ('.', '..') or ':' in x or x[-1] in ('.', ' ') for x in parts):
        deny('PATH_ALIAS')
    n = ntpath.normcase(ntpath.normpath(p))
    if n != ntpath.normcase(p):
        deny('PATH_NONCANONICAL')
    return n

KERNEL_SYMBOLS = frozenset({
    'CreateJobObjectW','SetInformationJobObject','AssignProcessToJobObject',
    'IsProcessInJob','ResumeThread','TerminateProcess','TerminateJobObject',
    'WaitForSingleObject','CloseHandle'
})

class Policy:
    """One owner, exact read manifest, and deliberately scoped ctypes bootstrap."""
    def __init__(self, *, root, git_exe, read_files, scan_dirs, owner_thread):
        self.root = winpath(root)
        self.git_exe = winpath(git_exe)
        self.read_files = frozenset(winpath(x) for x in read_files)
        self.scan_dirs = frozenset(winpath(x) for x in scan_dirs)
        if len(self.read_files) != len(tuple(read_files)) or not self.read_files:
            deny('MANIFEST_DUPLICATE_OR_EMPTY')
        self.owner_thread = owner_thread
        self.phase = 'UNARMED'
        self.popen_state = None
        self.events = []
        self.max_events = 200000

    def _event(self, kind):
        if len(self.events) >= self.max_events:
            deny('EVENT_CAP')
        self.events.append(kind)

    def decide(self, event, args):
        if self.phase in ('UNARMED', 'STOPPED'):
            return
        if type(event) is not str or type(args) is not tuple:
            deny('BAD_EVENT_SHAPE')
        if threading.get_ident() != self.owner_thread:
            # The B4 source uses reader threads to read existing pipe streams;
            # those reads do not emit Python open events. No OS-level claim.
            deny('OFF_OWNER_THREAD_' + event[:40])
        if self.phase == 'BOOTSTRAP':
            if event == 'import' and args and args[0] == '_winapi' and '_winapi' in sys.modules:
                self._event('PINNED_PRELOADED_WINAPI_IMPORT'); return
            if event == 'ctypes.dlopen' and len(args) == 1 and args[0] in ('kernel32', 'kernel32.dll'):
                self._event('WIN32_DLL_LOAD'); return
            if event in ('ctypes.dlsym','ctypes.dlsym/handle') and len(args) == 2 and args[1] in KERNEL_SYMBOLS:
                self._event('WIN32_PINNED_SYMBOL'); return
            deny('BOOTSTRAP_EVENT_' + event[:48])
        if event == 'open':
            if len(args) != 3:
                deny('OPEN_ARITY')
            name, mode, flags = args
            if type(name) is not str or type(flags) is not int:
                deny('OPEN_FD_OR_FLAGS')
            if self.phase == 'RUN' and self.popen_state is not None and name.lower() == 'nul':
                # Windows Popen(stdin=DEVNULL) opens the NUL device O_RDWR.
                self._event('POPEN_DEVNULL_STD_HANDLE'); return
            if mode is not None and (type(mode) is not str or any(c in mode for c in 'wax+')):
                deny('OPEN_WRITE_MODE')
            disallowed = 0
            for flag in ('O_WRONLY','O_RDWR','O_APPEND','O_CREAT','O_TRUNC','O_EXCL'):
                disallowed |= getattr(os, flag, 0)
            if flags & disallowed:
                deny('OPEN_MUTATING_FLAGS')
            if winpath(name) not in self.read_files:
                deny('READ_PATH_NOT_PINNED')
            self._event('PINNED_FILE_READ'); return
        if event == 'sys._getframe' and self.phase == 'RUN':
            frame = args[0] if len(args) == 1 else None
            code = getattr(frame, 'f_code', None)
            if code and ((code.co_filename.endswith('\\cp23_n23_owner_int.py') and
                          code.co_name == 'guarded_popen') or
                         (code.co_filename.endswith('\\cp23_winjob_int.py') and
                          code.co_name == '_from_run_frame')):
                self._event('PINNED_OWNER_STACK_PROBE'); return
            deny('STACK_PROBE_ORIGIN')
        if event == 'import' and self.phase == 'RUN':
            name = args[0] if args else None
            if (type(name) is str and name in (
                 'hashlib','os','pathlib','re','stat','subprocess','threading',
                 'types','sys','dataclasses','ast','inspect','typing','collections') and
                 name in sys.modules):
                self._event('EXISTING_STDLIB_IMPORT'); return
            deny('UNKNOWN_IMPORT')
        if event == 'os.scandir' and self.phase in ('RUN','POSTFLIGHT'):
            if len(args) == 1 and type(args[0]) is str and winpath(args[0]) in self.scan_dirs:
                self._event('POSTFLIGHT_SCAN'); return
            deny('UNPINNED_SCANDIR')
        if event == 'subprocess.Popen' and self.phase == 'RUN':
            state = self.popen_state
            if len(args) != 4 or type(state) is not dict:
                deny('UNARMED_POPEN')
            image, argv, cwd, env = args
            if (image not in (None, state['git_exe']) or type(argv) is not list or
                tuple(argv) != state['argv'] or cwd != state['cwd'] or
                type(env) is not dict or env != state['env'] or state['resumed']):
                deny('POPEN_ARGUMENT_MISMATCH')
            self._event('ORIGINAL_POPEN_AUDITED'); return
        deny('UNKNOWN_' + event[:48])
