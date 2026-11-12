"""CP23 B4 V2 revised-verifier R2 canonical integration runner (new source identity).

Default = HOLD. Native requires a separate exact Owner authorization file and
operation-specific preflight. Never invoke this file as part of source install.
It intentionally does not mutate Git or historical B4 sources.
"""
from __future__ import annotations

import ast
import ntpath
import subprocess
import zlib
import re
import hashlib
import importlib
import json
import os
import stat
import sys
import time
from types import MappingProxyType
from pathlib import Path

ROOT = Path(r'D:\MMD\mmd-asset-registry')
CORE = ROOT / 'mmd_registry'
REPORTS = ROOT / 'reports'
SOURCE_PINS = {
    'mesh_projection_v2.py':'24eaaedeb6af5e1577849990d24514f484a5f298ccd29fc8d46c045860b37233',
    'cp23_n23_owner_v2.py':'360dac5aaf5cf8312e0cb1f51f84653e1e825c5fc505806c764212b43f004559',
    'cp23_n23_policy_v2.py':'7acf87e81caa97d70b195cade5e005b8cfb3553e6193aba6368263660e438e74',
    'cp23_winjob_v2.py':'1c1598936637e55eaee4341379520d996e82e634d0eb6fc43df94ab5ef5ce922',
}
NEW_SOURCE_PINS = {
    'cp23_n23_owner_int.py': 'f5f3cb9717c7f1c876f96145ba9791ea8e15fd69a71f318cd52df1483ca345fb',
    'cp23_n23_policy_int.py': 'df393c432cbf19226fd2d0c3ed961f5b3189e6c2be8f0cadd48bcc611008d083',
    'cp23_winjob_int.py': 'f5cb3837223894028d63506eef6a69fe33b43444c4aecc36978778f4548031f0',
}
# Persistent default deny. Only independently signed, exact one-attempt C permit
# may authorize the R2-native entrypoint; source installation never executes it.
NATIVE_ADMISSION = False
CONTRACT_R1_SOURCE_SHA = '82a656a18f4b2ff1d6f15872ea85e6679e8cabe2eabf00add3a537b4c5ae7c57'
EXT_MANIFEST_R1_SHA = '699e5fc8644fdca188cc82755bbbfd485ae788ce6e1a76fce04b4f096fda799d'
REVISED_R2_VERIFIER_SHA = '94f17d5f8e0d5f5f967dea096372da16de38344c8a42a9d7a010500db9198790'
REVISED_R2_VERIFIER_REL = 'tools/cp23_v2_verifier_r2.py'
RAW_INIT = '5e73f4f4e117fd56b1a06e3f0c429ed8ac3a7bbd729c838f326b2c6da93adf32'
LF_INIT = 'cae48625419b5fe5baecdd670651bbf9bf205f24a7fc89def84f0609e2d57fee'
NATIVE_APPROVAL = 'CP23_B4_V2_R2_ONE_BOUNDED_NATIVE_RUN_SEPARATELY_OWNER_APPROVED'
# Persistent source lock MUST remain False. A signed, one-use capability is not
# a modification of this flag; no default or command-line-only native admission.
OWNER_PERMIT_SCHEMA = 'CP23_D13_SIGNED_ONE_RUN_V1'
PERMIT_DOMAIN = b'CP23_NATIVE_R2_PERMIT_V1\x00'
OWNER_PUBKEY_PATH = Path(r'C:\Users\ADMIN\.ssh\cp23_owner_ed25519_public.raw')
OWNER_SPKI_PATH = REPORTS / 'CP23_D13_OWNER_ED25519_SPKI.der'
OPENSSL_EXE = Path(r'C:\Program Files\Git\usr\bin\openssl.exe')
OPENSSL_SHA = '2c6f2c64612cf45349f15850e4647b2fe594c2759de63a695ec4cbe13b2404da'
OBSERVED_CANONICAL_HEAD_OID = '90140c9064392540c9a26e71ea7fc163a43ebd58'
ACCEPTED_CP19_CORE_REFERENCE_OID = '006803c2bdd6be566c53af40af0232fe229185c1'
# Owner's separately approved raw 32-byte key fingerprint, NEVER operator supplied.
OWNER_PUBKEY_SHA256_TRUST_ANCHOR = '475620139d17a56489ce5f591c40cae7eda08fe0cf9987cd56493aca218a5f18'


class Hold(RuntimeError): pass

def need(ok, token):
    if not ok:
        raise Hold('CP23_' + token)

def digest(data): return hashlib.sha256(data).hexdigest()

def raw_read(path, cap=36*1024*1024):
    need(path.is_file() and not path.is_symlink() and
         not getattr(path.stat(follow_symlinks=False),'st_file_attributes',0) &
         getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024) and
         path.stat().st_size <= cap,
         'FILE_NOT_REGULAR_OR_TOO_LARGE:' + str(path))
    return path.read_bytes()

def trusted_dir(path):
    need(path.is_dir() and not path.is_symlink(), 'DIR_NOT_TRUSTED:' + str(path))
    attributes = getattr(path.stat(follow_symlinks=False),'st_file_attributes',0)
    need(not attributes & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024),
         'DIR_REPARSE_DENIED:' + str(path))

def verify_source_identity():
    need(sys.platform == 'win32' and os.name == 'nt', 'WINDOWS_ONLY')
    for directory in (ROOT, CORE, ROOT/'tools', REPORTS, ROOT/'.git'):
        trusted_dir(directory)
    actual = {}
    for n,expected in SOURCE_PINS.items():
        b = raw_read(CORE/n)
        need(digest(b) == expected, 'EXISTING_V2_SOURCE_PIN_DRIFT:' + n)
        actual[n] = expected
    for n,expected in NEW_SOURCE_PINS.items():
        b = raw_read(CORE/n)
        need(digest(b) == expected, 'INTEGRATION_SOURCE_PIN_DRIFT:' + n)
        actual[n] = expected
    need(digest(raw_read(CORE/'cp23_b4_v2_contract_r1.py')) == CONTRACT_R1_SOURCE_SHA,
         'CONTRACT_R1_SOURCE_PIN_DRIFT')
    need(digest(raw_read(CORE/'cp23_b4_v2_extensions_r1.json')) == EXT_MANIFEST_R1_SHA,
         'EXTENSION_MANIFEST_R1_PIN_DRIFT')
    need(digest(raw_read(ROOT/'tools'/'cp23_v2_verifier_r2.py')) == REVISED_R2_VERIFIER_SHA,
         'REVISED_VERIFIER_R2_SOURCE_PIN_DRIFT')
    init = raw_read(CORE/'__init__.py')
    need(digest(init) == RAW_INIT and digest(init.replace(b'\r\n',b'\n')) == LF_INIT,
         'CANONICAL_OWNER_APPROVED_BASELINE_DRIFT')
    return actual

def historical_core_pins():
    b = raw_read(CORE/'mesh_projection_v2.py')
    tree=ast.parse(b)
    f=next((node for node in tree.body if isinstance(node,ast.FunctionDef) and
            node.name=='verify_core'),None)
    need(f is not None, 'V2_VERIFY_CORE_AST_MISSING')
    assignment=next((x for x in f.body if isinstance(x,ast.Assign) and
                  any(isinstance(t,ast.Name) and t.id=='_contract' for t in x.targets)),None)
    need(assignment is not None,'ORIGINAL_CONTRACT_MISSING')
    contract=ast.literal_eval(assignment.value)
    pins=contract['core_pins']
    need(len(pins)==119 and all(isinstance(v,str) and len(v)==64 for v in pins.values()),
         'SOURCE_PIN_MANIFEST_INVALID')
    return tuple(sorted(pins)),pins

def verify_revised_r2_runtime():
    """Use the NEW R2 verifier. Never invoke original B4 verify_core()."""
    from tools import cp23_v2_verifier_r2 as verifier
    expected = str(ROOT/'tools'/'cp23_v2_verifier_r2.py')
    need(getattr(verifier,'__file__',None) == expected and
         getattr(getattr(verifier,'__spec__',None),'origin',None) == expected,
         'R2_VERIFIER_CANONICAL_IMPORT_ORIGIN')
    need(getattr(verifier,'SOURCE_IDENTITY',None)==
         'CP23_B4_V2_REVISED_VERIFIER_R2' and
         verifier.NATIVE_ADMISSION is False,
         'R2_VERIFIER_IDENTITY_OR_NATIVE_LOCK')
    return verifier.verify_r2_canonical(ROOT,check_loaded=True)

def verify_core119():
    paths,pins=historical_core_pins()
    for rel in paths:
        p=ROOT.joinpath(*rel.split('/'))
        data=raw_read(p,2*1024*1024)
        lf=digest(data.replace(b'\r\n',b'\n'))
        expected=LF_INIT if rel=='mmd_registry/__init__.py' else pins[rel]
        need(lf==expected, 'CANONICAL_CORE_BASELINE_DRIFT:' + rel)
    return paths

def iter_inventory(base, *, files_content, max_items=50000, max_total_bytes=1024*1024*1024):
    """Bounded no-link inventory; each per-path record allows a specific delta."""
    trusted_dir(base)
    result={}
    stack=[base]
    bytes_seen=0
    while stack:
        folder=stack.pop()
        trusted_dir(folder)
        for p in sorted(folder.iterdir(),key=lambda q:q.name.casefold()):
            rel=p.relative_to(base).as_posix()
            st=p.lstat()
            need(not p.is_symlink() and
                 not getattr(st,'st_file_attributes',0) &
                 getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024),
                 'INVENTORY_SYMLINK_OR_REPARSE:' + str(p))
            need(len(result)<max_items,'INVENTORY_ENTRY_CAP')
            if p.is_dir():
                result[rel]={'type':'dir','size':0,'mtime_ns':st.st_mtime_ns}
                stack.append(p)
            elif p.is_file():
                bytes_seen += st.st_size
                need(bytes_seen<=max_total_bytes,'INVENTORY_BYTES_CAP')
                record={'type':'file','size':st.st_size,'mtime_ns':st.st_mtime_ns}
                if files_content:
                    need(st.st_size<=36*1024*1024,'INVENTORY_FILE_SIZE_CAP')
                    record['sha256']=digest(raw_read(p))
                result[rel]=record
            else:
                raise Hold('CP23_UNEXPECTED_INVENTORY_FILE_TYPE:' + str(p))
    return result

def git_controls(root):
    """Control content is separate from object-store timestamps/metadata."""
    base=root/'.git'
    trusted_dir(base)
    files=['HEAD','config','index','packed-refs','shallow','commondir','objects/info/alternates']
    refs=base/'refs'
    if refs.exists():
        trusted_dir(refs)
        refs_map=iter_inventory(refs,files_content=False,max_items=30000)
        files.extend('refs/'+x for x,v in refs_map.items() if v['type']=='file')
    result={}
    for rel in sorted(files):
        p=base.joinpath(*rel.split('/'))
        if not p.exists():
            result[rel]=None; continue
        result[rel]=digest(raw_read(p,8*1024*1024))
    return result

def delta(before,after):
    all_keys=set(before)|set(after)
    return [{'path':p,'before':before.get(p),'after':after.get(p)} for p in sorted(all_keys)
            if before.get(p)!=after.get(p)]

def sealed_paths(scope, key):
    items=scope[key]
    need(type(items) is list and 0 < len(items) <= 10000 and
         len(items) == len(set(items)) and all(type(x) is str for x in items),
         'SIGNED_PATHS_INVALID:'+key)
    return tuple(Path(x) for x in items)

def _under(path, parent):
    # Pure path containment on canonical Windows literals, not a permission grant.
    p=ntpath.normcase(ntpath.normpath(str(path)))
    root=ntpath.normcase(ntpath.normpath(str(parent)))
    return p.startswith(root+'\\') and p!=root and '..' not in path.parts

def _entry(path, *, content):
    need(path.exists() and not path.is_symlink(), 'SEALED_PATH_MISSING_OR_LINK:'+str(path))
    st=path.stat(follow_symlinks=False)
    need(not getattr(st,'st_file_attributes',0) &
         getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024), 'SEALED_PATH_REPARSE')
    rec={'kind':'file' if path.is_file() else 'dir' if path.is_dir() else 'other',
         'size':st.st_size,'mtime_ns':st.st_mtime_ns}
    need(rec['kind']!='other','SEALED_TYPE_NOT_ALLOWED')
    if content:
        need(rec['kind']=='file','SEALED_CONTENT_MUST_BE_FILE')
        rec['sha256']=digest(raw_read(path,36*1024*1024))
    return rec

def protected_snapshot(scope):
    # No wildcard exploration. Every path must appear in the separately signed
    # and Owner-authorized read inventory BEFORE being inspected.
    source,controls,metadata={}, {}, {}
    for p in sealed_paths(scope,'protected_source_files'):
        need(_under(p,CORE) or _under(p,ROOT/'tools'), 'SOURCE_PATH_OUT_OF_SCOPE')
        need(str(p) in scope['allowed_file_reads'],'SOURCE_READ_NOT_APPROVED')
        source[str(p)]=_entry(p,content=True)
    for p in sealed_paths(scope,'git_control_files'):
        need(_under(p,ROOT/'.git'), 'GIT_CONTROL_PATH_OUT_OF_SCOPE')
        need(str(p) in scope['allowed_file_reads'],'GIT_CONTROL_READ_NOT_APPROVED')
        controls[str(p)]=_entry(p,content=True)
    for p in sealed_paths(scope,'git_metadata_paths'):
        need(_under(p,ROOT/'.git'), 'GIT_METADATA_PATH_OUT_OF_SCOPE')
        need(str(p) in scope['allowed_file_reads'] or str(p) in scope['allowed_directories'],
             'GIT_METADATA_READ_NOT_APPROVED')
        metadata[str(p)]=_entry(p,content=False)
    listing={}
    for d in sealed_paths(scope,'allowed_directories'):
        need(d.is_dir(), 'SEALED_SCAN_DIR_MISSING')
        # Approved directory listing only; no content reads or recursive descent.
        entries=sorted((x.name for x in d.iterdir()),key=str.casefold)
        need(len(entries)<=20000, 'SEALED_SCAN_ENTRY_LIMIT')
        listing[str(d)]=entries
    return {'source_content_and_metadata':source,
            'git_controls_content_and_metadata':controls,
            'git_store_metadata':metadata,
            'authorized_directory_entries':listing}

def separate_deltas(before,after):
    def content(src):
        return {k:{'sha256':v.get('sha256'),'kind':v['kind']}
                for k,v in src.items()}
    def metadata(src):
        return {k:{j:v[j] for j in ('kind','size','mtime_ns')}
                for k,v in src.items()}
    return {
        'source_content':delta(content(before['source_content_and_metadata']),
                               content(after['source_content_and_metadata'])),
        'source_metadata':delta(metadata(before['source_content_and_metadata']),
                                metadata(after['source_content_and_metadata'])),
        'git_controls_content':delta(content(before['git_controls_content_and_metadata']),
                                     content(after['git_controls_content_and_metadata'])),
        'git_controls_metadata':delta(metadata(before['git_controls_content_and_metadata']),
                                      metadata(after['git_controls_content_and_metadata'])),
        'git_store_metadata':delta(before['git_store_metadata'],after['git_store_metadata']),
        'authorized_directory_entries':delta(before['authorized_directory_entries'],
                                             after['authorized_directory_entries']),
    }

def delta(a,b):
    return [{'path':k,'before':a.get(k),'after':b.get(k)} for k in sorted(set(a)|set(b))
            if a.get(k)!=b.get(k)]

def _unique_pairs(pairs):
    obj={}
    for k,v in pairs:
        need(k not in obj, 'JSON_DUPLICATE_KEY:'+k)
        obj[k]=v
    return obj

def sha_shape(x):
    return type(x) is str and re.fullmatch('[0-9a-f]{64}',x) is not None

def oid_shape(x):
    return type(x) is str and re.fullmatch('[0-9a-f]{40}',x) is not None

def _strict_approval_file(path, *, max_size):
    p=Path(path)
    need(p.parent==REPORTS,'SIGNED_INPUT_OUTSIDE_APPROVED_REPORTS')
    trusted_dir(p.parent)
    return raw_read(p,max_size)

def canonical_json(obj):
    # Intentionally small deterministic JSON subset: no floats, NaNs, NULs,
    # duplicate keys, or alternate textual spellings. All bytes ASCII.
    def walk(x):
        if x is None or type(x) in (str,int,bool):
            if type(x) is str:need('\x00' not in x,'JSON_STRING_NUL')
            return
        if type(x) is list:
            for y in x:walk(y)
            return
        need(type(x) is dict,'JSON_UNSUPPORTED_VALUE')
        for k,v in x.items():
            need(type(k) is str and k,'JSON_KEY_TYPE')
            walk(k);walk(v)
    walk(obj)
    return json.dumps(obj,sort_keys=True,ensure_ascii=True,
                      separators=(',',':'),allow_nan=False).encode('ascii')

def decode_signed_payload(binary):
    need(binary.startswith(PERMIT_DOMAIN) and len(binary)>len(PERMIT_DOMAIN)+8,
         'SIGNED_DOMAIN_SEPARATOR_MISMATCH')
    offset=len(PERMIT_DOMAIN)
    n=int.from_bytes(binary[offset:offset+8],'big')
    data=binary[offset+8:]
    need(0<n<=32768 and len(data)==n,'SIGNED_PAYLOAD_LENGTH_DRIFT')
    try:obj=json.loads(data.decode('ascii'),object_pairs_hook=_unique_pairs)
    except (ValueError,UnicodeError) as exc:raise Hold('CP23_SIGNED_JSON_INVALID') from exc
    need(data==canonical_json(obj),'SIGNED_JSON_NONCANONICAL')
    return obj

def owner_public_spki(raw):
    need(type(raw) is bytes and len(raw)==32 and
         digest(raw)==OWNER_PUBKEY_SHA256_TRUST_ANCHOR,
         'OWNER_PUBLIC_KEY_UNTRUSTED')
    return bytes.fromhex('302a300506032b6570032100')+raw

def verify_detached_with_openssl(*,openssl_exe,openssl_sha,spki_path,
                                  signed_file,signature_file):
    need(digest(raw_read(Path(openssl_exe),36*1024*1024))==openssl_sha,
         'OPENSSL_EXE_IDENTITY_DRIFT')
    # Established crypto only, never an Ed25519 implementation in Python.
    # This one extra subprocess is a permit signature check, not a Git child.
    argv=[str(openssl_exe),'pkeyutl','-verify','-pubin','-keyform','DER',
          '-inkey',str(spki_path),'-rawin','-in',str(signed_file),
          '-sigfile',str(signature_file)]
    try:
        out=subprocess.run(argv,cwd=str(ROOT),env={
            'SystemRoot':os.environ.get('SystemRoot',r'C:\Windows'),
            'WINDIR':os.environ.get('SystemRoot',r'C:\Windows'),
            'PATH':r'C:\Program Files\Git\usr\bin;C:\Windows\System32;C:\Windows',
            'OPENSSL_CONF':'NUL',
        },stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            shell=False,timeout=10,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Hold('CP23_OPENSSL_SIGNATURE_VERIFICATION_EXEC_FAILED') from exc
    need(len(out.stdout)<=4096 and len(out.stderr)<=4096 and out.returncode==0,
         'OWNER_ED25519_SIGNATURE_INVALID')
    return True

SCOPE_FIELDS=frozenset({
 'root','runner_sha256','verifier_sha256','contract_sha256',
 'extension_manifest_sha256','owner_public_key_sha256',
 'openssl_executable_path','openssl_executable_sha256',
 'git_executable_path','git_executable_sha256',
 'git_actual_runtime_image_path','git_actual_runtime_image_sha256',
 'observed_canonical_head_oid','accepted_cp19_core_reference_oid',
 'expected_head_ref','cwd','git_dir','argv','environment',
 'allowed_file_reads','allowed_directories','protected_source_files',
 'git_control_files','git_metadata_paths','git_object_files',
 'report_path','consumption_record_path','max_git_children',
 'per_child_timeout_seconds','batch_deadline_seconds',
 'aggregate_stdout_stderr_cap_bytes','no_retry','no_network',
 'no_mutations','protected_postflight','child_descendant_policy',
 'reports_dir_acl_sha256','approval_b_manifest_sha256',
})

def validate_signed_scope(scope,*,report,consume_path):
    need(type(scope) is dict and set(scope)==SCOPE_FIELDS,'SIGNED_SCOPE_KEYS_NOT_EXACT')
    from mmd_registry.cp23_n23_owner_v2 import GIT_EXE,GIT_SHA
    static={
       'root':str(ROOT),'runner_sha256':digest(raw_read(Path(__file__))),
       'verifier_sha256':REVISED_R2_VERIFIER_SHA,
       'contract_sha256':CONTRACT_R1_SOURCE_SHA,
       'extension_manifest_sha256':EXT_MANIFEST_R1_SHA,
       'owner_public_key_sha256':OWNER_PUBKEY_SHA256_TRUST_ANCHOR,
       'openssl_executable_path':str(OPENSSL_EXE),
       'openssl_executable_sha256':OPENSSL_SHA,
       'git_executable_path':GIT_EXE,'git_executable_sha256':GIT_SHA,
       'observed_canonical_head_oid':OBSERVED_CANONICAL_HEAD_OID,
       'accepted_cp19_core_reference_oid':ACCEPTED_CP19_CORE_REFERENCE_OID,
       'cwd':str(ROOT),'git_dir':str(ROOT/'.git'),
       'argv':['rev-parse','--verify','HEAD^{commit}'],
       'expected_head_ref':'refs/heads/feature/v0.9.5.11-smart-morph-core',
       'report_path':str(report),'consumption_record_path':str(consume_path),
       'max_git_children':1,'per_child_timeout_seconds':65,
       'aggregate_stdout_stderr_cap_bytes':24*1024*1024,
       'no_retry':True,'no_network':True,'no_mutations':True,
       'protected_postflight':True,
       'child_descendant_policy':'OS_JOB_NO_BREAKAWAY_WITH_RUNTIME_ATTESTATION',
    }
    need(all(scope[k]==v and type(scope[k]) is type(v) for k,v in static.items()),
         'SIGNED_STATIC_SCOPE_OR_DUAL_BASELINE_DRIFT')
    need(type(scope['batch_deadline_seconds']) is int and
         1<=scope['batch_deadline_seconds']<=65,'SIGNED_DEADLINE_INVALID')
    need(sha_shape(scope['approval_b_manifest_sha256']) and
         sha_shape(scope['reports_dir_acl_sha256']), 'B_MANIFEST_OR_REPORT_ACL_PIN_MISSING')
    need(type(scope['git_actual_runtime_image_path']) is str and
         sha_shape(scope['git_actual_runtime_image_sha256']),
         'DELEGATED_RUNTIME_IMAGE_NOT_SEALED')
    need(report.parent==REPORTS and consume_path.parent==REPORTS and
         report!=consume_path and not report.exists() and not consume_path.exists() and
         re.fullmatch(r'CP23_D13_NATIVE_RESULT_[A-Z0-9_]{8,40}\.txt',report.name) and
         re.fullmatch(r'CP23_D13_CONSUMED_[A-Z0-9_]{8,40}\.txt',consume_path.name),
         'EXACT_CREATE_ONLY_OUTPUT_PATH_DENIED')
    for name in ('allowed_file_reads','allowed_directories','protected_source_files',
                 'git_control_files','git_metadata_paths','git_object_files'):
        paths=scope[name]
        need(type(paths) is list and 0<len(paths)<=10000 and
             len(paths)==len(set(paths)) and all(type(x) is str and
             (x.startswith('D:\\') or x.startswith('C:\\')) and
             '\x00' not in x and not any(y in ('..','.') for y in x.replace('/','\\').split('\\'))
             for x in paths), 'SIGNED_PATH_LIST_INVALID:'+name)
    for name in ('protected_source_files','git_control_files','git_object_files'):
        need(set(scope[name]).issubset(set(scope['allowed_file_reads'])),
             'SIGNED_READ_SCOPE_NOT_CLOSED:'+name)
    need(set(scope['git_metadata_paths']).issubset(
         set(scope['allowed_file_reads'])|set(scope['allowed_directories'])),
         'SIGNED_METADATA_SCOPE_NOT_CLOSED')
    # A signed map is not enough if original Repo inherits extra host variables.
    env=scope['environment']
    need(type(env) is dict and env and all(type(k) is str and
         type(v) is str and '\x00' not in v for k,v in env.items()) and
         len({k.upper() for k in env})==len(env), 'SIGNED_ENV_SHAPE_INVALID')
    allowed_base=frozenset({'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC',
         'TEMP','TMP','USERPROFILE','USERNAME','USERDOMAIN','HOMEDRIVE',
         'HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMDATA','PROGRAMFILES',
         'PROGRAMFILES(X86)','COMMONPROGRAMFILES','ALLUSERSPROFILE',
         'SYSTEMDRIVE','OS','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS'})
    from mmd_registry.cp23_n23_owner_v2 import EXPECTED_GIT_ENV
    allow_upper=allowed_base|frozenset(k.upper() for k in EXPECTED_GIT_ENV)
    need(set(k.upper() for k in env)<=allow_upper and
         all(env.get(k)==v for k,v in EXPECTED_GIT_ENV.items()) and
         env.get('GIT_CONFIG_GLOBAL')==os.devnull and
         env.get('GIT_CONFIG_SYSTEM')==os.devnull,
         'UNCONTROLLED_GIT_PROCESS_ENVIRONMENT')
    # Original Repo.__init__ inherits non-GIT variables from the host. Reject
    # unexpected inherited names; never mutate os.environ to force a pass.
    inherited={k:v for k,v in os.environ.items() if not k.upper().startswith('GIT_')}
    need(set(k.upper() for k in inherited)<=allowed_base,
         'ORIGINAL_REPO_WOULD_INHERIT_UNAPPROVED_VARIABLES')
    effective=dict(inherited);effective.update(EXPECTED_GIT_ENV)
    need(effective==env,'SIGNED_EFFECTIVE_ENV_NOT_EQUAL_TO_REPO')
    return MappingProxyType(scope)

def load_signed_one_time_capability(*,permit_file,signature_file,
                approved_permit_sha,owner_decision_id,report,consume_path):
    need(NATIVE_ADMISSION is False,'PERSISTENT_NATIVE_DEFAULT_TAMPERED')
    need(all(x is not None for x in (permit_file,signature_file,
         approved_permit_sha,owner_decision_id,report,consume_path)),
         'INDEPENDENT_OWNER_DECISION_REQUIRED')
    need(sha_shape(approved_permit_sha) and type(owner_decision_id) is str and
         re.fullmatch(r'[A-Z0-9_-]{12,120}',owner_decision_id),
         'OWNER_DECISION_PIN_MALFORMED')
    trusted_dir(OWNER_PUBKEY_PATH.parent)
    raw=raw_read(OWNER_PUBKEY_PATH,32)
    spki=owner_public_spki(raw)
    need(raw_read(OWNER_SPKI_PATH,44)==spki,'OWNER_SPKI_CREATION_OR_PIN_MISSING')
    permit=_strict_approval_file(permit_file,max_size=32768+64)
    sig=_strict_approval_file(signature_file,max_size=64)
    need(digest(permit)==approved_permit_sha and len(sig)==64,
         'SIGNED_PERMIT_SHA_OR_SIGNATURE_LENGTH_DRIFT')
    obj=decode_signed_payload(permit)
    need(type(obj) is dict and set(obj)=={'schema','decision_id','permit_id',
         'issued_unix','expires_unix','scope'},'PERMIT_TOP_LEVEL_KEYS')
    need(obj['schema']==OWNER_PERMIT_SCHEMA and obj['decision_id']==owner_decision_id and
         type(obj['permit_id']) is str and
         re.fullmatch('[A-Z0-9_]{8,40}',obj['permit_id']) and
         type(obj['issued_unix']) is int and type(obj['expires_unix']) is int and
         obj['issued_unix']<=int(time.time())<=obj['expires_unix'] and
         0<obj['expires_unix']-obj['issued_unix']<=3600,
         'OWNER_DECISION_OR_EXPIRED_PERMIT')
    need(report.name==f'CP23_D13_NATIVE_RESULT_{obj["permit_id"]}.txt' and
         consume_path.name==f'CP23_D13_CONSUMED_{obj["permit_id"]}.txt',
         'SIGNED_PERMIT_ID_NOT_BOUND_TO_OUTPUTS')
    # Verify exact Owner-approved signature using the pinned OpenSSL executable.
    # Public SPKI is derived at Authorization A, never passed through permit.
    verify_detached_with_openssl(openssl_exe=OPENSSL_EXE,openssl_sha=OPENSSL_SHA,
                 spki_path=OWNER_SPKI_PATH,signed_file=permit_file,
                 signature_file=signature_file)
    scope=validate_signed_scope(obj['scope'],report=report,consume_path=consume_path)
    class Capability:
        scope_verified=True
        def __init__(self, d):self.scope=d
    return Capability(scope)

def _read_head_without_git(expected_ref, expected_oid):
    """Do not invoke Git or follow aliases when sealing HEAD."""
    head=raw_read(ROOT/'.git'/'HEAD',2048)
    need(head.startswith(b'ref: ') and head.rstrip(b'\r\n')==
         ('ref: '+expected_ref).encode('ascii'), 'HEAD_REF_NOT_PINNED')
    # Loose-ref only; packed-refs/head alternatives require separate design.
    path=ROOT/'.git'/Path(expected_ref)
    need(path.parent.is_dir(), 'HEAD_REF_PARENT_MISSING')
    value=raw_read(path,1024).strip().decode('ascii')
    need(oid_shape(value) and value==expected_oid,'HEAD_OID_NOT_SEALED')
    return {'head_sha256':digest(head),'ref_sha256':digest(raw_read(path,1024)),
            'head_ref':expected_ref,'head_oid':value}

def consume_approved_attempt(path, capability, owner_decision_id):
    """Atomic cross-process, create-only consumption; no retry on failure."""
    need(path==Path(capability.scope['consumption_record_path']) and
         path.parent==REPORTS and not path.exists(), 'CONSUMPTION_SCOPE_OR_REPLAY')
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,'O_BINARY'):flags|=os.O_BINARY
    try:fd=os.open(path,flags,0o600)
    except FileExistsError as e:raise Hold('CP23_NATIVE_PERMIT_ALREADY_CONSUMED') from e
    with os.fdopen(fd,'wb') as f:
        record=(f'DECISION_ID={owner_decision_id}\r\n'
                f'CONSUMED_BEFORE_ANY_GIT_PROCESS=YES\r\n'
                f'RETRY=FORBIDDEN\r\n')
        f.write(record.encode('ascii'));f.flush();os.fsync(f.fileno())
    return True

def verify_loose_commit(scope):
    oid=scope['observed_canonical_head_oid']
    path=ROOT/'.git'/'objects'/oid[:2]/oid[2:]
    need(str(path) in scope['git_object_files'] and
         str(path) in scope['allowed_file_reads'],
         'EXACT_GIT_COMMIT_OBJECT_NOT_AUTHORIZED')
    compressed=raw_read(path,8*1024*1024)
    try:
        z=zlib.decompressobj()
        raw=z.decompress(compressed,8*1024*1024+1)
        need(z.eof and not z.unconsumed_tail and not z.unused_data,
             'GIT_OBJECT_STREAM_NOT_COMPLETE_OR_TOO_LARGE')
    except (ValueError,zlib.error) as exc:raise Hold('CP23_GIT_OBJECT_ZLIB_INVALID') from exc
    need(len(raw)<=8*1024*1024 and raw.startswith(b'commit ') and
         b'\x00' in raw and hashlib.sha1(raw).hexdigest()==oid,
         'CANONICAL_COMMIT_OBJECT_IDENTITY_DRIFT')
    return {'path':str(path),'sha256':digest(compressed),'oid':oid}

def validate_approval_b(scope):
    manifest=REPORTS/'CP23_D13_SEALED_MANIFEST.json'
    need(str(manifest) in scope['allowed_file_reads'],
         'APPROVAL_B_EXACT_MANIFEST_READ_NOT_AUTHORIZED')
    raw=raw_read(manifest,65536)
    need(digest(raw)==scope['approval_b_manifest_sha256'],
         'APPROVAL_B_MANIFEST_SHA_CHANGED')
    obj=json.loads(raw.decode('utf-8'),object_pairs_hook=_unique_pairs)
    need(type(obj) is dict and obj.get('native_execution_authorized') is False and
         obj.get('observed_canonical_head_oid')==OBSERVED_CANONICAL_HEAD_OID and
         obj.get('accepted_cp19_core_reference_oid')==ACCEPTED_CP19_CORE_REFERENCE_OID,
         'APPROVAL_B_PROVENANCE_DRIFT')
    # Read-only identity sealing never authorizes native execution by itself.
    return {'manifest_sha256':digest(raw),'status':'READONLY_PROVENANCE_NOT_NATIVE_APPROVAL'}

def _report_dir_acl_sha(path):
    # Windows security descriptor checksum: runtime must match Owner-approved B.
    import ctypes
    from ctypes import wintypes
    sec=ctypes.WinDLL('advapi32',use_last_error=True)
    kern=ctypes.WinDLL('kernel32',use_last_error=True)
    get=sec.GetNamedSecurityInfoW
    get.argtypes=[wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD,
                  ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                  ctypes.POINTER(ctypes.c_void_p)]
    get.restype=wintypes.DWORD
    tostr=sec.ConvertSecurityDescriptorToStringSecurityDescriptorW
    tostr.argtypes=[ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,
                    ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(wintypes.DWORD)]
    tostr.restype=wintypes.BOOL
    free=kern.LocalFree;free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
    sd=ctypes.c_void_p(); output=ctypes.c_void_p(); length=wintypes.DWORD()
    # SE_FILE_OBJECT=1; OWNER_SECURITY_INFORMATION=1; DACL=4
    rc=get(str(path),1,5,None,None,None,None,ctypes.byref(sd))
    need(rc==0 and bool(sd.value),'WINDOWS_REPORTS_DIRECTORY_DACL_UNAVAILABLE')
    try:
        need(bool(tostr(sd,1,5,ctypes.byref(output),ctypes.byref(length))),
             'WINDOWS_REPORTS_DIRECTORY_SDDL_UNAVAILABLE')
        string=ctypes.wstring_at(output,length.value)
        return digest(string.encode('utf-8'))
    finally:
        if output.value:free(output)
        if sd.value:free(sd)

def _initial_process_image_binding():
    # Pinned API is bound before N23 audit bootstrap; never dynamically loads
    # an unlisted ctypes DLL after the audit hook is installed.
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    query=kernel.QueryFullProcessImageNameW
    query.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,
                    ctypes.POINTER(wintypes.DWORD)]
    query.restype=wintypes.BOOL
    def actual(handle):
        buffer=ctypes.create_unicode_buffer(32768)
        length=wintypes.DWORD(len(buffer))
        need(bool(query(handle,0,buffer,ctypes.byref(length))),
             'INITIAL_GIT_PROCESS_IMAGE_QUERY_FAILED')
        return buffer.value[:length.value]
    return actual

def native_integration(*,permit_file=None,signature_file=None,
                       approved_permit_sha=None,owner_decision_id=None,
                       report=None,consumption_record=None):
    """D13 exact signed, single-attempt R2 path; NEVER original verify_core().

    An approved source install does not run this. Owner C must separately sign
    the C manifest and authorization, including OpenSSL verification executable.
    """
    need(NATIVE_ADMISSION is False,'PERSISTENT_NATIVE_DEFAULT_MUST_REMAIN_FALSE')
    need(sys.platform=='win32' and os.name=='nt','WINDOWS_ONLY')
    report=Path(report) if report else None
    consumed=Path(consumption_record) if consumption_record else None
    need(report is not None and consumed is not None,
         'OWNER_APPROVED_EXACT_EVIDENCE_PATHS_REQUIRED')
    capability=load_signed_one_time_capability(
        permit_file=permit_file,signature_file=signature_file,
        approved_permit_sha=approved_permit_sha,
        owner_decision_id=owner_decision_id,report=report,consume_path=consumed)
    scope=capability.scope
    verify_source_identity()
    need(sys.dont_write_bytecode,'PYTHON_BYTECODE_WRITES_NOT_DISABLED')
    need(_report_dir_acl_sha(REPORTS)==scope['reports_dir_acl_sha256'],
         'REPORTS_ACL_NOT_MATCHING_APPROVAL_B')
    paths=verify_core119()
    need(str(ROOT) not in sys.path or sys.path[0]==str(ROOT),
         'CANONICAL_SYS_PATH_HAS_ALTERNATE_ENTRY')
    if sys.path[0]!=str(ROOT):sys.path.insert(0,str(ROOT))
    importlib.invalidate_caches()
    b4=importlib.import_module('mmd_registry.mesh_projection_v2')
    importlib.import_module('mmd_registry.cp23_winjob_int')
    importlib.import_module('mmd_registry.cp23_b4_v2_contract_r1')
    from mmd_registry.cp23_n23_owner_int import Owner
    from mmd_registry.cp23_n23_owner_v2 import GIT_EXE,BARE,GIT_SHA
    verified=verify_revised_r2_runtime()
    Repo=verified['repo_class']
    contract_report={k:v for k,v in verified.items()
                     if k not in ('repo_class','run_code')}
    # B has not authorized recursive enumeration; only exact signed paths.
    b_provenance=validate_approval_b(scope)
    need(digest(raw_read(Path(GIT_EXE),32*1024*1024))==GIT_SHA,
         'WINDOWS_GIT_EXE_PIN_CHANGED')
    actual_path=Path(scope['git_actual_runtime_image_path'])
    need(str(actual_path) in scope['allowed_file_reads'] and
         digest(raw_read(actual_path,32*1024*1024))==scope['git_actual_runtime_image_sha256'],
         'GIT_DELEGATED_RUNTIME_IMAGE_PIN_CHANGED')
    need(str(ROOT/'.git'/'HEAD') in scope['git_control_files'] and
         str(ROOT/'.git'/Path(scope['expected_head_ref'])) in scope['git_control_files'],
         'EXACT_HEAD_CONTROL_READ_NOT_APPROVED')
    head_pre=_read_head_without_git(scope['expected_head_ref'],
                                    scope['observed_canonical_head_oid'])
    commit=verify_loose_commit(scope)
    before=protected_snapshot(scope)
    initial_image=_initial_process_image_binding()
    initial_images=[]
    # Explicit subclass exposes an additional identity check at the exact
    # original N23 before_resume callsite. Never patch Owner or Job Gate source.
    class ExactOwner(Owner):
        def before_resume(self,frame,pid,process_handle,job_handle):
            image=initial_image(process_handle)
            need(ntpath.normcase(image)==ntpath.normcase(GIT_EXE),
                 'JOB_SUSPENDED_INITIAL_IMAGE_NOT_PINNED')
            initial_images.append(image)
            return super().before_resume(frame,pid,process_handle,job_handle)
    owner=ExactOwner(core_paths=paths,
                     read_files=tuple(scope['allowed_file_reads']),
                     scan_dirs=tuple(scope['allowed_directories']),
                     native_capability=capability)
    owner.pin_original(b4)
    need(Repo._run.__code__ == owner.expected_run,
         'EXACT_ORIGINAL_V2_RUN_CODE_OBJECT_NOT_PRESERVED')
    need(str(Path(BARE)/'config') in scope['allowed_file_reads'],
         'HISTORICAL_BARE_CONFIG_READ_NOT_APPROVED')
    owner.pin_native_inputs()
    owner.deadline=time.monotonic()+scope['batch_deadline_seconds']
    def forbid(*args,**kwargs):raise Hold('R2_REPO_UNAPPROVED_CALLBACK')
    repo=Repo(Path(GIT_EXE),ROOT/'.git',ROOT,ROOT,forbid,forbid)
    need(repo._env==scope['environment'],
         'REBOUND_ORIGINAL_REPO_EFFECTIVE_ENV_DRIFT')
    # Before native creation, atomic consumption and durable HOLD-first record.
    consume_approved_attempt(consumed,capability,owner_decision_id)
    with report.open('x',encoding='utf-8') as f:
        f.write('CP23_D13_NATIVE_SINGLE_ATTEMPT\nRESULT=HOLD_IN_PROGRESS\n'
                'AUTO_RETRY=FALSE\n');f.flush();os.fsync(f.fileno())
    error=None;result_sha=None;after=None;head_post=None
    owner.install_hook()
    try:
        with owner:
            _,raw=repo._run(['rev-parse','--verify','HEAD^{commit}'],
                            cap=1024,allowed=(0,))
            need(len(raw)<=1024 and oid_shape(raw.strip().decode('ascii')),
                 'R2_GIT_OUTPUT_NOT_EXACT_SHA1')
            result_sha=raw.strip().decode('ascii')
    except BaseException as exc:
        error=type(exc).__name__+':'+str(exc)[:300]
    finally:
        try:owner.finish()
        except BaseException as exc:
            error=(error or '')+';OWNER_FINISH='+str(exc)[:200]
        try:after=protected_snapshot(scope)
        except BaseException as exc:
            error=(error or '')+';POSTFLIGHT='+str(exc)[:200]
        try:
            head_post=_read_head_without_git(scope['expected_head_ref'],
                      scope['observed_canonical_head_oid'])
            need(head_post==head_pre,'HEAD_CHANGED_DURING_NATIVE_BATCH')
        except BaseException as exc:
            error=(error or '')+';HEAD_POST='+str(exc)[:200]
    changes=separate_deltas(before,after) if after is not None else None
    no_drift=changes is not None and all(not v for v in changes.values())
    # OS delegation/descendant identity is NOT attested merely by confirming
    # Job-before-resume for the initial wrapper. A full PASS must be gated on
    # additional exact Windows process-tree evidence reviewed by Owner.
    parent_ok=(len(initial_images)==1 and owner.resumed==owner.spawned==1)
    all_local=(error is None and no_drift and parent_ok and
               result_sha==scope['observed_canonical_head_oid'] and
               owner.runtime_code is owner.expected_run and head_post==head_pre)
    result={
       'result':'NATIVE_PASS_LIMITED_R2_HOLD' if all_local else 'HOLD_EXIT23',
       'full_native_attestation':False,
       'reason':'DESCENDANT_IMAGE_AND_PROCESS_TREE_NEED_INDEPENDENT_WINDOWS_ATTESTATION',
       'signed_owner_decision':owner_decision_id,
       'observed_canonical_head_oid':scope['observed_canonical_head_oid'],
       'accepted_cp19_core_reference_oid':scope['accepted_cp19_core_reference_oid'],
       'actual_output_oid':result_sha,
       'initial_process_image_observed':initial_images,
       'git_children':owner.spawned,'jobs_resumed':owner.resumed,
       'child_events':owner.child_events,'audit_events':owner.policy.events,
       'protected_deltas':changes,'head_pre':head_pre,'head_post':head_post,
       'loose_commit':commit,'approval_b':b_provenance,
       'permit_consumed_before_native':True,'consumption_path':str(consumed),
       'original_verify_core':'HOLD_UNMODIFIED_NOT_CALLED',
       'original_repo_run':'ONE_R2_CODE_REBOUND_CALL_NOT_HISTORICAL_12',
       'verifier':contract_report,'error':error,
       'historical_r1s':'HOLD','r14_g1':'HOLD','r14_g3':'NOT_ATTESTED',
       'promotion':'NOT_AUTHORIZED',
    }
    with report.open('r+',encoding='utf-8') as f:
        f.seek(0);json.dump(result,f,ensure_ascii=False,indent=2)
        f.truncate();f.flush();os.fsync(f.fileno())
    # Never return zero for the current limited OS evidence.
    return 23

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument('--native-execute',action='store_true')
    ap.add_argument('--native-permit')
    ap.add_argument('--permit-signature')
    ap.add_argument('--approved-permit-sha256')
    ap.add_argument('--owner-decision-id')
    ap.add_argument('--consumption-record')
    ap.add_argument('--report')
    args=ap.parse_args()
    try:
        need(args.native_execute, 'NO_NATIVE_ADMISSION_IN_DEFAULT_MODE')
        return native_integration(permit_file=args.native_permit,
                                  signature_file=args.permit_signature,
                                  approved_permit_sha=args.approved_permit_sha256,
                                  owner_decision_id=args.owner_decision_id,
                                  report=args.report,
                                  consumption_record=args.consumption_record)
    except BaseException as exc:
        print('CP23_NATIVE=HOLD_EXIT23')
        print('REASON='+type(exc).__name__+':'+str(exc)[:300])
        return 23

if __name__=='__main__':
    raise SystemExit(main())
