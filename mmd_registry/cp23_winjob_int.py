"""CP23 V2 integrated Job Gate: original Popen -> Win32 Job-before-resume.

Component only. Native runs require independent exact Owner authorization.
This code is only one component of a future OWNER-AUTHORIZED root-only batch.
The native runner binds a single owner and attests all callbacks.

Unlike a replacement subprocess.Popen, this hook preserves Python's original
Popen and three stream pipes. The hook intercepts the lower Win32 CreateProcess
call, forces CREATE_SUSPENDED, assigns and verifies a kill-on-close Job, and
only then resumes. Windows compatibility, native safety, owner and CP23 gates
are NOT_ATTESTED.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import threading
import time


class GateHold(RuntimeError):
    pass


def need(ok: bool, token: str) -> None:
    if not ok:
        raise GateHold(token)


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', ctypes.c_longlong),
        ('PerJobUserTimeLimit', ctypes.c_longlong),
        ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t),
        ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD),
        ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD),
        ('SchedulingClass', wintypes.DWORD),
    ]


class _IOCounters(ctypes.Structure):
    _fields_ = [
        ('ReadOperationCount', ctypes.c_ulonglong),
        ('WriteOperationCount', ctypes.c_ulonglong),
        ('OtherOperationCount', ctypes.c_ulonglong),
        ('ReadTransferCount', ctypes.c_ulonglong),
        ('WriteTransferCount', ctypes.c_ulonglong),
        ('OtherTransferCount', ctypes.c_ulonglong),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ('BasicLimitInformation', _BasicLimit),
        ('IoInfo', _IOCounters),
        ('ProcessMemoryLimit', ctypes.c_size_t),
        ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryUsed', ctypes.c_size_t),
        ('PeakJobMemoryUsed', ctypes.c_size_t),
    ]


class JobBeforeResume:
    """Use only in a dedicated CP23 audit-owner process; strict fail closed.

    Owner interface (each method MUST return exactly True or raise):
      authorize_install()
      authorize_original_caller(frame)
      authorize_git_createprocess(frame, image, command, cwd, env, startup)
      before_resume(frame, pid, process_handle, job_handle)

    A real owner MUST bind B4 source SHA, exact _run code object, verified Git
    image/argv/cwd/env, N23 origin, six historical guards, the three inherited
    pipe handles, deadline, per-child logs, and protected postflight.
    """

    MAX_CHILDREN = 18
    CREATE_SUSPENDED = 0x00000004
    BREAKAWAY_FROM_JOB = 0x01000000
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    def __init__(self, owner):
        self.owner = owner
        self._installed = False
        self._jobs = {}
        self._spawned = 0
        self._thread_id = None
        self._original = None
        self._replacement = None
        self._winapi = None
        self._func = {}
        self._jobs_lock = threading.Lock()
        self._watch_stop = threading.Event()
        self._watch_thread = None
        self._deadline_triggered = False
        self._deadline_kill_errors = []

    def _bind(self, kernel, name, argtypes, restype):
        f = getattr(kernel, name)
        f.argtypes = argtypes
        f.restype = restype
        self._func[name] = f

    def __enter__(self):
        need(os.name == 'nt' and ctypes.sizeof(ctypes.c_void_p) == 8,
             'CP23_WIN64_ONLY')
        need(ctypes.sizeof(_ExtendedLimit) == 144,
             'CP23_WIN32_ABI_NOT_VERIFIED')
        need(self.owner.authorize_install() is True,
             'CP23_AUDIT_OWNER_INSTALL_DENIED')
        import _winapi
        need(subprocess._winapi is _winapi,
             'CP23_POPEN_NATIVE_MODULE_MISMATCH')
        self._winapi = _winapi
        self._original = _winapi.CreateProcess
        # A prior hook or alternate transport must NOT be silently accepted.
        need(type(self._original).__name__ == 'builtin_function_or_method',
             'CP23_CREATEPROCESS_ALREADY_INTERCEPTED')
        # The owner must have installed an exact-phase audit hook first.
        need(getattr(self.owner, 'audit_phase', None) == 'BOOTSTRAP',
             'CP23_AUDIT_BOOTSTRAP_NOT_ACTIVE')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        H = wintypes.HANDLE
        self._bind(kernel, 'CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], H)
        self._bind(kernel, 'SetInformationJobObject',
                   [H, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL)
        self._bind(kernel, 'AssignProcessToJobObject', [H, H], wintypes.BOOL)
        self._bind(kernel, 'IsProcessInJob', [H, H, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL)
        self._bind(kernel, 'ResumeThread', [H], wintypes.DWORD)
        self._bind(kernel, 'TerminateProcess', [H, wintypes.UINT], wintypes.BOOL)
        self._bind(kernel, 'TerminateJobObject', [H, wintypes.UINT], wintypes.BOOL)
        self._bind(kernel, 'WaitForSingleObject', [H, wintypes.DWORD], wintypes.DWORD)
        self._bind(kernel, 'CloseHandle', [H], wintypes.BOOL)
        self._thread_id = threading.get_ident()

        def intercepted(image, command, process_attrs, thread_attrs,
                        inherit, flags, environment, cwd, startup):
            return self._create(image, command, process_attrs, thread_attrs,
                                inherit, flags, environment, cwd, startup)

        self._replacement = intercepted
        _winapi.CreateProcess = intercepted
        self._installed = True
        return self

    def start_deadline_watchdog(self):
        need(self._installed and self._watch_thread is None,
             'CP23_WATCHDOG_PRECONDITION')
        deadline = getattr(self.owner, 'deadline', 0)
        need(deadline > time.monotonic(), 'CP23_DEADLINE_ALREADY_EXPIRED')
        def watchdog():
            remaining = max(0.0, deadline-time.monotonic())
            if self._watch_stop.wait(remaining):
                return
            self._deadline_triggered = True
            with self._jobs_lock:
                jobs = tuple(self._jobs.values())
            for job in jobs:
                try:
                    ok = bool(self._func['TerminateJobObject'](job, 23))
                    if not ok: self._deadline_kill_errors.append('TERMINATE_FALSE')
                except BaseException as exc:
                    self._deadline_kill_errors.append(type(exc).__name__)
        self._watch_thread = threading.Thread(target=watchdog, name='CP23_N23_JOB_DEADLINE',daemon=True)
        self._watch_thread.start()

    @staticmethod
    def _from_run_frame():
        import sys
        f = sys._getframe(1)
        for _ in range(24):
            if f is None:
                return None
            if (f.f_code.co_name == '_run' and
                    f.f_code.co_qualname.endswith('verify_core.<locals>.Repo._run')):
                return f
            f = f.f_back
        return None

    def _close_raw(self, value):
        if value:
            need(bool(self._func['CloseHandle'](int(value))),
                 'CP23_CLOSE_HANDLE_FAILED')

    def _create(self, image, command, process_attrs, thread_attrs,
                inherit, flags, environment, cwd, startup):
        need(self._installed and self._winapi.CreateProcess is self._replacement,
             'CP23_CREATEPROCESS_HOOK_TAMPERED')
        need(threading.get_ident() == self._thread_id,
             'CP23_OFF_OWNER_THREAD_PROCESS_DENIED')
        frame = self._from_run_frame()
        need(frame is not None and self.owner.authorize_original_caller(frame) is True,
             'CP23_ORIGINAL_B4_CALLER_DENIED')
        need(self.owner.authorize_git_createprocess(
            frame, image, command, cwd, environment, startup) is True,
            'CP23_EXACT_GIT_CREATION_DENIED')
        need(type(flags) is int and flags == 0,
             'CP23_CREATEPROCESS_FLAGS_NOT_EXACT')
        need(self.owner.audit_phase == 'RUN', 'CP23_AUDIT_RUN_PHASE_REQUIRED')
        # Popen must supply exactly the three inherited standard handles.
        attrs = getattr(startup, 'lpAttributeList', None)
        handle_list = attrs.get('handle_list') if type(attrs) is dict else None
        expected = [getattr(startup, a, None) for a in
                    ('hStdInput', 'hStdOutput', 'hStdError')]
        def valid_handle(v):
            try:
                n = int(v)
            except (TypeError, ValueError):
                return False
            return n > 0 and n != (1 << 64) - 1
        need(inherit and isinstance(handle_list, (list, tuple)) and
             len(handle_list) == 3 and len(set(map(int, handle_list))) == 3 and
             all(valid_handle(x) for x in expected) and
             set(map(int, handle_list)) == set(map(int, expected)),
             'CP23_EXACT_THREE_PIPE_HANDLES_DENIED')
        need(self._spawned < self.MAX_CHILDREN, 'CP23_GIT_CHILD_CAP')
        self._spawned += 1

        f = self._func
        job = 0
        hp = ht = None
        try:
            job = int(f['CreateJobObjectW'](None, None) or 0)
            need(job > 0, 'CP23_CREATE_JOB_FAILED')
            limits = _ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            need(bool(f['SetInformationJobObject'](job, 9, ctypes.byref(limits),
                                                  ctypes.sizeof(limits))),
                 'CP23_JOB_KILL_ON_CLOSE_NOT_SET')
            hp, ht, pid, tid = self._original(
                image, command, process_attrs, thread_attrs, inherit,
                flags | self.CREATE_SUSPENDED, environment, cwd, startup)
            need(valid_handle(hp) and valid_handle(ht) and pid > 0,
                 'CP23_SUSPENDED_PROCESS_HANDLES_INVALID')
            need(bool(f['AssignProcessToJobObject'](job, int(hp))),
                 'CP23_JOB_ASSIGN_BEFORE_RESUME_FAILED')
            member = wintypes.BOOL(False)
            need(bool(f['IsProcessInJob'](int(hp), job, ctypes.byref(member)))
                 and bool(member.value), 'CP23_JOB_MEMBERSHIP_NOT_CONFIRMED')
            need(self.owner.before_resume(frame, pid, int(hp), job) is True,
                 'CP23_AUDIT_OWNER_REFUSED_RESUME')
            # An owner records success ONLY AFTER ResumeThread succeeds.
            need(int(f['ResumeThread'](int(ht))) == 1,
                 'CP23_RESUME_SUSPEND_COUNT_NOT_ONE')
            need(self.owner.after_resume(frame, pid, int(hp), job) is True,
                 'CP23_RESUME_CONFIRMATION_NOT_ATTESTED')
            with self._jobs_lock:
                self._jobs[pid] = job  # keep Job alive through entire owner scope
            job = 0
            return hp, ht, pid, tid  # original subprocess.Popen receives its handles
        except BaseException:
            # Never retry or silently continue on any Create/Assign/Resume failure.
            if job:
                try: f['TerminateJobObject'](job, 23)
                except BaseException: pass
            if hp is not None:
                try:
                    f['TerminateProcess'](int(hp), 23)
                    f['WaitForSingleObject'](int(hp), 10_000)
                except BaseException: pass
            for h in (ht, hp):
                if h is not None:
                    try: h.Close()
                    except BaseException: pass
            raise
        finally:
            if job:
                self._close_raw(job)

    def __exit__(self, exc_type, exc, tb):
        self._watch_stop.set()
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=3)
        try:
            need(self._installed and
                 self._winapi.CreateProcess is self._replacement,
                 'CP23_CREATEPROCESS_RESTORE_TAMPERED')
        finally:
            if self._installed and self._winapi is not None:
                self._winapi.CreateProcess = self._original
                self._installed = False
            errors = list(self._deadline_kill_errors)
            if self._watch_thread is not None and self._watch_thread.is_alive():
                errors.append(('watchdog','DID_NOT_TERMINATE'))
            if self._deadline_triggered:
                errors.append(('watchdog','GLOBAL_DEADLINE_EXPIRED'))
            with self._jobs_lock:
                jobs = tuple(self._jobs.items())
            for pid, job in jobs:
                try:
                    # Fail closed even if an untrusted child outlived its parent.
                    self._func['TerminateJobObject'](job, 23)
                    self._close_raw(job)
                except BaseException as failure:
                    errors.append((pid, type(failure).__name__))
            self._jobs.clear()
            if errors:
                raise GateHold('CP23_JOB_CLEANUP_NOT_ATTESTED:' + repr(errors))
        return False
