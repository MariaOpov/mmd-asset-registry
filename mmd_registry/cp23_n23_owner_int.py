"""CP23 B4 V2 integration owner, wired to ORIGINAL V2 Repo._run and Job Gate.

Not standalone. Native activation must be held by the runner until a separately
approved exact Windows scope is provided. Python audit hooks are not a sandbox.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
import time
from pathlib import Path

from mmd_registry.cp23_n23_owner_v2 import (
    CANONICAL, B4_PATH, B4_SHA, GIT_EXE, GIT_SHA, BARE,
    CANONICAL_CONFIG_SHA, BARE_CONFIG_SHA, EXPECTED_GIT_ENV,
    require, nested_run, exact_argv, norm,
)
from mmd_registry.cp23_n23_policy_int import Policy

OWNER_V2_SHA = '360dac5aaf5cf8312e0cb1f51f84653e1e825c5fc505806c764212b43f004559'
POLICY_V2_SHA = '7acf87e81caa97d70b195cade5e005b8cfb3553e6193aba6368263660e438e74'
JOB_V2_SHA = '1c1598936637e55eaee4341379520d996e82e634d0eb6fc43df94ab5ef5ce922'

class Owner:
    """One owner, one thread, <=18 B4 original calls, fail closed."""
    def __init__(self, *, core_paths, read_files, scan_dirs, native_capability):
        require(type(core_paths) in (tuple, list) and len(core_paths) == 119 and
                len(set(core_paths)) == 119, 'CORE119_MANIFEST_REQUIRED')
        require(native_capability is not None and
                getattr(native_capability, 'scope_verified', False) is True,
                'NATIVE_SCOPE_UNAUTHORIZED')
        self.core_paths = tuple(core_paths)
        self.thread = threading.get_ident()
        self.native_capability = native_capability
        self.policy = Policy(root=CANONICAL, git_exe=GIT_EXE,
                             read_files=tuple(read_files), scan_dirs=tuple(scan_dirs),
                             owner_thread=self.thread)
        self.expected_run = None
        self.runtime_code = None
        self.armed = None
        self._orig_popen = None
        self._wrapper = None
        self._gate = None
        self.installed = False
        self.audit_installed = False
        self.spawned = 0
        self.resumed = 0
        self.failures = []
        self.child_events = []
        self.deadline = 0.0
        self._callback = None

    @property
    def audit_phase(self):
        return self.policy.phase

    def pin_original(self, b4_module):
        require(threading.get_ident() == self.thread, 'PIN_WRONG_THREAD')
        b4 = Path(B4_PATH)
        require(b4.is_file() and not b4.is_symlink() and
                hashlib.sha256(b4.read_bytes()).hexdigest() == B4_SHA,
                'B4_NEW_IDENTITY_DRIFT')
        require(getattr(b4_module, '__file__', None) == B4_PATH and
                getattr(b4_module.__spec__, 'origin', None) == B4_PATH,
                'B4_IMPORT_ORIGIN_NOT_CANONICAL')
        code = compile(b4.read_bytes(), B4_PATH, 'exec', dont_inherit=True)
        self.expected_run = nested_run(code)
        require(self.expected_run is not None and
                self.expected_run.co_filename == B4_PATH,
                'ORIGINAL_V2_RUN_CODE_NOT_FOUND')
        require(getattr(b4_module, 'verify_core', None) is not None,
                'V2_VERIFY_CORE_MISSING')
        return True

    def pin_native_inputs(self):
        require(self.expected_run is not None, 'B4_NOT_BOUND')
        for path, expected in (
            (GIT_EXE,GIT_SHA),
            (CANONICAL + r'\.git\config',CANONICAL_CONFIG_SHA),
            (BARE + r'\config',BARE_CONFIG_SHA)):
            target = Path(path)
            require(target.is_file() and not target.is_symlink() and
                    hashlib.sha256(target.read_bytes()).hexdigest() == expected,
                    'NATIVE_PIN_DRIFT:' + target.name)
        return True

    def _audit_hook(self, event, args):
        if getattr(self, '_audit_probing', False):
            require(event == 'sys._getframe', 'AUDIT_UNEXPECTED_REENTRANT_EVENT')
            return
        if event in ('ctypes.dlopen', 'ctypes.dlsym', 'ctypes.dlsym/handle'):
            require(self.audit_phase == 'BOOTSTRAP', 'FFI_OUTSIDE_PINNED_BOOTSTRAP')
            self._audit_probing = True
            try:
                frame = sys._getframe(1)
                found = False
                for _ in range(16):
                    if frame is None: break
                    code = frame.f_code
                    if (code.co_filename == CANONICAL+r'\mmd_registry\cp23_winjob_int.py'
                        and code.co_name in ('__enter__', '_bind')):
                        found = True; break
                    frame = frame.f_back
                require(found, 'FFI_CALLSITE_NOT_PINNED_WINJOB')
            finally:
                self._audit_probing = False
        self.policy.decide(event, args)

    def install_hook(self):
        require(not self.audit_installed and self.expected_run is not None,
                'AUDIT_INSTALL_PRECONDITION')
        # Hook registered once before ctypes bootstrap AND guarded Git operations.
        # It cannot be uninstalled; STOPPED phase disables enforcement only after
        # the native transaction has fully completed or failed closed.
        self.policy.phase = 'BOOTSTRAP'
        self._callback = self._audit_hook
        try:
            sys.addaudithook(self._callback)
            self.audit_installed = True
        except BaseException:
            self.policy.phase = 'STOPPED'
            raise
        return True

    def authorize_install(self):
        return (self.native_capability.scope_verified is True and
                threading.get_ident() == self.thread and
                self.expected_run is not None and self.audit_installed)

    def authorize_original_caller(self, frame):
        require(self.authorize_install(), 'OWNER_NOT_ACTIVE')
        require(frame is not None and
                frame.f_code.co_filename == B4_PATH and
                frame.f_code == self.expected_run,
                'ORIGINAL_V2_CODE_OBJECT_NOT_IDENTICAL')
        if self.runtime_code is None:
            self.runtime_code = frame.f_code
        require(frame.f_code is self.runtime_code, 'ORIGINAL_V2_CODE_OBJECT_CHANGED')
        repo = frame.f_locals.get('self')
        require(repo is not None and
                type(repo).__qualname__.endswith('verify_core.<locals>.Repo') and
                norm(getattr(repo, 'cwd', '')) == norm(CANONICAL) and
                norm(getattr(repo, 'git_exe', '')) == norm(GIT_EXE) and
                norm(getattr(repo, 'gitdir', '')) in
                (norm(CANONICAL+r'\.git'),norm(BARE)),
                'REPO_ORIGIN_OR_CWD_DENIED')
        return True

    def _check_popen(self, frame, args, kwargs):
        self.authorize_original_caller(frame)
        require(self.armed is None, 'CONCURRENT_CHILD_DENIED')
        require(type(args) in (tuple, list), 'ARGV_SHAPE')
        repo = frame.f_locals['self']
        action = exact_argv(args, gitdir=str(repo.gitdir), core_paths=self.core_paths)
        require(set(kwargs) == {'cwd','env','shell','stdin','stdout','stderr'} and
                kwargs['shell'] is False and norm(kwargs['cwd']) == norm(CANONICAL) and
                kwargs['env'] == repo._env and
                kwargs['stdout'] == subprocess.PIPE and
                kwargs['stderr'] == subprocess.PIPE and
                kwargs['stdin'] in (subprocess.PIPE, subprocess.DEVNULL),
                'POPEN_CONTEXT_NOT_EXACT')
        for key, expected in EXPECTED_GIT_ENV.items():
            require(kwargs['env'].get(key,'').casefold() == expected.casefold(),
                    'GIT_ENV_DRIFT_'+key)
        require(self.spawned < 18 and time.monotonic() < self.deadline,
                'CHILD_CAP_OR_GLOBAL_DEADLINE')
        self.spawned += 1
        self.armed = {'frame':frame, 'argv':tuple(args), 'git_exe':GIT_EXE,
                      'command':action,'cwd':str(kwargs['cwd']),
                      'env':dict(kwargs['env']),'resumed':False,'preauthorized':False}
        self.policy.popen_state = self.armed
        return True

    def authorize_git_createprocess(self, frame, image, command, cwd, env, startup):
        state = self.armed
        require(state is not None and frame is state['frame'], 'WINAPI_UNARMED')
        self.authorize_original_caller(frame)
        require(image in (None,GIT_EXE) and
                command == subprocess.list2cmdline(state['argv']) and
                norm(cwd) == norm(state['cwd']) and env == state['env'] and
                time.monotonic() < self.deadline, 'WINAPI_IMAGE_OR_ARGV_DRIFT')
        return True

    def before_resume(self, frame, pid, process_handle, job_handle):
        state = self.armed
        require(state is not None and frame is state['frame'] and
                not state['resumed'] and not state['preauthorized'] and
                type(pid) is int and pid > 0 and process_handle > 0 and
                job_handle > 0 and time.monotonic() < self.deadline,
                'JOB_BEFORE_RESUME_DENIED')
        state['preauthorized'] = True
        state['pid'] = pid
        return True

    def after_resume(self, frame, pid, process_handle, job_handle):
        state = self.armed
        require(state is not None and frame is state['frame'] and
                state['preauthorized'] and not state['resumed'] and
                pid == state['pid'] and time.monotonic() < self.deadline,
                'JOB_AFTER_RESUME_DENIED')
        state['resumed'] = True
        self.resumed += 1
        self.child_events.append({'pid':pid, 'action':state['command'],
                                  'job_bound_before_resume':True,
                                  'resume_confirmed':True})
        return True

    def guarded_popen(self, *args, **kwargs):
        require(self.installed and threading.get_ident() == self.thread,
                'POPEN_OFF_OWNER')
        require(len(args) == 1, 'POPEN_NOT_ORIGINAL_SIGNATURE')
        frame = sys._getframe(1)
        self._check_popen(frame, args[0], kwargs)
        try:
            p = self._orig_popen(*args, **kwargs)
            require(self.armed is not None and self.armed['resumed'],
                    'POPEN_RETURNED_WITHOUT_CONFIRMED_JOB')
            return p
        except BaseException as exc:
            self.failures.append(type(exc).__name__)
            raise
        finally:
            self.policy.popen_state = None
            self.armed = None

    def __enter__(self):
        require(self.authorize_install() and not self.installed,
                'SINGLE_OWNER_ENTRY_DENIED')
        # Native FFI bootstrap happens under the already-installed audit hook.
        mod = sys.modules.get('mmd_registry.cp23_winjob_int')
        require(mod is not None and hasattr(mod, 'JobBeforeResume'),
                'JOB_MODULE_NOT_PRELOADED_BEFORE_AUDIT')
        JobBeforeResume = mod.JobBeforeResume
        try:
            self._gate = JobBeforeResume(self)
            self._gate.__enter__()
            require(self.audit_phase == 'BOOTSTRAP','BOOTSTRAP_PHASE_DRIFT')
            self._orig_popen = subprocess.Popen
            require(isinstance(self._orig_popen, type) and
                    self._orig_popen.__module__ == 'subprocess',
                    'PREPATCHED_SUBPROCESS_POPEN_DENIED')
            self.policy.phase = 'RUN'
            self._wrapper = self.guarded_popen
            subprocess.Popen = self._wrapper
            self.installed = True
            self._gate.start_deadline_watchdog()
            return self
        except BaseException:
            if self._orig_popen is not None:
                subprocess.Popen = self._orig_popen
            if self._gate is not None and getattr(self._gate,'_installed',False):
                self._gate.__exit__(*sys.exc_info())
            self.policy.phase = 'STOPPED'
            raise

    def __exit__(self, exc_type, exc, tb):
        problems = []
        try:
            if subprocess.Popen is not self._wrapper:
                problems.append('POPEN_PATCH_TAMPERED')
            if self._orig_popen is not None:
                subprocess.Popen = self._orig_popen
            if self._gate is not None:
                try: self._gate.__exit__(exc_type,exc,tb)
                except BaseException as e: problems.append('JOB_CLEANUP_'+type(e).__name__)
            self.installed = False
            if self.armed is not None:
                problems.append('UNFINISHED_CHILD_STATE')
            if self.resumed != self.spawned:
                problems.append('UNMATCHED_JOB_RESUME')
        finally:
            self.policy.phase = 'POSTFLIGHT'
        if problems:
            raise RuntimeError('CP23_INTEGRATED_OWNER_POSTRUN_HOLD:' + ','.join(problems))
        return False

    def finish(self):
        require(self.policy.phase == 'POSTFLIGHT', 'POSTFLIGHT_MISSING')
        self.policy.phase = 'STOPPED'
