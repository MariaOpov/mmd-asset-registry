"""Fail-closed, read-only bridge to the existing verified Registry CLI.

This module never parses/writes PMX and never invokes any write-capable command.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

MAX_OUTPUT = 16_000_000
TIMEOUT_SECONDS = 120
ALLOWED = frozenset({'inspect', 'scan', 'bones'})

class StudioInputError(ValueError):
    """Explicit report of an unusable model or Registry command."""


def inspect_pmx(repo: Path, source: Path, *, runner=None) -> dict[str, Any]:
    repo = Path(repo).resolve()
    try:
        source = Path(source).resolve(strict=True)
    except OSError as exc:
        raise StudioInputError(f'Model does not exist: {type(exc).__name__}') from exc
    if source.suffix.casefold() not in ('.pmx', '.pmd') or not source.is_file():
        raise StudioInputError('Select an existing .pmx or .pmd file.')
    entrypoint = repo / 'check_assets.py'
    if not entrypoint.is_file():
        raise StudioInputError('Verified Registry CLI entrypoint not found.')
    run = runner or _run_readonly
    header = run(entrypoint, repo, 'inspect', source)
    if not isinstance(header, dict) or header.get('status') == 'error':
        return _result(source, header, None, None, 'Header inspection failed; structural checks not run.')
    if source.suffix.casefold() == '.pmd':
        return _result(source, header, None, None, 'PMD header inspection only; no PMD editing or structural scan.')
    scan = run(entrypoint, repo, 'scan', source)
    if not isinstance(scan, dict) or scan.get('status') == 'error' or scan.get('scan_complete') is False:
        return _result(source, header, scan, None, 'Structural scan incomplete; bone inspection blocked.')
    # Projection already exposes bounded bone names from the authoritative scan.
    # Do not rerun a potentially huge bones --json for large models.
    if scan.get('bounded_gui_projection') is True:
        bones = None
    else:
        try:
            bones = run(entrypoint, repo, 'bones', source)
        except (StudioInputError, ValueError):
            bones = None
    return _result(source, header, scan, bones, 'Read-only inspection completed; source was not modified.')


def _result(source: Path, header: dict, scan: dict | None, bones: dict | None, message: str) -> dict:
    # Keep the Registry's authoritative records; frontend handles bounded pagination.
    return {'path': str(source), 'header': header, 'scan': scan, 'bones': bones,
            'message': message, 'mode': 'READ_ONLY', 'source_writes': False}


def _run_readonly(entrypoint: Path, repo: Path, command: str, source: Path) -> dict:
    if command not in ALLOWED:
        raise StudioInputError('GUI-A0 is not authorized to execute writing commands.')
    if command == 'scan':
        args = [sys.executable, '-B', str(Path(__file__).with_name('scan_projection.py')),
                '--repo', str(repo), '--source', str(source)]
    else:
        args = [sys.executable, '-B', str(entrypoint), command, str(source), '--json']
    try:
        completed = subprocess.run(args, cwd=str(repo), capture_output=True,
                                   timeout=TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StudioInputError(f'Registry command did not finish: {type(exc).__name__}') from exc
    if len(completed.stdout) > MAX_OUTPUT:
        raise StudioInputError('Registry JSON exceeds safe GUI-A0 response bound; source not modified.')
    if command == 'scan' and completed.returncode != 0:
        raise StudioInputError('Bounded structural scan failed: ' + completed.stderr.decode('utf-8', errors='replace')[:250])
    try:
        payload = json.loads(completed.stdout.decode('utf-8-sig'))
    except (ValueError, UnicodeDecodeError) as exc:
        raise StudioInputError('Registry did not return valid UTF-8 JSON.') from exc
    if not isinstance(payload, dict):
        raise StudioInputError('Expected a JSON object from Registry.')
    if completed.returncode != 0 and payload.get('status') not in {'error', 'warning'}:
        raise StudioInputError(f'Registry command returned unexpected exit code {completed.returncode}.')
    return payload
