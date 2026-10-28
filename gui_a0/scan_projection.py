"""Bounded GUI projection of authoritative PMX structural scanner.

Only import/use mmd_registry.model_scanning from an owner-pinned verified core.
Never instantiate a PMX writer, serialize morph offsets, or mutate source.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

MAX_ROWS = 200
MAX_NAME_CHARS = 256
MAX_DIAGNOSTICS = 20
MAX_DIAGNOSTIC_CHARS = 400
MAX_JSON_BYTES = 1_000_000


def _short(value, limit=MAX_NAME_CHARS):
    return str(value if value is not None else '')[:limit]


def _list_projection(records, *, total):
    output = []
    for i, record in enumerate(records[:MAX_ROWS]):
        output.append({
            'index': i,
            'local_name': _short(getattr(record, 'local_name', '')),
            'universal_name': _short(getattr(record, 'universal_name', '')),
        })
    return output, {
        'total': total if isinstance(total, int) and total >= 0 else len(records),
        'returned': len(output),
        'offset': 0,
        'has_more': (total if isinstance(total, int) and total >= 0 else len(records)) > len(output),
        'scope': 'first_rows_only',
    }


def _diagnostics(lines):
    return [_short(s, MAX_DIAGNOSTIC_CHARS) for s in lines[:MAX_DIAGNOSTICS]]


def project_scan(scan):
    """Keep authoritative summary and bounded preview rows, never offset arrays."""
    materials, mp = _list_projection(scan.materials, total=scan.material_count)
    bones, bp = _list_projection(scan.bones, total=scan.bone_count)
    morphs, xp = _list_projection(scan.morphs, total=scan.morph_count)
    info = scan.model_info
    return {
        'status': scan.status,
        'scan_complete': scan.scan_complete,
        'version': scan.version,
        'encoding': scan.encoding,
        'model_info': {'local_name': _short(getattr(info, 'local_name', '')),
                       'universal_name': _short(getattr(info, 'universal_name', ''))} if info else None,
        'section_summary': scan.section_summary.to_dict() if scan.section_summary else None,
        'vertex_count': scan.vertex_count,
        'material_count': scan.material_count,
        'bone_count': scan.bone_count,
        'morph_count': scan.morph_count,
        'texture_count': scan.texture_count,
        'materials': materials,
        'bones': bones,
        'morphs': morphs,
        'texture_paths': [_short(s) for s in scan.texture_paths[:40]],
        'errors': _diagnostics(scan.errors),
        'warnings': _diagnostics(scan.warnings),
        'row_windows': {'materials': mp, 'bones': bp, 'morphs': xp},
        'bounded_gui_projection': True,
        'source_writes': False,
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--source',type=Path,required=True)
    a=p.parse_args(argv)
    repo=a.repo.resolve()
    if not (repo/'check_assets.py').is_file():
        print('Verified Registry entrypoint missing',file=sys.stderr)
        return 3
    sys.path.insert(0,str(repo))
    from mmd_registry.model_scanning import scan_pmx_structure
    scan=scan_pmx_structure(a.source.resolve(strict=True))
    output=json.dumps(project_scan(scan),ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(output)>MAX_JSON_BYTES:
        print('Bounded GUI projection still exceeds safe limit',file=sys.stderr)
        return 3
    sys.stdout.buffer.write(output)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
