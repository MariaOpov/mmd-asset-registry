"""Read-only Studio R1 operations shared by Qt and optional browser host."""
from __future__ import annotations
from pathlib import Path
from gui_a0.core_adapter import inspect_pmx, StudioInputError
from mc_a0.vmd_inspect import inspect_vmd_file
from creator_p0.template_gate import inspect_template_with_core
from gui_a0.mesh_adapter import preview_mesh

KINDS = frozenset({'model', 'motion', 'template', 'preview'})


def dispatch(kind: str, path: str, repo: Path) -> dict:
    if kind not in KINDS:
        raise StudioInputError('Unknown R1 operation type.')
    if type(path) is not str or not path.strip() or len(path) > 4096:
        raise StudioInputError('Select one existing local model, motion or template path.')
    item = Path(path.strip())
    if kind == 'model':
        return {'kind':'model', 'data': inspect_pmx(repo, item)}
    if kind == 'preview':
        return {'kind':'preview', 'data':preview_mesh(repo, item)}
    if kind == 'motion':
        return {'kind':'motion', 'data': inspect_vmd_file(item)}
    return {'kind':'template', 'data': inspect_template_with_core(item, repo)}
