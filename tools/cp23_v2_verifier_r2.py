"""CP23 B4 V2 revised verifier R2. NEW identity; never claims B4 verify_core PASS.

The existing B4 source is immutable. This module verifies its exact source and
recreates its nested Repo class ONLY from the pinned original class code object
and explicitly verified closure inputs, without altering B4 or sys.modules.
The caller method is the original bytecode (not a reimplementation or invoke()).

No Git, Win32 Job, native execution, output creation or source repair is done by
any source-only function here. Native operation needs a separate Owner decision.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import inspect
import marshal
import os
import re
import subprocess
import sys
import threading
import types
from pathlib import Path

ROOT = Path(r'D:\MMD\mmd-asset-registry')
B4_REL = 'mmd_registry/mesh_projection_v2.py'
B4_SHA = '24eaaedeb6af5e1577849990d24514f484a5f298ccd29fc8d46c045860b37233'
CONTRACT_SHA = '82a656a18f4b2ff1d6f15872ea85e6679e8cabe2eabf00add3a537b4c5ae7c57'
MANIFEST_SHA = '699e5fc8644fdca188cc82755bbbfd485ae788ce6e1a76fce04b4f096fda799d'
RUNNER_PREVIOUS_SHA = '70cab02bdebd844e816c6fc1d53804019db70325fd82e8b2dc003054887084b6'
EXPECTED_REPO_FREEVARS = ('Hold', 'Path', '_KNOWN', '_OID', 'hashlib', 'os', 'subprocess', 'threading')
EXPECTED_RUN_FREEVARS = ('Hold', 'subprocess', 'threading')
SOURCE_IDENTITY = 'CP23_B4_V2_REVISED_VERIFIER_R2'
NATIVE_ADMISSION = False

class R2Hold(RuntimeError):
    pass

def require(ok, token):
    if not ok:
        raise R2Hold('CP23_R2_' + token)

def sha(b):
    return hashlib.sha256(b).hexdigest()

def _one_code(parent, name, qual=None):
    found = [c for c in parent.co_consts if isinstance(c, types.CodeType) and c.co_name == name]
    require(len(found) == 1, 'CODE_LOOKUP_NOT_UNIQUE:' + name)
    if qual is not None:
        require(found[0].co_qualname == qual, 'CODE_QUALNAME_DRIFT:' + name)
    return found[0]

def _one_literal(tree, name):
    statements = [s for s in tree.body if isinstance(s, ast.Assign) and
                  any(isinstance(t,ast.Name) and t.id == name for t in s.targets)]
    require(len(statements)==1, 'SOURCE_LITERAL_NOT_UNIQUE:' + name)
    return ast.literal_eval(statements[0].value)

def verify_b4_code_bytes(data: bytes, expected_filename: str):
    """Source-level proof of EXACT original method code; no process creation."""
    require(sha(data)==B4_SHA, 'B4_PIN_DRIFT')
    source_tree = ast.parse(data, filename=expected_filename)
    function_nodes = [x for x in source_tree.body if isinstance(x,ast.FunctionDef) and x.name=='verify_core']
    require(len(function_nodes)==1, 'ORIGINAL_VERIFY_NOT_UNIQUE')
    verify_ast = function_nodes[0]
    top = compile(data, expected_filename, 'exec', dont_inherit=True)
    vf = _one_code(top, 'verify_core')
    repo = _one_code(vf, 'Repo', 'verify_core.<locals>.Repo')
    original_run = _one_code(repo, '_run', 'verify_core.<locals>.Repo._run')
    original_hold = _one_code(vf, 'Hold', 'verify_core.<locals>.Hold')
    require(repo.co_freevars == EXPECTED_REPO_FREEVARS and
            original_run.co_freevars == EXPECTED_RUN_FREEVARS and
            original_run.co_filename==expected_filename,
            'ORIGINAL_REPO_CLOSURE_OR_ORIGIN_DRIFT')
    klass_nodes = [x for x in verify_ast.body if isinstance(x,ast.ClassDef) and x.name=='Repo']
    require(len(klass_nodes)==1, 'REPO_AST_NOT_UNIQUE')
    run_nodes = [x for x in klass_nodes[0].body if isinstance(x,ast.FunctionDef) and x.name=='_run']
    require(len(run_nodes)==1, 'ORIGINAL_RUN_AST_NOT_UNIQUE')
    run_ast = run_nodes[0]
    calls = [c for c in ast.walk(run_ast) if isinstance(c,ast.Call) and
             isinstance(c.func,ast.Attribute) and c.func.attr=='Popen' and
             isinstance(c.func.value,ast.Name) and c.func.value.id=='subprocess']
    require(len(calls)==1, 'ORIGINAL_POPEN_CALLSITE_DRIFT')
    kw={k.arg for k in calls[0].keywords}
    require(kw == {'cwd','env','shell','stdin','stdout','stderr'},
            'ORIGINAL_POPEN_KEYWORDS_DRIFT')
    known = _one_literal(verify_ast, '_KNOWN')
    require(type(known) is dict and len(known)==5, 'ORIGINAL_KNOWN_ANCHORS_DRIFT')
    oid_ast = [s for s in verify_ast.body if isinstance(s,ast.Assign) and
               any(isinstance(t,ast.Name) and t.id=='_OID' for t in s.targets)]
    oid_value=oid_ast[0].value if len(oid_ast)==1 else None
    require(isinstance(oid_value, ast.Call) and
            isinstance(oid_value.func, ast.Attribute) and
            isinstance(oid_value.func.value, ast.Name) and
            oid_value.func.value.id=='re' and oid_value.func.attr=='compile' and
            len(oid_value.args)==1 and isinstance(oid_value.args[0], ast.Constant) and
            oid_value.args[0].value==r'[0-9a-f]{40}\Z' and
            not oid_value.keywords,
            'ORIGINAL_OID_CONTRACT_DRIFT')
    return {'module_code':top,'verify_code':vf,'repo_code':repo,'run_code':original_run,
            'hold_code':original_hold,'known':known,'run_qualname':original_run.co_qualname,
            'popen_keywords':sorted(kw),'b4_sha256':B4_SHA}

def _cell(value):
    def capture():
        return value
    return capture.__closure__[0]

def bind_exact_original_repo(b4_module, b4_bytes, b4_filename):
    """Bind original nested Repo class code with pinned closure values.

    This is a NEW R2 context, NOT invocation of original B4 verify_core(). The
    method's actual __code__ IS the original nested code object; never clone or
    rewrite it. A runtime native proof still needs separate authorized tests.
    """
    proof=verify_b4_code_bytes(b4_bytes,b4_filename)
    require(getattr(b4_module,'__file__',None)==b4_filename and
            getattr(getattr(b4_module,'__spec__',None),'origin',None)==b4_filename,
            'B4_CANONICAL_RUNTIME_ORIGIN_DRIFT')
    require(getattr(b4_module,'verify_core',None) is not None and
            b4_module.verify_core.__code__ == proof['verify_code'],
            'B4_LIVE_VERIFY_FUNCTION_CODE_DRIFT')
    g=vars(b4_module)
    require(g.get('subprocess') is subprocess and
            g.get('__name__')=='mmd_registry.mesh_projection_v2',
            'B4_GLOBAL_BINDINGS_DRIFT')
    # Execute ONLY the original verified class-body code; do not invoke its
    # native methods, import from a secondary root, or mutate sys.modules.
    original_hold = builtins.__build_class__(
        types.FunctionType(proof['hold_code'],g), 'Hold', RuntimeError)
    mapping={'Hold':original_hold,'Path':Path,'_KNOWN':proof['known'],
             '_OID':re.compile(r'[0-9a-f]{40}\Z'),'hashlib':hashlib,'os':os,
             'subprocess':subprocess,'threading':threading}
    fn=types.FunctionType(proof['repo_code'],g,
                           closure=tuple(_cell(mapping[x]) for x in proof['repo_code'].co_freevars))
    repo_class=builtins.__build_class__(fn,'Repo')
    require(repo_class.__module__==b4_module.__name__ and
            repo_class.__qualname__=='verify_core.<locals>.Repo' and
            repo_class._run.__code__ is proof['run_code'] and
            repo_class._run.__code__.co_filename==b4_filename,
            'REBOUND_ORIGINAL_REPO_CODE_DRIFT')
    require(tuple(inspect.signature(repo_class._run).parameters)==
            ('self','args','data','cap','repo','allowed'), 'ORIGINAL_POPEN_API_SIGNATURE')
    return repo_class, proof

def verify_r2_canonical(root: Path=ROOT, *, check_loaded=True):
    """Contract + canonical import origin + actual B4 source code identity.

    Must run BEFORE installing an audit hook or attempting native admission.
    Uses existing Contract R1, preserving its eight-extension membership.
    """
    require(sys.platform=='win32' and os.name=='nt' and root==ROOT,
            'CANONICAL_WINDOWS_ROOT_REQUIRED')
    require(sys.dont_write_bytecode,'BYTECODE_WRITES_MUST_BE_DISABLED')
    from mmd_registry import cp23_b4_v2_contract_r1 as contract
    from mmd_registry import mesh_projection_v2 as b4
    contract_file = root/'mmd_registry'/'cp23_b4_v2_contract_r1.py'
    manifest_file = root/'mmd_registry'/'cp23_b4_v2_extensions_r1.json'
    require(sha(contract_file.read_bytes())==CONTRACT_SHA and
            sha(manifest_file.read_bytes())==MANIFEST_SHA, 'CONTRACT_OR_MANIFEST_DRIFT')
    result=contract.verify_contract(root,manifest_sha=MANIFEST_SHA,
                                    loaded_modules=sys.modules if check_loaded else None)
    require(result['extensions_verified']==8 and
            result['canonical_core']['canonical_count']==119,
            'CORE_OR_EXTENSIONS_NOT_ATTESTED')
    b4_file=root/B4_REL
    b4_bytes=b4_file.read_bytes()
    Repo, proof = bind_exact_original_repo(b4, b4_bytes, str(b4_file))
    require(not NATIVE_ADMISSION,'NATIVE_DEFAULT_LOCK_TAMPERED')
    return {'verifier':'REVISED_R2_NEW_SOURCE_IDENTITY',
            'original_verify_core':'UNMODIFIED_HOLD_NOT_CALLED',
            'core':result['canonical_core'],
            'extensions':result['extensions_verified'],
            'original_repo_run_code':'EXACT_CODE_OBJECT_REBOUND_SOURCE_AND_LIVE_VERIFY_CHECKED',
            'runtime_native_attested':False,'repo_class':Repo,
            'run_code':proof['run_code']}
