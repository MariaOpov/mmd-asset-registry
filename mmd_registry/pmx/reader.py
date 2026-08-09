"""Complete PMX document reading independent from scanner and CLI layers."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import PmxDocument
from mmd_registry.pmx.sections.bones import read_pmx_bones
from mmd_registry.pmx.sections.display_frames import read_pmx_display_frames
from mmd_registry.pmx.sections.geometry import read_pmx_geometry
from mmd_registry.pmx.sections.header import read_pmx_header
from mmd_registry.pmx.sections.joints import read_pmx_joints
from mmd_registry.pmx.sections.materials import read_pmx_materials
from mmd_registry.pmx.sections.morphs import read_pmx_morphs
from mmd_registry.pmx.sections.rigid_bodies import read_pmx_rigid_bodies
from mmd_registry.pmx.sections.soft_bodies import read_pmx_soft_bodies
from mmd_registry.pmx.sections.textures import read_pmx_textures


def read_pmx_document(reader: BinaryReader) -> PmxDocument:
    """Read one complete PMX document from an existing bounded reader."""

    if not isinstance(reader, BinaryReader):
        raise TypeError("reader must be a BinaryReader instance.")

    header_result = read_pmx_header(reader)
    header = header_result.header
    geometry = read_pmx_geometry(reader, header=header)
    texture_paths = read_pmx_textures(reader, header=header)
    materials = read_pmx_materials(
        reader,
        header=header,
        texture_count=len(texture_paths),
        surface_index_count=len(geometry.surface_indices),
    )
    bones = read_pmx_bones(reader, header=header)
    morphs = read_pmx_morphs(
        reader,
        header=header,
        vertex_count=len(geometry.vertices),
        bone_count=len(bones),
        material_count=len(materials),
    )
    display_frames = read_pmx_display_frames(
        reader,
        header=header,
        bone_count=len(bones),
        morph_count=len(morphs),
    )
    rigid_bodies = read_pmx_rigid_bodies(
        reader,
        header=header,
        bone_count=len(bones),
    )
    joints = read_pmx_joints(
        reader,
        header=header,
        rigid_body_count=len(rigid_bodies),
    )
    soft_bodies = read_pmx_soft_bodies(
        reader,
        header=header,
        material_count=len(materials),
        rigid_body_count=len(rigid_bodies),
        vertex_count=len(geometry.vertices),
    )
    trailing_data = reader.read_exact(
        reader.remaining,
        "PMX trailing data",
    )

    return PmxDocument(
        header=header,
        model_info=header_result.model_info,
        geometry=geometry,
        texture_paths=texture_paths,
        materials=materials,
        bones=bones,
        morphs=morphs,
        display_frames=display_frames,
        rigid_bodies=rigid_bodies,
        joints=joints,
        soft_bodies=soft_bodies,
        trailing_data=trailing_data,
    )


def load_pmx(source: str | Path | BinaryIO) -> PmxDocument:
    """Load one complete PMX document from a path or binary stream."""

    if hasattr(source, "read"):
        return read_pmx_document(
            BinaryReader(source, format_name="PMX")  # type: ignore[arg-type]
        )

    path = Path(source)
    with path.open("rb") as file:
        return read_pmx_document(BinaryReader(file, format_name="PMX"))
