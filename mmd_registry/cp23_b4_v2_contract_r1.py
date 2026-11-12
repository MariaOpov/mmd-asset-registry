"""CP23 B4 V2 contract R1: canonical Core119 + explicitly pinned extensions.

Source-only verifier. Historical B4 verify_core() is NOT replaced or claimed to PASS.
Native admission and Git/process execution are outside this module's authority.
"""
from __future__ import annotations

import ast
import hashlib
import json
import ntpath
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType

CONTRACT_REVISION = 'CP23_B4_V2_CONTRACT_R1'
SCHEMA = 'CP23_B4_V2_EXPLICIT_EXTENSIONS_R1'
CANONICAL_ROOT = r'D:\MMD\mmd-asset-registry'
BASELINE_APPROVAL = 'APPROVE_B4_V2_CANONICAL_BASELINE_AND_NEW_SOURCE_FILES_ONLY'
HISTORICAL_COUNT = 119
OLD_INIT = '91015f768b78bdb15a55da2df70ed8d5960e71c848a6dc8c005011c2b024d5c1'
CANONICAL_INIT_NORMALIZED = 'cae48625419b5fe5baecdd670651bbf9bf205f24a7fc89def84f0609e2d57fee'
CANONICAL_INIT_RAW = '5e73f4f4e117fd56b1a06e3f0c429ed8ac3a7bbd729c838f326b2c6da93adf32'
V2_B4_SHA = '24eaaedeb6af5e1577849990d24514f484a5f298ccd29fc8d46c045860b37233'
EXTENSION_NAMES = (
    'mesh_projection_v2',
    'cp23_n23_owner_v2',
    'cp23_n23_policy_v2',
    'cp23_winjob_v2',
    'cp23_n23_owner_int',
    'cp23_n23_policy_int',
    'cp23_winjob_int',
    'cp23_b4_v2_contract_r1',
)
EXPECTED_EXISTING_SHA = {
    'mesh_projection_v2':'24eaaedeb6af5e1577849990d24514f484a5f298ccd29fc8d46c045860b37233',
    'cp23_n23_owner_v2':'360dac5aaf5cf8312e0cb1f51f84653e1e825c5fc505806c764212b43f004559',
    'cp23_n23_policy_v2':'7acf87e81caa97d70b195cade5e005b8cfb3553e6193aba6368263660e438e74',
    'cp23_winjob_v2':'1c1598936637e55eaee4341379520d996e82e634d0eb6fc43df94ab5ef5ce922',
    'cp23_n23_owner_int':'f5f3cb9717c7f1c876f96145ba9791ea8e15fd69a71f318cd52df1483ca345fb',
    'cp23_n23_policy_int':'df393c432cbf19226fd2d0c3ed961f5b3189e6c2be8f0cadd48bcc611008d083',
    'cp23_winjob_int':'f5cb3837223894028d63506eef6a69fe33b43444c4aecc36978778f4548031f0',
}
HEX64 = re.compile(r'[0-9a-f]{64}\Z')

class ContractHold(RuntimeError):
    pass

def require(ok, token):
    if not ok:
        raise ContractHold('CP23_CONTRACT_' + token)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def normalized_sha(data):
    return sha(data.replace(b'\r\n',b'\n'))

def exact_file(root: Path, rel: str, *, cap=8*1024*1024):
    """Read a regular file under a trusted root; deny symlink/junction ancestors."""
    require(isinstance(rel,str) and rel and '\\' not in rel and
            not rel.startswith('/') and all(p not in ('','.', '..') for p in rel.split('/')),
            'UNSAFE_RELATIVE_PATH')
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'ROOT_NOT_TRUSTED')
    cur = root
    parts = rel.split('/')
    for part in parts[:-1]:
        cur = cur / part
        require(cur.is_dir() and not cur.is_symlink(), 'DIRECTORY_NOT_TRUSTED')
        a=getattr(cur.stat(follow_symlinks=False),'st_file_attributes',0)
        require(not (a & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024)), 'DIRECTORY_REPARSE')
    p = cur / parts[-1]
    require(p.is_file() and not p.is_symlink(), 'FILE_MISSING_OR_LINK:' + rel)
    s=p.stat(follow_symlinks=False)
    require(not getattr(s,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024)
            and s.st_size<=cap, 'FILE_REPARSE_OR_SIZE:' + rel)
    require(p.resolve(strict=True).is_relative_to(root.resolve(strict=True)), 'PATH_ESCAPES_ROOT')
    return p.read_bytes()

def historical_pins_from_b4(b4_bytes):
    tree = ast.parse(b4_bytes, filename='mesh_projection_v2.py')
    functions = [x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='verify_core']
    require(len(functions)==1,'B4_VERIFY_CORE_NOT_UNIQUE')
    a=[x for x in functions[0].body if isinstance(x,ast.Assign) and
       any(isinstance(t,ast.Name) and t.id=='_contract' for t in x.targets)]
    require(len(a)==1, 'B4_CORE_CONTRACT_NOT_UNIQUE')
    contract=ast.literal_eval(a[0].value)
    pins=contract.get('core_pins')
    require(type(pins) is dict and len(pins)==HISTORICAL_COUNT,'HISTORICAL_CORE119_COUNT')
    require(all(isinstance(p,str) and p.startswith('mmd_registry/') and
                isinstance(v,str) and HEX64.fullmatch(v) for p,v in pins.items()),
            'HISTORICAL_PINS_SHAPE')
    require(pins.get('mmd_registry/__init__.py')==OLD_INIT,'HISTORICAL_INIT_IDENTITY_CHANGED')
    return pins

def validate_manifest(doc, *, contract_sha, manifest_sha=None, raw_manifest=None):
    """Validate document identity and exact membership; no wildcard or auto-accept."""
    if raw_manifest is not None and manifest_sha is not None:
        require(sha(raw_manifest)==manifest_sha,'MANIFEST_PIN_DRIFT')
    require(type(doc) is dict and set(doc)==
            {'schema','contract_revision','canonical_root','baseline_approval','historical_core',
             'extensions','original_verify_core_status'}, 'MANIFEST_FIELDS')
    require(doc['schema']==SCHEMA and doc['contract_revision']==CONTRACT_REVISION and
            doc['canonical_root']==CANONICAL_ROOT and
            doc['baseline_approval']==BASELINE_APPROVAL and
            doc['original_verify_core_status']=='UNMODIFIED_UNPINNED_EXTENSION_CLOSURE_HOLD',
            'MANIFEST_IDENTITY')
    h=doc['historical_core']
    require(type(h) is dict and set(h)=={'count','source','canonical_override'},
            'HISTORICAL_CORE_FIELDS')
    require(h['count']==119 and h['source']=='mesh_projection_v2.py::verify_core._contract.core_pins',
            'HISTORICAL_SOURCE_INVALID')
    overrides=h['canonical_override']
    require(type(overrides) is list and len(overrides)==1 and overrides[0]=={
        'relative_path':'mmd_registry/__init__.py','historical_normalized_sha256':OLD_INIT,
        'canonical_normalized_sha256':CANONICAL_INIT_NORMALIZED,
        'canonical_raw_sha256':CANONICAL_INIT_RAW,
    }, 'CANONICAL_OVERRIDE_MUST_BE_EXACT_ONE')
    items=doc['extensions']
    require(type(items) is list and len(items)==len(EXTENSION_NAMES),'EXTENSION_COUNT')
    seen_names=set(); seen_paths=set(); seen_origins=set()
    for n,item in zip(EXTENSION_NAMES,items):
        require(type(item) is dict and set(item)==
                {'module','relative_path','sha256','canonical_origin','source_identity','contract_revision'},
                'EXTENSION_ITEM_FIELDS')
        rel='mmd_registry/'+n+'.py'
        mod='mmd_registry.'+n
        origin=ntpath.join(CANONICAL_ROOT,'mmd_registry',n+'.py')
        digest=item['sha256']
        require(item['module']==mod and item['relative_path']==rel and
                item['canonical_origin']==origin and
                isinstance(digest,str) and HEX64.fullmatch(digest) and
                item['source_identity']=='sha256:'+digest and
                item['contract_revision']==CONTRACT_REVISION,
                'EXTENSION_EXPLICIT_IDENTITY:' + n)
        if n in EXPECTED_EXISTING_SHA:
            require(digest==EXPECTED_EXISTING_SHA[n],'EXISTING_EXTENSION_PIN_DRIFT:'+n)
        else:
            require(digest==contract_sha,'CONTRACT_SELF_SOURCE_PIN_DRIFT')
        require(mod not in seen_names and rel not in seen_paths and origin not in seen_origins,
                'EXTENSION_DUPLICATE')
        seen_names.add(mod);seen_paths.add(rel);seen_origins.add(origin)
    require(seen_names=={'mmd_registry.'+n for n in EXTENSION_NAMES}, 'MISSING_EXTENSION')
    return {x['module']:x for x in items}

def verify_canonical_core(root, pins):
    """Historical pins kept intact; canonical override exists only for init."""
    require(type(pins) is dict and len(pins)==119,'CORE119_NOT_ESTABLISHED')
    result={'historical_match':0,'canonical_exception':0,'canonical_count':0}
    for rel, old_sha in sorted(pins.items()):
        data=exact_file(root,rel,cap=4*1024*1024)
        if rel=='mmd_registry/__init__.py':
            require(old_sha==OLD_INIT and sha(data)==CANONICAL_INIT_RAW and
                    normalized_sha(data)==CANONICAL_INIT_NORMALIZED,
                    'OWNER_CANONICAL_INIT_DRIFT')
            result['canonical_exception']+=1
        else:
            require(normalized_sha(data)==old_sha,'CANONICAL_CORE_DRIFT:'+rel)
            result['historical_match']+=1
        result['canonical_count']+=1
    require(result=={'historical_match':118,'canonical_exception':1,'canonical_count':119},
            'CANONICAL_BASELINE_COUNT_DRIFT')
    return result

def verify_record_matrix(records, extensions, allowed_core):
    """Pure record validation for diagnostic tests; not OS/native attestation."""
    require(type(records) is list, 'IMPORT_RECORDS_NOT_LIST')
    identities=set(); origins=set(); names=set()
    for record in records:
        require(type(record) is dict and set(record)==
                {'module','relative_path','origin','file','sha256','object_identity'},
                'IMPORT_RECORD_FIELDS')
        name=record['module']; rel=record['relative_path']
        require(name not in names, 'DUPLICATE_MODULE_NAME')
        names.add(name)
        require(record['object_identity'] not in identities, 'DUPLICATE_MODULE_IDENTITY')
        identities.add(record['object_identity'])
        require(record['origin'] not in origins, 'DUPLICATE_MODULE_ORIGIN')
        origins.add(record['origin'])
        exp_rel=(extensions[name]['relative_path'] if name in extensions
                 else (name.replace('.','/')+'/__init__.py'
                       if name.replace('.','/')+'/__init__.py' in allowed_core
                       else name.replace('.','/')+'.py'))
        require(name in extensions or exp_rel in allowed_core,
                'UNEXPECTED_IMPORTED_MODULE:'+name)
        require(rel==exp_rel, 'MODULE_RELATIVE_PATH:'+name)
        expected_origin=(extensions[name]['canonical_origin'] if name in extensions
                         else ntpath.join(CANONICAL_ROOT,*rel.split('/')))
        require(record['origin']==expected_origin and record['file']==expected_origin,
                'WRONG_IMPORT_ORIGIN:'+name)
        expected_sha=(extensions[name]['sha256'] if name in extensions else allowed_core[rel])
        if rel=='mmd_registry/__init__.py':
            expected_sha=CANONICAL_INIT_NORMALIZED
        require(record['sha256']==expected_sha, 'WRONG_IMPORT_SHA:'+name)
    return len(records)

def collect_loaded_records(modules, root, allowed_core, extensions):
    """Return verified per-module records for actual sys.modules, no removal/spoof."""
    require(set(allowed_core).isdisjoint({v['relative_path'] for v in extensions.values()}),
            'CORE_EXTENSION_OVERLAP')
    records={}; identities=set(); origin_paths=set()
    for name, module in tuple(modules.items()):
        if name!='mmd_registry' and not name.startswith('mmd_registry.'):
            continue
        require(type(module) is ModuleType,'IMPORTED_OBJECT_NOT_MODULE:'+name)
        require(id(module) not in identities,'DUPLICATE_MODULE_OBJECT:'+name)
        identities.add(id(module))
        rel_package=name.replace('.','/')+'/__init__.py'
        rel_module=name.replace('.','/')+'.py'
        rel=rel_package if rel_package in allowed_core else rel_module
        if name in extensions:
            rel=extensions[name]['relative_path']
        elif rel not in allowed_core:
            require(False,'UNEXPECTED_IMPORTED_MODULE:'+name)
        data=exact_file(root,rel)
        actual=sha(data)
        if name in extensions:
            require(actual==extensions[name]['sha256'],'IMPORTED_EXTENSION_SHA:'+name)
        else:
            expected=allowed_core[rel]
            expected=CANONICAL_INIT_NORMALIZED if rel=='mmd_registry/__init__.py' else expected
            require(normalized_sha(data)==expected,'IMPORTED_CORE_SHA:'+name)
        expected_path=Path(root).joinpath(*rel.split('/'))
        expected_abs=os.path.abspath(str(expected_path))
        actual_file=vars(module).get('__file__')
        spec=vars(module).get('__spec__')
        require(isinstance(actual_file,str) and actual_file==expected_abs,
                'WRONG_IMPORT_FILE:'+name)
        require(spec is not None and spec.origin==expected_abs and spec.loader is not None,
                'WRONG_IMPORT_SPEC:'+name)
        require(expected_abs not in origin_paths, 'DUPLICATE_SOURCE_ORIGIN:'+name)
        origin_paths.add(expected_abs)
        if rel.endswith('/__init__.py'):
            require(list(vars(module).get('__path__',()))==[str(expected_path.parent)],
                    'PACKAGE_PATH_DRIFT:'+name)
        records[name]={'relative_path':rel,'sha256':actual,'origin':expected_abs}
    return records

def verify_contract(root:Path, *, manifest_sha:str, loaded_modules=None):
    """Complete source-level check; never executes native verifier or Git."""
    root=Path(root)
    require(str(root)==CANONICAL_ROOT and sys.platform=='win32', 'ACTUAL_CANONICAL_WINDOWS_ONLY')
    b4=exact_file(root,'mmd_registry/mesh_projection_v2.py')
    require(sha(b4)==V2_B4_SHA,'B4_V2_SOURCE_IDENTITY_DRIFT')
    own=exact_file(root,'mmd_registry/cp23_b4_v2_contract_r1.py')
    manifest=exact_file(root,'mmd_registry/cp23_b4_v2_extensions_r1.json')
    require(HEX64.fullmatch(manifest_sha) is not None,'EXPECTED_MANIFEST_SHA_FORMAT')
    doc=json.loads(manifest)
    entries=validate_manifest(doc,contract_sha=sha(own),manifest_sha=manifest_sha,raw_manifest=manifest)
    for item in entries.values():
        require(sha(exact_file(root,item['relative_path']))==item['sha256'],
                'EXTENSION_SOURCE_PIN_DRIFT:'+item['module'])
    historical=historical_pins_from_b4(b4)
    core_result=verify_canonical_core(root,historical)
    loaded_result=None
    if loaded_modules is not None:
        loaded_result=collect_loaded_records(loaded_modules,root,historical,entries)
    return {'contract_revision':CONTRACT_REVISION,'canonical_core':core_result,
            'extensions_verified':len(entries),'loaded_modules_verified':loaded_result,
            'original_verify_core':'UNMODIFIED_UNPINNED_EXTENSION_CLOSURE_HOLD',
            'native_attestation':False}
