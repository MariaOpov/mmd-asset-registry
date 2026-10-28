"""GUI-A2-P0: bounded, static read-only PMX mesh projection.

The *existing* Registry mmd_registry.pmx.reader.load_pmx is the only PMX parser.
No PMX writer, network fetch, texture read, animation or geometry mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

PIN = '35b3a30962465a759c15fcd9780e8c47022b1928'
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_VERTICES = 100_000
MAX_TRIANGLES = 150_000
MAX_PAYLOAD_BYTES = 11_000_000


class PreviewGateError(ValueError):
    pass


def hash_source(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def validate_source(path: Path) -> Path:
    if type(path) is not Path:
        path = Path(path)
    if not path.is_absolute() or path.suffix.casefold() != '.pmx':
        raise PreviewGateError('A local absolute .pmx path is required.')
    path = path.resolve(strict=True)
    if not path.is_file():
        raise PreviewGateError('Source is not a file.')
    size = path.stat().st_size
    if size <= 0 or size > MAX_SOURCE_BYTES:
        raise PreviewGateError('Model is outside the bounded 32 MiB preview input limit.')
    return path


# Core is frozen to v0.9.5.12; Studio additions may reside in the same
# committed Git worktree. Never treat a new HEAD alone as a Core change.
STUDIO_LANE_PREFIXES = ('gui_a0/', 'creator_p0/', 'mc_a0/')


def _git_checked(repo: Path, *args: str) -> bytes:
    """Bounded local Git reads only, with no network or repository mutations."""
    run = subprocess.run(
        ['git', '-C', str(repo), *args], capture_output=True,
        timeout=15, check=False,
    )
    if run.returncode:
        raise PreviewGateError('Local Core identity check failed: ' + args[0])
    return run.stdout


def verify_core(repo: Path) -> None:
    """Accept pinned Core or a clean descendant adding only Studio lane files.

    A post-merge Studio worktree no longer has HEAD==PIN. The complete diff
    from PIN to HEAD must still be limited to Studio-owned directories,
    protecting all original Registry Core files. Uncommitted edits are denied.
    """
    repo = Path(repo).resolve(strict=True)
    if not (repo / 'check_assets.py').is_file():
        raise PreviewGateError('Verified Core entrypoint is missing.')
    top = Path(_git_checked(repo, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve(strict=True)
    if top != repo:
        raise PreviewGateError('Core path must be the Git worktree root.')
    head = _git_checked(repo, 'rev-parse', 'HEAD').decode('ascii').strip()
    if _git_checked(repo, 'status', '--porcelain=v1', '--untracked-files=all'):
        raise PreviewGateError('Core worktree must be clean for viewport generation.')
    if head == PIN:
        return
    _git_checked(repo, 'merge-base', '--is-ancestor', PIN, head)
    modified = _git_checked(repo, 'diff', '--name-only', '-z', '--no-renames', PIN, head, '--')
    try:
        changed = [item.decode('utf-8') for item in modified.split(b'\x00') if item]
    except UnicodeDecodeError as exc:
        raise PreviewGateError('Non-UTF-8 Git path in Core verification.') from exc
    if not changed or any(not path.startswith(STUDIO_LANE_PREFIXES) for path in changed):
        raise PreviewGateError('Committed changes outside Studio lanes; Core pin not certified.')


def _f(value: Any) -> float:
    num = float(value)
    if not math.isfinite(num):
        raise PreviewGateError('Non-finite geometry or material value.')
    return num


def build_projection(document: Any, source: Path, sha: str) -> dict[str, Any]:
    """Pure projection of the official parsed document into WebGL-safe arrays."""
    vertices = document.geometry.vertices
    indices = document.geometry.surface_indices
    if not 0 < len(vertices) <= MAX_VERTICES:
        raise PreviewGateError('Vertex count outside static preview limit.')
    if len(indices) % 3 or not 0 < len(indices) <= MAX_TRIANGLES * 3:
        raise PreviewGateError('Triangle count outside static preview limit.')
    if any(type(i) is not int or i < 0 or i >= len(vertices) for i in indices):
        raise PreviewGateError('Invalid surface index in source model.')
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    bounds_min = [math.inf] * 3
    bounds_max = [-math.inf] * 3
    for v in vertices:
        if len(v.position) != 3 or len(v.normal) != 3:
            raise PreviewGateError('Invalid vertex vector dimensions.')
        for axis in range(3):
            coord = _f(v.position[axis])
            positions.append(coord)
            normals.append(_f(v.normal[axis]))
            bounds_min[axis] = min(bounds_min[axis], coord)
            bounds_max[axis] = max(bounds_max[axis], coord)
        uvs.extend([_f(v.uv[0]), _f(v.uv[1])])
    groups = []
    start = 0
    for index, mat in enumerate(document.materials):
        count = mat.surface_index_count
        if type(count) is not int or count < 0 or count % 3:
            raise PreviewGateError('Invalid material triangle partition.')
        if start + count > len(indices):
            raise PreviewGateError('Material partition exceeds triangle count.')
        color = [_f(x) for x in mat.diffuse[:3]]
        if mat.sphere_mode not in (0, 1, 2, 3):
            raise PreviewGateError('Unknown PMX sphere mode.')
        if mat.toon_reference_mode not in ('texture', 'shared'):
            raise PreviewGateError('Unknown PMX toon reference mode.')
        for ref in (mat.texture_index, mat.sphere_texture_index,
                    mat.toon_reference_index if mat.toon_reference_mode == 'texture' else -1):
            if type(ref) is not int or ref < -1 or ref >= len(document.texture_paths):
                raise PreviewGateError('Material texture reference outside document bounds.')
        if mat.toon_reference_mode == 'shared' and not (0 <= mat.toon_reference_index <= 9):
            raise PreviewGateError('Shared toon reference outside PMX range.')
        if count:
            groups.append({'start': start, 'count': count, 'color': [max(.0, min(1.0, c)) for c in color],
                           'material_index': index, 'texture_index': mat.texture_index,
                           'sphere_texture_index': mat.sphere_texture_index,
                           'sphere_mode': mat.sphere_mode,
                           'toon_reference_mode': mat.toon_reference_mode,
                           'toon_texture_index': (mat.toon_reference_index if mat.toon_reference_mode == 'texture' else -1),
                           'toon_shared_index': (mat.toon_reference_index if mat.toon_reference_mode == 'shared' else -1),
                           'ambient': [max(.0, min(1.0, _f(c))) for c in mat.ambient],
                           'specular': [max(.0, min(1.0, _f(c))) for c in mat.specular],
                           'specular_strength': max(.0, min(128.0, _f(mat.specular_strength))),
                           'drawing_flags': mat.drawing_flags,
                           'alpha': max(.0, min(1.0, _f(mat.diffuse[3])))})
        start += count
    if start != len(indices):
        raise PreviewGateError('Material partitions do not cover all triangles.')
    return {
        'status': 'ok', 'scope': 'STATIC_TEXTURE_PREVIEW_NO_SKINNING_NO_MOTION',
        'source_path': str(source), 'source_sha256': sha,
        'name': document.model_info.local_name,
        'vertex_count': len(vertices), 'triangle_count': len(indices) // 3,
        'positions': positions, 'normals': normals, 'uvs': uvs, 'indices': list(indices),
        'texture_paths': list(document.texture_paths),
        'groups': groups, 'bounds': {'min': bounds_min, 'max': bounds_max},
        'source_writes': False,
    }


def export_preview(repo: Path, source: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    verify_core(repo)
    source = validate_source(source)
    initial_stat = source.stat()
    before = hash_source(source)
    # The pinned Registry reader is authoritative; never implement a second parser.
    sys.path.insert(0, str(repo))
    from mmd_registry.pmx.reader import load_pmx
    from mmd_registry import __version__
    if __version__ != '0.9.5.12':
        raise PreviewGateError('Core version mismatch.')
    result = build_projection(load_pmx(source), source, before)
    after = hash_source(source)
    final_stat = source.stat()
    if before != after or initial_stat.st_size != final_stat.st_size or initial_stat.st_mtime_ns != final_stat.st_mtime_ns:
        raise PreviewGateError('Source changed during projection; preview refused.')
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', type=Path, required=True)
    ap.add_argument('--source', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        result = export_preview(args.repo, args.source)
        data = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
        if len(data) > MAX_PAYLOAD_BYTES:
            raise PreviewGateError('Static mesh projection exceeds 11 MB transfer bound.')
        sys.stdout.buffer.write(data)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'VIEWPORT_HOLD={type(exc).__name__}: {exc}', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
