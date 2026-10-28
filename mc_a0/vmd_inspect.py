"""MC-A0: bounded read-only VMD2 inspector with frame ranges (not playback).

No VMD writer, camera editor, retargeter or animation engine.
"""
from __future__ import annotations
import hashlib
import json
import struct
import sys
from pathlib import Path

MAGIC = b'Vocaloid Motion Data 0002'
SECTIONS = (('bone',111,15),('morph',23,15),('camera',61,0),('light',28,0),('shadow',9,0))
MAX_SIZE = 128*1024*1024
MAX_KEYS = 1_000_000
MAX_SAMPLES = 120

class VmdFormatError(ValueError):
    pass


def inspect_vmd_bytes(data: bytes) -> dict:
    if type(data) is not bytes:
        raise TypeError('VMD input must be bytes')
    if len(data) > MAX_SIZE:
        raise VmdFormatError('VMD exceeds the inspector size bound')
    if len(data) < 50:
        raise VmdFormatError('Truncated VMD2 header')
    if data[:30].rstrip(b'\x00') != MAGIC:
        raise VmdFormatError('Only VMD2 structure is supported')
    try:
        name = data[30:50].split(b'\x00',1)[0].decode('cp932')
    except UnicodeDecodeError as exc:
        raise VmdFormatError('Model name is not valid CP932') from exc
    offset = 50; counts = {}; ranges = {}; warnings = []
    for section, size, frame_at in SECTIONS:
        if offset == len(data):
            warnings.append('Later fixed-size VMD sections are absent')
            break
        if offset + 4 > len(data):
            raise VmdFormatError(f'Truncated {section} count')
        count = struct.unpack_from('<I', data, offset)[0]
        offset += 4
        if count > MAX_KEYS or size * count > len(data) - offset:
            raise VmdFormatError(f'Truncated or impossible {section} section')
        counts[section] = count
        # Record min/max frame and evenly distributed sample positions without
        # allocating record objects or retaining asset/motion content.
        min_frame = None; max_frame = None; samples = []
        stride = max(1, (count + MAX_SAMPLES - 1)//MAX_SAMPLES)
        for i in range(count):
            f = struct.unpack_from('<I', data, offset + i*size + frame_at)[0]
            min_frame = f if min_frame is None else min(min_frame, f)
            max_frame = f if max_frame is None else max(max_frame, f)
            if i % stride == 0 and len(samples) < MAX_SAMPLES:
                samples.append(f)
        ranges[section] = {'first_frame': min_frame, 'last_frame': max_frame,
                           'sample_frames': sorted(set(samples)), 'sample_only': count > len(samples)}
        offset += count * size
    if len(counts) == len(SECTIONS):
        if offset == len(data):
            warnings.append('Optional IK/show section not present')
        else:
            if offset+4 > len(data):
                raise VmdFormatError('Truncated IK/show count')
            n = struct.unpack_from('<I',data,offset)[0]; offset += 4
            if n > MAX_KEYS:
                raise VmdFormatError('Excessive IK/show count')
            for _ in range(n):
                if offset+9 > len(data):
                    raise VmdFormatError('Truncated IK/show frame')
                item_count = struct.unpack_from('<I',data,offset+5)[0]; offset += 9
                if item_count > MAX_KEYS or item_count*21 > len(data)-offset:
                    raise VmdFormatError('Truncated IK toggles')
                offset += item_count*21
            counts['ik_show'] = n
    if offset != len(data):
        warnings.append(f'{len(data)-offset} trailing bytes not interpreted')
    return {'status':'warning' if warnings else 'ok','format':'VMD2',
            'model_name':name,'counts':counts,'frame_ranges':ranges,
            'warnings':warnings,'bytes_consumed':offset,'file_size':len(data),
            'sha256':hashlib.sha256(data).hexdigest(),
            'scope':'READ_ONLY_STRUCTURE_NOT_PLAYBACK_OR_CAMERA_CERTIFICATION'}


def inspect_vmd_file(file_path: Path) -> dict:
    try:
        path = Path(file_path).resolve(strict=True)
        if path.suffix.casefold() != '.vmd' or not path.is_file():
            raise VmdFormatError('Select an existing .vmd file.')
        if path.stat().st_size > MAX_SIZE:
            raise VmdFormatError('VMD exceeds the inspector size bound')
        # Reading immutable snapshot prevents inconsistencies within this inspection.
        data = path.read_bytes()
    except OSError as exc:
        raise VmdFormatError(f'Cannot open VMD file: {type(exc).__name__}') from exc
    return {'path':str(path), **inspect_vmd_bytes(data)}


def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    if len(args)!=1:
        print('Usage: python -m mc_a0.vmd_inspect motion.vmd',file=sys.stderr)
        return 2
    try:
        print(json.dumps(inspect_vmd_file(Path(args[0])),ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError) as exc:
        print(f'MC_A0=HOLD {type(exc).__name__}: {exc}',file=sys.stderr)
        return 3
if __name__=='__main__': raise SystemExit(main())
