"""Session-scoped local QA PNG evidence writer; never writes source/model paths.

Only the browser host invokes this on an explicit same-origin user-click POST.
No user-provided destination path or filename is accepted. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import secrets
import struct
from datetime import datetime, timezone
import zlib

PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_PNG_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 8_000_000
KINDS = frozenset({'VIEWPORT', 'ALPHA_AB'})

class QASaveHold(ValueError):
    pass


def verify_png(data: bytes) -> tuple[int, int]:
    if not isinstance(data, bytes) or len(data) < 45 or len(data) > MAX_PNG_BYTES:
        raise QASaveHold('PNG_SIZE_BOUND')
    if not data.startswith(PNG_SIGNATURE):
        raise QASaveHold('PNG_SIGNATURE_INVALID')
    offset = 8
    chunks = 0
    width = height = 0
    seen_ihdr = seen_idat = seen_iend = False
    while offset < len(data):
        if chunks >= 2048 or offset + 12 > len(data):
            raise QASaveHold('PNG_CHUNK_BOUND')
        n = struct.unpack_from('>I', data, offset)[0]
        if n > MAX_PNG_BYTES or offset + 12 + n > len(data):
            raise QASaveHold('PNG_CHUNK_SIZE_INVALID')
        chunk_type = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + n]
        crc = struct.unpack_from('>I', data, offset + 8 + n)[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != crc:
            raise QASaveHold('PNG_CRC_INVALID')
        if chunks == 0:
            if chunk_type != b'IHDR' or n != 13:
                raise QASaveHold('PNG_IHDR_INVALID')
            width, height, depth, color, comp, filt, interlace = struct.unpack('>IIBBBBB', payload)
            if (width == 0 or height == 0 or width * height > MAX_IMAGE_PIXELS or
                    depth != 8 or color not in (2, 6) or comp != 0 or filt != 0 or interlace != 0):
                raise QASaveHold('PNG_UNSUPPORTED_FORMAT')
            seen_ihdr = True
        if chunk_type == b'IDAT':
            seen_idat = True
        if chunk_type == b'IEND':
            if n != 0 or offset + 12 != len(data):
                raise QASaveHold('PNG_IEND_INVALID')
            seen_iend = True
            break
        chunks += 1
        offset += 12 + n
    if not (seen_ihdr and seen_idat and seen_iend):
        raise QASaveHold('PNG_REQUIRED_CHUNKS_MISSING')
    return width, height


def save_png(folder: Path, data: bytes, kind: str) -> dict[str, object]:
    if kind not in KINDS:
        raise QASaveHold('QA_KIND_INVALID')
    width, height = verify_png(data)
    now = datetime.now(timezone.utc)
    filename = f'MMD_CP16F_{kind}_{now:%Y%m%dT%H%M%SZ}_{secrets.token_hex(5)}.png'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / filename
    with target.open('xb') as file:
        file.write(data)
    sha = hashlib.sha256(data).hexdigest()
    record = {
        'result': 'PNG_SAVED_TO_EVIDENCE', 'checkpoint': 'CP16F',
        'kind': kind, 'filename': filename, 'evidence_png': str(target),
        'sha256': sha, 'size_bytes': len(data), 'width': width, 'height': height,
        'time_utc': now.isoformat(), 'pmx_source_modified': False,
        'mmd_parity': 'NOT_VERIFIED'
    }
    (folder / (filename + '.json')).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    with (folder / 'CP16F_GUI_EVIDENCE.txt').open('a', encoding='utf-8') as f:
        f.write(f"RESULT=PNG_SAVED_TO_EVIDENCE\nKIND={kind}\nEVIDENCE_PNG={target}\nSHA256={sha}\nSIZE_BYTES={len(data)}\nNO_GIT_OR_PMX_OR_TEXTURE_WRITES=TRUE\n\n")
    return record
