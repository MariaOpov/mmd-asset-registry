"""Typed reading for complete PMX display-frame records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from mmd_registry.binary_reader import BinaryReader
from mmd_registry.pmx.document import (
    PmxDisplayFrame,
    PmxDisplayFrameElement,
    PmxDisplayFrameTargetType,
    PmxHeader,
)
from mmd_registry.pmx.errors import raise_pmx_error
from mmd_registry.pmx.sections.header import MAX_PMX_NAME_BYTES


MAX_PMX_DISPLAY_FRAME_COUNT: Final[int] = 100_000
MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT: Final[int] = 1_000_000
MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT: Final[int] = 5_000_000


@dataclass(slots=True)
class PmxDisplayFrameReadState:
    """Incremental display-frame data for legacy scanner projections."""

    display_frame_count: int | None = None
    display_frames: tuple[PmxDisplayFrame, ...] = ()


def _minimum_display_frame_size() -> int:
    """Return the smallest possible PMX display-frame record size."""

    return 8 + 1 + 4


def _minimum_display_frame_element_size(header: PmxHeader) -> int:
    """Return the smallest possible PMX display-frame element size."""

    return 1 + min(header.index_sizes.bone, header.index_sizes.morph)


def _validate_target_index(
    value: int,
    *,
    target_type: PmxDisplayFrameTargetType,
    target_count: int,
    frame_record_index: int,
    element_index: int,
    offset: int,
) -> None:
    """Validate one display-frame bone or morph reference."""

    if value < 0 or value >= target_count:
        if target_count == 0:
            expected = f"no valid {target_type} index exists"
        else:
            expected = f"expected a value from 0 through {target_count - 1}"

        raise_pmx_error(
            section=f"display_frames[{frame_record_index}].elements",
            record_index=element_index,
            offset=offset,
            operation=f"validating display-frame {target_type} index",
            reason=(
                f"index {value} is invalid for {target_type} count "
                f"{target_count}; {expected}."
            ),
        )


def _read_display_frame_element(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    bone_count: int,
    morph_count: int,
    frame_record_index: int,
    element_index: int,
) -> PmxDisplayFrameElement:
    """Read and validate one PMX display-frame element."""

    section = f"display_frames[{frame_record_index}].elements"

    with reader.context(section, record_index=element_index):
        target_type_offset = reader.offset
        target_type_value = reader.read_uint8(
            "display-frame element target type"
        )

        if target_type_value == 0:
            target_type: PmxDisplayFrameTargetType = "bone"
            target_count = bone_count
            target_index_size = header.index_sizes.bone
        elif target_type_value == 1:
            target_type = "morph"
            target_count = morph_count
            target_index_size = header.index_sizes.morph
        else:
            raise_pmx_error(
                section=section,
                record_index=element_index,
                offset=target_type_offset,
                operation="validating display-frame element target type",
                reason=(
                    f"invalid target type {target_type_value}; "
                    "expected 0 for bone or 1 for morph."
                ),
            )

        target_index_offset = reader.offset
        target_index = reader.read_index(
            target_index_size,
            signed=True,
            label=f"display-frame {target_type} index",
        )

    _validate_target_index(
        target_index,
        target_type=target_type,
        target_count=target_count,
        frame_record_index=frame_record_index,
        element_index=element_index,
        offset=target_index_offset,
    )

    return PmxDisplayFrameElement(
        target_type=target_type,
        target_index=target_index,
    )


def _read_display_frame(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    bone_count: int,
    morph_count: int,
    record_index: int,
) -> PmxDisplayFrame:
    """Read one PMX display-frame record."""

    require_even_length = header.encoding == "utf-16-le"

    with reader.context("display_frames", record_index=record_index):
        local_name = reader.read_length_prefixed_text(
            "local display-frame name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )
        universal_name = reader.read_length_prefixed_text(
            "universal display-frame name",
            encoding=header.encoding,
            max_length=MAX_PMX_NAME_BYTES,
            require_even_length=require_even_length,
        )

        special_flag_offset = reader.offset
        special_flag = reader.read_uint8("display-frame special flag")
        if special_flag not in {0, 1}:
            raise_pmx_error(
                section="display_frames",
                record_index=record_index,
                offset=special_flag_offset,
                operation="validating display-frame special flag",
                reason=(
                    f"invalid special flag {special_flag}; expected 0 or 1."
                ),
            )

        element_count = reader.read_bounded_count(
            "display-frame element count",
            max_count=MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT,
            minimum_item_size=_minimum_display_frame_element_size(header),
        )

    elements = tuple(
        _read_display_frame_element(
            reader,
            header=header,
            bone_count=bone_count,
            morph_count=morph_count,
            frame_record_index=record_index,
            element_index=element_index,
        )
        for element_index in range(element_count)
    )

    return PmxDisplayFrame(
        local_name=local_name,
        universal_name=universal_name,
        special=bool(special_flag),
        elements=elements,
    )


def _validate_count_argument(value: object, label: str) -> int:
    """Require one nonnegative, non-boolean prior-section count."""

    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{label} must be an integer.")
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")
    return value


def read_pmx_display_frames(
    reader: BinaryReader,
    *,
    header: PmxHeader,
    bone_count: int,
    morph_count: int,
    state: PmxDisplayFrameReadState | None = None,
    max_total_element_count: int = MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT,
) -> tuple[PmxDisplayFrame, ...]:
    """Read the complete ordered PMX display-frame section."""

    if not isinstance(header, PmxHeader):
        raise TypeError("header must be a PmxHeader instance.")

    bone_count = _validate_count_argument(bone_count, "bone_count")
    morph_count = _validate_count_argument(morph_count, "morph_count")
    max_total_element_count = _validate_count_argument(
        max_total_element_count,
        "max_total_element_count",
    )
    read_state = state if state is not None else PmxDisplayFrameReadState()

    with reader.context("display_frames"):
        display_frame_count = reader.read_bounded_count(
            "display-frame count",
            max_count=MAX_PMX_DISPLAY_FRAME_COUNT,
            minimum_item_size=_minimum_display_frame_size(),
        )

    read_state.display_frame_count = display_frame_count
    display_frames: list[PmxDisplayFrame] = []
    total_element_count = 0

    for record_index in range(display_frame_count):
        display_frame = _read_display_frame(
            reader,
            header=header,
            bone_count=bone_count,
            morph_count=morph_count,
            record_index=record_index,
        )
        display_frames.append(display_frame)
        total_element_count += len(display_frame.elements)

        if total_element_count > max_total_element_count:
            raise_pmx_error(
                section="display_frames",
                record_index=record_index,
                offset=reader.offset,
                operation="validating total display-frame element count",
                reason=(
                    f"cumulative display-frame element count "
                    f"{total_element_count} exceeds the safety limit of "
                    f"{max_total_element_count}."
                ),
            )

    frame_records = tuple(display_frames)
    read_state.display_frames = frame_records
    return frame_records
