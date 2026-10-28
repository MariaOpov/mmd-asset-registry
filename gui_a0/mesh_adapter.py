"""Read-only bounded subprocess to the pinned PMX mesh projection."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from gui_a0.core_adapter import StudioInputError

MAX_JSON_BYTES = 11_000_000


def preview_mesh(repo: Path, source: Path) -> dict:
    source = Path(source)
    if not source.is_absolute() or source.suffix.casefold() != '.pmx':
        raise StudioInputError('Viewport requires one local absolute PMX path.')
    script = Path(__file__).with_name('mesh_projection.py')
    try:
        completed = subprocess.run([sys.executable, '-B', str(script), '--repo', str(repo),
                                    '--source', str(source)], cwd=str(repo), capture_output=True,
                                   timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StudioInputError(f'Viewport projection failed: {type(exc).__name__}') from exc
    if completed.returncode != 0:
        raise StudioInputError('Viewport projection HOLD: '+ completed.stderr.decode('utf-8',errors='replace')[:350])
    if len(completed.stdout) > MAX_JSON_BYTES:
        raise StudioInputError('Mesh response exceeds 11 MB safety bound.')
    try:
        data = json.loads(completed.stdout.decode('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise StudioInputError('Invalid bounded mesh response.') from exc
    if type(data) is not dict or data.get('source_writes') is not False:
        raise StudioInputError('Unexpected projection contract.')
    return data
