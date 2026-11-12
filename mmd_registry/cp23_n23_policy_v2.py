"""CP23 V2 NEW-ID source-only N23-derived Python event policy.

The policy is deliberately closed to native ctypes, unknown operations, runtime
imports, and Git children without an armed original owner. This is pure event
classification only. It does NOT install sys.addaudithook or attest a Windows OS
security boundary. Native use remains disabled independently in owner code.
"""
from __future__ import annotations

import ntpath
import os


class AuditDenied(PermissionError):
    pass


def deny(token):
    raise AuditDenied('CP23_AUDIT_' + token)


def canonical_windows_path(path):
    """Reject NT aliases, UNC, DOS device/ADS, trailing dot, traversal and relative paths."""
    if type(path) is not str or not path or '\x00' in path:
        deny('PATH_TYPE')
    if '/' in path or path.startswith('\\\\') or path.startswith('\\?') or path.startswith('\\.'):
        deny('PATH_DEVICE_OR_UNC')
    drive, tail = ntpath.splitdrive(path)
    if len(drive) != 2 or drive[1] != ':' or not drive[0].isalpha() or not tail.startswith('\\'):
        deny('PATH_NOT_ABSOLUTE_DRIVE')
    parts = tail.split('\\')[1:]
    if not parts or any(not part or part in ('.', '..') or part[-1] in ('.', ' ')
                        or ':' in part for part in parts):
        deny('PATH_COMPONENT_ALIAS')
    normalized = ntpath.normcase(ntpath.normpath(path))
    if normalized != ntpath.normcase(path):
        deny('PATH_NONCANONICAL')
    return normalized


class N23AuditPolicy:
    """Pure, intentionally restrictive policy for NEW source identity.

    Caller must provide a preverified finite set of exact read paths, original
    B4 owner armed state and original stdlib Popen audit event arguments.
    This policy does NOT authorize all imports/ctypes/Win32 operations and
    therefore cannot be presented as full N23 audit-hook implementation.
    """
    def __init__(self, *, canonical_root, git_image, allowed_read_paths):
        self.root = canonical_windows_path(canonical_root)
        self.git_image = canonical_windows_path(git_image)
        if type(allowed_read_paths) not in (tuple, list, frozenset):
            deny('READ_MANIFEST_TYPE')
        paths = [canonical_windows_path(p) for p in allowed_read_paths]
        if not paths or len(set(paths)) != len(paths):
            deny('READ_MANIFEST_DUPLICATE_OR_EMPTY')
        self.read_set = frozenset(paths)

    def decide(self, event, args, *, armed=None, owner_thread=False):
        if type(event) is not str or type(args) is not tuple:
            deny('EVENT_SHAPE')
        if event == 'open':
            if len(args) != 3:
                deny('OPEN_ARITY')
            path, mode, flags = args
            # A read-only fd open needs a separate pinned stdlib pipe origin,
            # which this source-only policy has not integrated yet.
            if type(path) is not str or type(flags) is not int:
                deny('OPEN_FD_OR_FLAGS')
            if mode is not None and (type(mode) is not str or
                                     any(ch in mode for ch in 'wax+')):
                deny('OPEN_MODE_WRITE')
            mask = 0
            for name in ('O_WRONLY', 'O_RDWR', 'O_APPEND', 'O_CREAT', 'O_TRUNC', 'O_EXCL'):
                mask |= getattr(os, name, 0)
            if flags & mask:
                deny('OPEN_FLAGS_WRITE')
            if canonical_windows_path(path) not in self.read_set:
                deny('OPEN_NOT_IN_EXACT_READ_SET')
            return 'EXACT_READ_ONLY'
        if event == 'subprocess.Popen':
            if len(args) != 4 or type(armed) is not dict or not owner_thread:
                deny('PROCESS_UNARMED_OR_SHAPE')
            executable, argv, cwd, env = args
            if executable is not None and (type(executable) is not str or
                                           canonical_windows_path(executable) != self.git_image):
                deny('PROCESS_IMAGE')
            if type(argv) is not list or tuple(argv) != armed.get('argv') or not argv or \
                    canonical_windows_path(argv[0]) != self.git_image:
                deny('PROCESS_ARGV')
            if type(cwd) is not str or canonical_windows_path(cwd) != self.root:
                deny('PROCESS_CWD')
            if type(env) is not dict or env != armed.get('env'):
                deny('PROCESS_ENV')
            if armed.get('resumed') is not False:
                deny('PROCESS_ALREADY_RESUMED')
            return 'ARMED_ORIGINAL_POPEN_EVENT_ONLY'
        # N23 OS/Python hook has deliberately NOT admitted native functions,
        # device paths, imports, external worktrees, network or mutation.
        deny('EVENT_NOT_AUTHORIZED_' + event[:64])
