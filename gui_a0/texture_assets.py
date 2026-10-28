"""Constrained, read-only local PMX preview texture resolution and conversion.

Never accepts a path from an HTTP request. The caller supplies paths declared
by the already validated PMX document; images must remain under its directory.
"""
from __future__ import annotations

import hashlib
import mimetypes
import struct
import zlib
from pathlib import Path

MAX_TEXTURE_COUNT = 128
MAX_TEXTURE_FILE_BYTES = 24 * 1024 * 1024
MAX_TEXTURE_PIXELS = 4096 * 4096
ALLOWED_SUFFIXES = frozenset({'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tga'})

class TextureHold(ValueError):
    pass


def resolve_declared_texture(source: Path, declaration: str) -> Path | None:
    if not isinstance(declaration, str) or not declaration or len(declaration) > 512:
        return None
    # Paths in PMX commonly use Windows separators, even on non-Windows QA.
    relative = declaration.replace('\\', '/')
    parts = relative.split('/')
    if any(p in ('', '.', '..') or ':' in p or '\x00' in p for p in parts):
        return None
    if relative.startswith('/') or relative.startswith('//'):
        return None
    candidate = source.parent.joinpath(*parts)
    try:
        parent = source.parent.resolve(strict=True)
        candidate = candidate.resolve(strict=True)
        size = candidate.stat().st_size
    except OSError:
        return None
    if not candidate.is_relative_to(parent) or not candidate.is_file():
        return None
    if candidate.suffix.casefold() not in ALLOWED_SUFFIXES:
        return None
    if not 0 < size <= MAX_TEXTURE_FILE_BYTES:
        return None
    return candidate


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack('>I', len(data)) + payload + struct.pack('>I', zlib.crc32(payload) & 0xffffffff)


def tga_to_png(data: bytes) -> bytes:
    """Decode only bounded, true-color 24/32bpp TGA type 2 or 10."""
    if len(data) < 18 or len(data) > MAX_TEXTURE_FILE_BYTES:
        raise TextureHold('TGA length outside safe bounds.')
    id_length, cmap_type, image_type = data[0], data[1], data[2]
    width, height, depth, desc = struct.unpack_from('<HHBB', data, 12)
    if cmap_type != 0 or image_type not in (2, 10) or depth not in (24, 32):
        raise TextureHold('Unsupported TGA encoding (requires uncompressed/RLE 24/32bpp truecolor).')
    if width <= 0 or height <= 0 or width > 4096 or height > 4096 or width*height > MAX_TEXTURE_PIXELS:
        raise TextureHold('TGA dimensions exceed safe bounds.')
    channels = depth // 8
    off = 18 + id_length
    count = width * height
    raw = bytearray(count * channels)
    pos = 0
    if image_type == 2:
        end = off + len(raw)
        if end > len(data):
            raise TextureHold('TGA data truncated.')
        raw[:] = data[off:end]
    else:
        while pos < count:
            if off >= len(data):
                raise TextureHold('TGA RLE packet truncated.')
            head = data[off]; off += 1
            n = (head & 127) + 1
            if pos + n > count:
                raise TextureHold('TGA RLE packet exceeds pixel count.')
            length = channels if head & 128 else channels*n
            if off + length > len(data):
                raise TextureHold('TGA RLE pixels truncated.')
            blob = data[off:off+length]; off += length
            if head & 128:
                raw[pos*channels:(pos+n)*channels] = blob*n
            else:
                raw[pos*channels:(pos+n)*channels] = blob
            pos += n
    origin_top = bool(desc & 0x20)
    origin_right = bool(desc & 0x10)
    color_type = 6 if channels == 4 else 2
    scanlines = bytearray()
    stride = width * channels
    for y in range(height):
        source_y = y if origin_top else height - 1 - y
        row = raw[source_y*stride:(source_y+1)*stride]
        if origin_right:
            row = b''.join(row[i:i+channels] for i in range(stride-channels, -1, -channels))
        out = bytearray(stride)
        out[0::channels] = row[2::channels]  # BGR(A) -> RGB(A)
        out[1::channels] = row[1::channels]
        out[2::channels] = row[0::channels]
        if channels == 4:
            out[3::channels] = row[3::channels]
        scanlines.append(0)  # PNG filter none
        scanlines.extend(out)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = struct.pack('>IIBBBBB', width, height, 8, color_type, 0, 0, 0)
    return sig + _png_chunk(b'IHDR', ihdr) + _png_chunk(b'IDAT', zlib.compress(scanlines, 6)) + _png_chunk(b'IEND', b'')


def open_texture_bytes(path: Path) -> tuple[str, bytes]:
    if not path.is_file() or path.suffix.casefold() not in ALLOWED_SUFFIXES:
        raise TextureHold('Texture is not an allowed regular file.')
    if not 0 < path.stat().st_size <= MAX_TEXTURE_FILE_BYTES:
        raise TextureHold('Texture file size bound exceeded.')
    data = path.read_bytes()
    suffix = path.suffix.casefold()
    if suffix == '.tga':
        return 'image/png', tga_to_png(data)
    kinds = {
        '.png': ('image/png', data.startswith(b'\x89PNG\r\n\x1a\n')),
        '.jpg': ('image/jpeg', data.startswith(b'\xff\xd8\xff')),
        '.jpeg': ('image/jpeg', data.startswith(b'\xff\xd8\xff')),
        '.bmp': ('image/bmp', data.startswith(b'BM')),
        '.webp': ('image/webp', len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP'),
    }
    mime, valid = kinds[suffix]
    if not valid:
        raise TextureHold('Texture signature mismatch.')
    return mime, data
