"""CP23 V2 NEW-IDENTITY N23/B4 audit owner, SOURCE-ONLY policy-bridge candidate.

No native admission is granted by possessing this source. Strictly requires an
independent, exact Windows permission/preflight before invoking its activation.
The historical N23 proof is a reference, NOT this file's runtime certificate.
"""
from __future__ import annotations

import hashlib
import marshal
import ntpath
from pathlib import Path
import re
import subprocess
import sys
import threading
import types
from mmd_registry.cp23_n23_policy_v2 import N23AuditPolicy


class Denied(RuntimeError):
    pass


CANONICAL = r'D:\MMD\mmd-asset-registry'
B4_PATH = CANONICAL + r'\mmd_registry\mesh_projection_v2.py'
B4_SHA = '24eaaedeb6af5e1577849990d24514f484a5f298ccd29fc8d46c045860b37233'
N23_HISTORICAL_SHA = 'ee95e199a52e95436e4ce566adc769ef15a0503b86ac51cf0db56ba726468ed5'
NATIVE_ADMISSION = False  # Hard lock in this source-only release
GIT_EXE = r'C:\Program Files\Git\cmd\git.exe'
GIT_SHA = '54194a1af7cfb6730448ce14b8f2c1dddd9f950b7f995dc351c1ed16eb179249'
BARE = r'D:\Assets\MMDRegistry\Studio\Baselines\CP19_R0C_9747_4291_12665_8308_BARE.git'
CANONICAL_CONFIG_SHA = '0b6d4c2e1f0441d8f24f63755dc0b35aec86f19af5aa524f9de92e026ddd0b0c'
BARE_CONFIG_SHA = '74c63b4eae3533b3ff4c0e285897778464d6c04815c33457729279ded1e2a947'
EXPECTED_GIT_ENV = {
    'GIT_OPTIONAL_LOCKS': '0', 'GIT_NO_REPLACE_OBJECTS': '1',
    'GIT_NO_LAZY_FETCH': '1', 'GIT_CONFIG_NOSYSTEM': '1',
    'GIT_CONFIG_GLOBAL': 'nul', 'GIT_CONFIG_SYSTEM': 'nul',
    'GIT_ALLOW_PROTOCOL': '', 'GIT_PROTOCOL_FROM_USER': '0',
    'GIT_TERMINAL_PROMPT': '0',
}
# This is exactly the B4 _prefix() source grammar, not a generic Git allowlist.
CONFIG = ('protocol.allow=never', 'core.fsmonitor=false',
          'core.commitGraph=false', 'core.multiPackIndex=false',
          'gc.auto=0', 'maintenance.auto=false')
OID = re.compile(r'[0-9a-f]{40}\Z')
REF = re.compile(r'(?:HEAD|refs/(?:heads|tags)/[A-Za-z0-9_./-]+)\^\{commit\}\Z')


def require(condition, reason):
    if not condition:
        raise Denied('CP23_' + reason)


def norm(value):
    require(isinstance(value, (str, Path)), 'PATH_TYPE_DENIED')
    return ntpath.normcase(ntpath.normpath(str(value)))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def nested_run(code):
    for child in code.co_consts:
        if isinstance(child, types.CodeType):
            if (child.co_name == '_run' and
                    child.co_qualname.endswith('verify_core.<locals>.Repo._run')):
                return child
            found = nested_run(child)
            if found:
                return found
    return None


def exact_argv(argv, *, gitdir, core_paths):
    """Pure, fail-closed grammar for the eight B4 source callsites.

    NO filesystem access, process creation, imports from B4 or Git invocation.
    Paths must be independently pinned at Windows preflight before use.
    """
    require(type(argv) in (list, tuple) and len(argv) <= 192 and len(argv) >= 2,
            'ARGV_LENGTH')
    require(all(type(x) is str and 0 < len(x) < 1024 and '\x00' not in x
                for x in argv) and sum(map(len, argv)) < 24576, 'ARGV_BYTES')
    require(norm(argv[0]) == norm(GIT_EXE), 'GIT_IMAGE_NOT_PINNED')
    require(norm(gitdir) in (norm(CANONICAL + r'\.git'), norm(BARE)),
            'GIT_DIR_NOT_PINNED')
    prefix = [GIT_EXE, '--no-pager', '--no-optional-locks',
              '--no-replace-objects', '--no-lazy-fetch']
    for setting in (*CONFIG, 'safe.directory=' + (CANONICAL if norm(gitdir) ==
                            norm(CANONICAL + r'\.git') else BARE)):
        prefix.extend(('-c', setting))
    require(list(argv[:len(prefix)]) == prefix, 'B4_PREFIX_NOT_EXACT')
    remaining = list(argv[len(prefix):])
    if remaining == ['--version']:
        return '--version'
    require(remaining and remaining[0] == '--git-dir=' + str(gitdir),
            'GITDIR_SELECTOR_NOT_EXACT')
    tail = remaining[1:]
    require(tail, 'MISSING_SUBCOMMAND')
    cmd, args = tail[0], tail[1:]
    if cmd == 'config':
        require(len(args) >= 5 and args[:3] ==
                ['--no-includes', '--null', '--file'] and
                norm(args[3]) == norm(str(gitdir) + r'\config'),
                'CONFIG_READ_GRAMMAR')
        require(args[4:] == ['--list'] or
                (len(args[4:]) == 2 and args[4] in ('--get', '--get-regexp') and
                 re.fullmatch('[A-Za-z0-9_.^$*|-]{1,160}', args[5]) is not None),
                'CONFIG_QUERY_NOT_EXACT')
    elif cmd == 'cat-file':
        require(args == ['--batch'], 'CATFILE_NOT_BATCH')
    elif cmd == 'rev-parse':
        require(args == ['--verify', 'HEAD^{commit}'] or
                (len(args) == 3 and args[:2] == ['--verify', '--quiet'] and
                 REF.fullmatch(args[2]) is not None), 'REVPARSE_NOT_EXACT')
    elif cmd == 'merge-base':
        require(len(args) == 3 and args[0] == '--is-ancestor' and
                OID.fullmatch(args[1]) is not None and
                OID.fullmatch(args[2]) is not None,
                'MERGEBASE_NOT_EXACT')
    elif cmd == 'ls-tree':
        require(len(args) >= 6 and args[:2] == ['-r', '-z'] and
                OID.fullmatch(args[2]) is not None and args[3] == '--',
                'LSTREE_NOT_EXACT')
        requested = args[4:]
        require(len(requested) == len(core_paths) == 119 and
                len(set(requested)) == len(requested) and
                set(requested) == set(core_paths), 'LSTREE_NOT_PINNED_CORE119')
    else:
        raise Denied('CP23_GIT_COMMAND_NOT_IN_B4_SOURCE:' + cmd[:32])
    return cmd


class SingleAuditOwner:
    """One process-bound owner for original B4 Popen and Job-before-resume.

    Popen wrapper validates original B4 _run and arms exactly one call. It then
    calls original subprocess.Popen; the separate Job Gate intercepts WinAPI
    CreateProcess, requires this SAME owner and verifies membership before
    resume. This class does not claim Win32 attestation without a native test.
    """
    def __init__(self, *, core_paths, proof_token=None):
        require(type(core_paths) in (list, tuple) and len(core_paths) == 119,
                'PINNED_CORE_PATHS_REQUIRED')
        require(all(type(p) is str for p in core_paths) and
                len(set(core_paths)) == 119, 'CORE_PATHS_INVALID')
        self.core_paths = tuple(core_paths)
        self.proof_token = proof_token
        self.installed = False
        self.expected_run = None
        self.bound_code = None
        self.owner_thread = None
        self.armed = None
        self.before_resume_events = []
        self.denials = []
        self._original_popen = None
        self._wrapper = None
        self._gate = None
        self._count = 0
        # Only pure policy assessment is implemented in R3. Installation of
        # the process-global sys.addaudithook requires a later separate native
        # approval and OS/stdlib origin proof; R3 NEVER installs it.
        self.audit_policy = N23AuditPolicy(
            canonical_root=CANONICAL, git_image=GIT_EXE,
            allowed_read_paths=(B4_PATH, CANONICAL + r'\.git\config',
                                BARE + r'\config', *
                                (CANONICAL + '\\' + p.replace('/', '\\') for p in core_paths)))
        self.python_os_hook_installed = False
        self._audit_enabled = False
        self._audit_hook_ref = None

    def authorize_python_audit_event(self, event, args):
        """Pure policy check; not an installed CPython audit hook."""
        return self.audit_policy.decide(
            event, args, armed=self.armed,
            owner_thread=(self.owner_thread == threading.get_ident()))

    def install_python_os_audit_hook(self):
        """Native-only, future admission. Installs once, before protected run.

        CPython audit hooks are process-global and NOT a security boundary.
        Underlying event completeness and runtime compatibility must be proven
        by a separately authorized integration test. No silent allow fallback.
        """
        require(NATIVE_ADMISSION, 'NATIVE_ADMISSION_NOT_AUTHORIZED')
        require(self.owner_thread == threading.get_ident(), 'OWNER_THREAD_ONLY')
        require(not self.python_os_hook_installed, 'AUDIT_HOOK_ALREADY_INSTALLED')
        self._audit_enabled = True
        def audit_hook(event, arguments):
            if self._audit_enabled:
                self.authorize_python_audit_event(event, arguments)
        # Hooks cannot be uninstalled. The owner retains and disarms this
        # reference after the native scope; a failed installation is HOLD.
        sys.addaudithook(audit_hook)
        self._audit_hook_ref = audit_hook
        self.python_os_hook_installed = True
        return True

    def prepare_from_canonical(self):
        """Windows-only preflight; MUST NOT run from R2 source-only QA.

        Preparation is not an execution approval. Checks exact future install
        location and newly pinned source identity, not a sandbox alias.
        """
        require(NATIVE_ADMISSION, 'NATIVE_ADMISSION_NOT_AUTHORIZED')
        require(sys.platform == 'win32', 'WINDOWS_ONLY')
        require(self.proof_token == 'OWNER_EXPLICIT_CP23_NEW_B4_NATIVE_BATCH',
                'NATIVE_AUTHORITY_NOT_GRANTED')
        b4 = Path(B4_PATH)
        require(b4.is_file() and not b4.is_symlink() and
                digest(b4.read_bytes()) == B4_SHA, 'B4_INSTALL_SHA_NOT_PROVED')
        gp = Path(GIT_EXE)
        require(gp.is_file() and digest(gp.read_bytes()) == GIT_SHA,
                'GIT_EXECUTABLE_SHA_NOT_PROVED')
        for file, expected in ((Path(CANONICAL) / '.git' / 'config', CANONICAL_CONFIG_SHA),
                               (Path(BARE) / 'config', BARE_CONFIG_SHA)):
            require(file.is_file() and not file.is_symlink() and
                    digest(file.read_bytes()) == expected, 'PINNED_GIT_CONFIG_DRIFT')
        code = compile(b4.read_bytes(), B4_PATH, 'exec', dont_inherit=True)
        self.expected_run = nested_run(code)
        require(self.expected_run is not None and
                self.expected_run.co_filename == B4_PATH, 'B4_CODE_ORIGIN_MISSING')
        self.owner_thread = threading.get_ident()
        return True

    def authorize_install(self):
        return bool(self.expected_run is not None and
                    self.owner_thread == threading.get_ident() and
                    self.proof_token == 'OWNER_EXPLICIT_CP23_NEW_B4_NATIVE_BATCH')

    def authorize_original_caller(self, frame):
        require(self.authorize_install(), 'OWNER_INSTALL_NOT_ATTESTED')
        require(frame is not None and frame.f_code.co_filename == B4_PATH and
                marshal.dumps(frame.f_code) == marshal.dumps(self.expected_run),
                'ORIGINAL_CALLER_CODE_IDENTITY_DENIED')
        if self.bound_code is None:
            self.bound_code = frame.f_code
        require(frame.f_code is self.bound_code, 'ORIGINAL_CALLER_CODE_OBJECT_DRIFT')
        repo = frame.f_locals.get('self')
        require(repo is not None and
                type(repo).__qualname__.endswith('verify_core.<locals>.Repo') and
                norm(getattr(repo, 'cwd', '')) == norm(CANONICAL) and
                norm(getattr(repo, 'git_exe', '')) == norm(GIT_EXE),
                'ORIGINAL_REPO_BINDING_DENIED')
        require(norm(getattr(repo, 'gitdir', '')) in
                (norm(CANONICAL + r'\.git'), norm(BARE)),
                'REPO_GITDIR_NOT_PINNED')
        return True

    def authorize_popen(self, frame, args, call_kwargs):
        """Arm before original stdlib Popen; never replace original B4 _run."""
        require(not self.armed, 'CONCURRENT_PROCESS_DENIED')
        self.authorize_original_caller(frame)
        repo = frame.f_locals['self']
        cmd = exact_argv(args, gitdir=str(repo.gitdir), core_paths=self.core_paths)
        require(not call_kwargs.get('shell') and call_kwargs.get('cwd') == CANONICAL and
                call_kwargs.get('env') == repo._env, 'CHILD_CWD_ENV_NOT_EXACT')
        require(call_kwargs.get('stdout') == subprocess.PIPE and
                call_kwargs.get('stderr') == subprocess.PIPE and
                call_kwargs.get('stdin') in (subprocess.PIPE, subprocess.DEVNULL),
                'CHILD_PIPES_NOT_EXACT')
        require(set(call_kwargs) == {'cwd', 'env', 'shell', 'stdin', 'stdout', 'stderr'},
                'PROCESS_KWARGS_EXTRA_DENIED')
        for k, v in EXPECTED_GIT_ENV.items():
            require(call_kwargs['env'].get(k, '').casefold() == v.casefold(),
                    'GIT_ENV_SETTING_NOT_PINNED:' + k)
        self._count += 1
        require(self._count <= 18, 'MAX_GIT_CHILDREN_REACHED')
        self.armed = {'frame': frame, 'argv': tuple(args), 'command': cmd,
                      'cwd': CANONICAL, 'env': dict(call_kwargs['env']),
                      'resumed': False}
        return True

    def authorize_git_createprocess(self, frame, image, command, cwd, env, startup):
        state = self.armed
        require(state is not None and frame is state['frame'],
                'UNARMED_WIN32_CREATEPROCESS')
        self.authorize_original_caller(frame)
        require(image in (None, GIT_EXE) and
                command == subprocess.list2cmdline(state['argv']) and
                norm(cwd) == norm(state['cwd']) and env == state['env'],
                'WIN32_CHILD_IMAGE_COMMAND_CWD_ENV_MISMATCH')
        return True

    def before_resume(self, frame, pid, process_handle, job_handle):
        state = self.armed
        require(state is not None and frame is state['frame'] and
                not state['resumed'] and type(pid) is int and pid > 0 and
                int(process_handle) > 0 and int(job_handle) > 0,
                'UNAUTHORIZED_JOB_RESUME')
        state['resumed'] = True
        self.before_resume_events.append((pid, state['command']))
        return True

    def guarded_popen(self, *args, **kwargs):
        """Bridge invoked only after actual B4 _run calls subprocess.Popen."""
        require(self.installed and threading.get_ident() == self.owner_thread,
                'OFF_OWNER_THREAD_POPEN_DENIED')
        require(len(args) == 1, 'POPEN_POSITIONAL_ARGS_DENIED')
        frame = sys._getframe(1)
        self.authorize_popen(frame, args[0], kwargs)
        try:
            result = self._original_popen(*args, **kwargs)
            require(self.armed is not None and self.armed['resumed'],
                    'POPEN_RETURNED_WITHOUT_JOB_RESUME_ATTESTATION')
            return result
        finally:
            self.armed = None

    def __enter__(self):
        """Dangerous native activation: only after explicit path+op approval."""
        require(NATIVE_ADMISSION, 'NATIVE_ADMISSION_NOT_AUTHORIZED')
        require(self.authorize_install(), 'OWNER_ACTIVATION_NOT_AUTHORIZED')
        require(self.python_os_hook_installed and self._audit_enabled, 'N23_PYTHON_OS_AUDIT_HOOK_NOT_ATTESTED')
        require(not self.installed, 'AUDIT_OWNER_ALREADY_ACTIVE')
        from mmd_registry.cp23_winjob_v2 import JobBeforeResume
        self._original_popen = subprocess.Popen
        require(type(self._original_popen) is type, 'ORIGINAL_POPEN_PATCHED')
        self._gate = JobBeforeResume(self)
        self._gate.__enter__()  # installs native gate before Popen wrapper
        self._wrapper = self.guarded_popen
        subprocess.Popen = self._wrapper
        self.installed = True
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            require(subprocess.Popen is self._wrapper, 'POPEN_WRAPPER_TAMPERED')
        finally:
            subprocess.Popen = self._original_popen
            self.installed = False
            if self._gate is not None:
                self._gate.__exit__(exc_type, exc, tb)
            self._audit_enabled = False
        return False


# IMPORTANT: R3 adds a pure Python audit-event policy but DOES NOT install
# sys.addaudithook, admit FFI, or prove import origins, native writes, or process isolation.
# Such a scope cannot be called N23 full integration, OS attestation or G1/G3.
# The source is a mechanism candidate only until the audit hook, exact OS
# postflight, authorized paths, and Win32 negative testing are completed.


def run_integrated_v2(owner, b4_module, canonical_root):
    """SINGLE target for future Owner-authorized native path, NOT runnable here.

    The original V2 verify_core code object invokes its original nested
    Repo._run. SingleAuditOwner wraps Popen, same owner gates CreateProcess,
    JobBeforeResume holds CREATE_SUSPENDED until membership confirmed.
    No authority is inferred from importing this function.
    """
    require(NATIVE_ADMISSION, 'NATIVE_ADMISSION_NOT_AUTHORIZED')
    require(getattr(b4_module, '__file__', None) == B4_PATH,
            'V2_CANONICAL_IMPORT_ORIGIN_REQUIRED')
    require(norm(canonical_root) == norm(CANONICAL), 'V2_CANONICAL_ROOT_ONLY')
    require(owner.expected_run is not None and
            owner.python_os_hook_installed and owner._audit_enabled,
            'V2_AUDIT_NOT_ACTIVE_BEFORE_GUARDED_RUN')
    with owner:
        return b4_module.verify_core(Path(canonical_root))
