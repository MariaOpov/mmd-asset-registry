"""Reusable generated PMX fixtures for complete round-trip tests."""

from __future__ import annotations

from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_bone_morph_offset,
    build_pmx_display_frame,
    build_pmx_display_frame_element,
    build_pmx_flip_morph_offset,
    build_pmx_group_morph_offset,
    build_pmx_ik_link,
    build_pmx_impulse_morph_offset,
    build_pmx_joint,
    build_pmx_material,
    build_pmx_material_morph_offset,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_soft_body,
    build_pmx_soft_body_anchor,
    build_pmx_structure,
    build_pmx_uv_morph_offset,
    build_pmx_vertex_morph_offset,
)


def _build_bones(*, encoding_flag: int, index_size: int) -> tuple[bytes, ...]:
    """Build root and fully flag-controlled IK bones."""

    return (
        build_pmx_bone(
            local_name="全ての親",
            universal_name="Root",
            encoding_flag=encoding_flag,
            bone_index_size=index_size,
        ),
        build_pmx_bone(
            local_name="ＩＫ",
            universal_name="IK",
            parent_bone_index=0,
            tail_bone_index=0,
            inherit_rotation=True,
            inherit_translation=True,
            inherit_parent_bone_index=0,
            inherit_weight=0.25,
            fixed_axis=(1.0, 0.0, 0.0),
            local_axes=((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
            external_parent_key=7,
            ik_target_bone_index=0,
            ik_loop_count=8,
            ik_angle_limit=0.75,
            ik_links=(
                build_pmx_ik_link(
                    angle_limit_flag=1,
                    bone_index_size=index_size,
                ),
            ),
            encoding_flag=encoding_flag,
            bone_index_size=index_size,
        ),
    )


def _build_materials(
    *,
    encoding_flag: int,
    index_size: int,
) -> tuple[bytes, ...]:
    """Build materials covering texture and shared-toon reference modes."""

    return (
        build_pmx_material(
            local_name="材質",
            universal_name="Body Material",
            drawing_flags=0x1F,
            texture_index=0,
            sphere_texture_index=1,
            sphere_mode=2,
            toon_reference_mode=0,
            toon_reference_index=2,
            memo="round-trip material",
            surface_index_count=3,
            encoding_flag=encoding_flag,
            texture_index_size=index_size,
        ),
        build_pmx_material(
            local_name="補助材質",
            universal_name="Auxiliary Material",
            toon_reference_mode=1,
            toon_reference_index=9,
            surface_index_count=0,
            encoding_flag=encoding_flag,
            texture_index_size=index_size,
        ),
    )


def _build_morphs(
    *,
    version: float,
    encoding_flag: int,
    vertex_index_size: int,
    material_index_size: int,
    bone_index_size: int,
    morph_index_size: int,
    rigid_body_index_size: int,
) -> tuple[bytes, ...]:
    """Build every morph type supported by the selected PMX version."""

    definitions: list[tuple[str, int, bytes]] = [
        (
            "グループ",
            0,
            build_pmx_group_morph_offset(
                morph_index=1,
                morph_index_size=morph_index_size,
            ),
        ),
        (
            "頂点",
            1,
            build_pmx_vertex_morph_offset(vertex_index_size=vertex_index_size),
        ),
        (
            "ボーン",
            2,
            build_pmx_bone_morph_offset(bone_index_size=bone_index_size),
        ),
    ]
    for morph_type, name in enumerate(
        ("UV", "追加UV1", "追加UV2", "追加UV3", "追加UV4"),
        start=3,
    ):
        definitions.append(
            (
                name,
                morph_type,
                build_pmx_uv_morph_offset(
                    vertex_index_size=vertex_index_size,
                ),
            )
        )
    definitions.append(
        (
            "材質",
            8,
            build_pmx_material_morph_offset(
                material_index_size=material_index_size,
            ),
        )
    )
    if version == 2.1:
        definitions.extend(
            (
                (
                    "フリップ",
                    9,
                    build_pmx_flip_morph_offset(
                        morph_index=1,
                        morph_index_size=morph_index_size,
                    ),
                ),
                (
                    "インパルス",
                    10,
                    build_pmx_impulse_morph_offset(
                        rigid_body_index_size=rigid_body_index_size,
                    ),
                ),
            )
        )

    return tuple(
        build_pmx_morph(
            local_name=name,
            universal_name=f"Morph {morph_type}",
            panel=morph_type % 5,
            morph_type=morph_type,
            offsets=(offset,),
            encoding_flag=encoding_flag,
        )
        for name, morph_type, offset in definitions
    )


def _build_display_frames(
    *,
    encoding_flag: int,
    bone_index_size: int,
    morph_index_size: int,
) -> tuple[bytes, ...]:
    """Build one ordered frame containing bone and morph references."""

    return (
        build_pmx_display_frame(
            local_name="表示枠",
            universal_name="Display Frame",
            special_flag=1,
            elements=(
                build_pmx_display_frame_element(
                    target_type=0,
                    target_index=0,
                    bone_index_size=bone_index_size,
                    morph_index_size=morph_index_size,
                ),
                build_pmx_display_frame_element(
                    target_type=1,
                    target_index=1,
                    bone_index_size=bone_index_size,
                    morph_index_size=morph_index_size,
                ),
            ),
            encoding_flag=encoding_flag,
        ),
    )


def _build_rigid_bodies(
    *,
    encoding_flag: int,
    index_size: int,
) -> tuple[bytes, ...]:
    """Build bone-bound and unbound rigid bodies."""

    return (
        build_pmx_rigid_body(
            local_name="剛体A",
            universal_name="Rigid Body A",
            bone_index=0,
            shape=1,
            physics_mode=1,
            encoding_flag=encoding_flag,
            bone_index_size=index_size,
        ),
        build_pmx_rigid_body(
            local_name="剛体B",
            universal_name="Rigid Body B",
            bone_index=-1,
            shape=2,
            physics_mode=2,
            encoding_flag=encoding_flag,
            bone_index_size=index_size,
        ),
    )


def _build_joints(
    *,
    version: float,
    encoding_flag: int,
    index_size: int,
) -> tuple[bytes, ...]:
    """Build the PMX 2.0 joint or all PMX 2.1 joint variants."""

    joint_types = range(6) if version == 2.1 else range(1)
    return tuple(
        build_pmx_joint(
            local_name=f"ジョイント{joint_type}",
            universal_name=f"Joint {joint_type}",
            joint_type=joint_type,
            rigid_body_a_index=0,
            rigid_body_b_index=1,
            encoding_flag=encoding_flag,
            rigid_body_index_size=index_size,
        )
        for joint_type in joint_types
    )


def _build_soft_bodies(
    *,
    version: float,
    encoding_flag: int,
    vertex_index_size: int,
    material_index_size: int,
    rigid_body_index_size: int,
) -> tuple[bytes, ...]:
    """Build one complete PMX 2.1 soft body when the section exists."""

    if version == 2.0:
        return ()

    return (
        build_pmx_soft_body(
            local_name="ソフトボディ",
            universal_name="Soft Body",
            shape=1,
            material_index=0,
            flags=0x07,
            bending_link_distance=2,
            cluster_count=3,
            anchors=(
                build_pmx_soft_body_anchor(
                    rigid_body_index=0,
                    vertex_index=0,
                    near_mode=1,
                    rigid_body_index_size=rigid_body_index_size,
                    vertex_index_size=vertex_index_size,
                ),
            ),
            pinned_vertex_indices=(1, 2),
            encoding_flag=encoding_flag,
            material_index_size=material_index_size,
            vertex_index_size=vertex_index_size,
        ),
    )


def build_pmx_roundtrip_fixture(
    *,
    version: float = 2.1,
    encoding_flag: int = 1,
    index_size: int = 1,
    index_sizes: tuple[int, int, int, int, int, int] | None = None,
) -> bytes:
    """Build one complete PMX fixture for a version/encoding/index tuple."""

    if version not in (2.0, 2.1):
        raise ValueError("version must be 2.0 or 2.1.")
    if encoding_flag not in (0, 1):
        raise ValueError("encoding_flag must be 0 or 1.")
    if index_size not in (1, 2, 4):
        raise ValueError("index_size must be 1, 2, or 4.")

    if index_sizes is None:
        resolved_sizes = (index_size,) * 6
    else:
        if not isinstance(index_sizes, tuple) or len(index_sizes) != 6:
            raise ValueError("index_sizes must contain exactly six values.")
        if any(size not in (1, 2, 4) for size in index_sizes):
            raise ValueError("every index size must be 1, 2, or 4.")
        resolved_sizes = index_sizes

    (
        vertex_index_size,
        texture_index_size,
        material_index_size,
        bone_index_size,
        morph_index_size,
        rigid_body_index_size,
    ) = resolved_sizes

    deform_types = (0, 1, 2, 3, 4) if version == 2.1 else (0, 1, 2, 3)
    return build_pmx_structure(
        version=version,
        encoding_flag=encoding_flag,
        additional_uv_count=4,
        vertex_index_size=vertex_index_size,
        texture_index_size=texture_index_size,
        material_index_size=material_index_size,
        bone_index_size=bone_index_size,
        morph_index_size=morph_index_size,
        rigid_body_index_size=rigid_body_index_size,
        deform_types=deform_types,
        surface_indices=(0, 1, 2),
        texture_paths=(
            "テクスチャ/体.png",
            "textures/sphere.spa",
            "textures/toon.bmp",
        ),
        materials=_build_materials(
            encoding_flag=encoding_flag,
            index_size=texture_index_size,
        ),
        bones=_build_bones(
            encoding_flag=encoding_flag,
            index_size=bone_index_size,
        ),
        morphs=_build_morphs(
            version=version,
            encoding_flag=encoding_flag,
            vertex_index_size=vertex_index_size,
            material_index_size=material_index_size,
            bone_index_size=bone_index_size,
            morph_index_size=morph_index_size,
            rigid_body_index_size=rigid_body_index_size,
        ),
        display_frames=_build_display_frames(
            encoding_flag=encoding_flag,
            bone_index_size=bone_index_size,
            morph_index_size=morph_index_size,
        ),
        rigid_bodies=_build_rigid_bodies(
            encoding_flag=encoding_flag,
            index_size=bone_index_size,
        ),
        joints=_build_joints(
            version=version,
            encoding_flag=encoding_flag,
            index_size=rigid_body_index_size,
        ),
        soft_bodies=_build_soft_bodies(
            version=version,
            encoding_flag=encoding_flag,
            vertex_index_size=vertex_index_size,
            material_index_size=material_index_size,
            rigid_body_index_size=rigid_body_index_size,
        ),
        trailing_bytes=b"roundtrip-extension",
    )
