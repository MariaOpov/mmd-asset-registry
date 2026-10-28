"""Creator-P0: read-only SHA/provenance/PMX scan gate, NOT a creation engine.

A manifest assertion is not proof of redistribution permission.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

class TemplateGateError(ValueError):
    pass


def verify_template(manifest_file: Path) -> dict[str, Any]:
    try:
        manifest_file = Path(manifest_file).resolve(strict=True)
        doc = json.loads(manifest_file.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise TemplateGateError('Template manifest cannot be read as UTF-8 JSON.') from exc
    if type(doc) is not dict:
        raise TemplateGateError('Template manifest must be a JSON object.')
    required = ('model_path', 'sha256', 'license_identifier', 'source_reference', 'owner_rights_reviewed')
    if any(key not in doc for key in required):
        raise TemplateGateError('Missing a required template provenance field.')
    if type(doc['model_path']) is not str or not doc['model_path'].strip():
        raise TemplateGateError('model_path must be a non-empty string.')
    if type(doc['sha256']) is not str or len(doc['sha256']) != 64 or any(x not in '0123456789abcdef' for x in doc['sha256']):
        raise TemplateGateError('sha256 must contain exactly 64 lowercase hex characters.')
    if doc['owner_rights_reviewed'] is not True:
        raise TemplateGateError('Owner rights review has not been recorded.')
    for key in ('license_identifier', 'source_reference'):
        if type(doc[key]) is not str or not doc[key].strip() or doc[key].strip().casefold() in {'unknown', 'tbd', 'none', 'pending'}:
            raise TemplateGateError(f'Inconclusive {key}.')
    try:
        model = Path(doc['model_path'])
        if not model.is_absolute():
            model = manifest_file.parent / model
        model = model.resolve(strict=True)
        if model.suffix.casefold() != '.pmx' or not model.is_file():
            raise TemplateGateError('Template must reference an existing PMX file.')
        h = hashlib.sha256()
        with model.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
    except OSError as exc:
        raise TemplateGateError(f'Template file inaccessible: {type(exc).__name__}') from exc
    if h.hexdigest() != doc['sha256']:
        raise TemplateGateError('Template SHA-256 mismatch.')
    return {'status': 'CANDIDATE_FOR_OWNER_REVIEW', 'path': str(model),
            'sha256': h.hexdigest(), 'license_identifier': doc['license_identifier'],
            'source_reference': doc['source_reference'],
            'note': 'Manifest assertions and bytes match only. Does not certify PMX structure, legal rights, export or MMD compatibility.'}


def inspect_template_with_core(manifest_file: Path, repo: Path, *, runner=None) -> dict[str, Any]:
    """Check manifest and existing core PMX structural scan. Never copy/export."""
    from gui_a0.core_adapter import inspect_pmx
    result = verify_template(manifest_file)
    model = inspect_pmx(repo, Path(result['path']), runner=runner)
    scan = model.get('scan') or {}
    result['pmx_scan_status'] = scan.get('status', 'not_run')
    result['pmx_scan_complete'] = scan.get('scan_complete')
    result['status'] = ('STRUCTURAL_CANDIDATE_OWNER_REVIEW_REQUIRED'
                        if scan.get('scan_complete') is True and scan.get('status') in {'ok', 'warning'}
                        else 'HOLD_PMX_STRUCTURE_NOT_CERTIFIED')
    return result
