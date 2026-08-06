"""Tests for safe PMX display-frame structural scanning."""

from __future__ import annotations

import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mmd_registry import model_scanning
from mmd_registry.model_scanning import (
    MAX_PMX_DISPLAY_FRAME_COUNT,
    MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT,
    scan_pmx_structure,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_display_frame,
    build_pmx_display_frame_element,
    build_pmx_morph,
    build_pmx_structure,
)


class PmxDisplayFrameScanningTests(unittest.TestCase):
    """Tests for bounded PMX display-frame metadata extraction."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_fixture(self, file_name: str, data: bytes) -> Path:
        """Write and return one generated PMX fixture."""

        fixture_path = self.project_root / file_name
        fixture_path.write_bytes(data)
        return fixture_path

    def test_scans_zero_display_frame_section(self) -> None:
        fixture_data = build_pmx_structure(display_frames=())
        fixture = self.write_fixture("no_frames.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.display_frame_count, 0)
        self.assertEqual(result.display_frames, [])
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_bone_and_morph_elements(self) -> None:
        frame = build_pmx_display_frame(
            local_name="Main",
            universal_name="Main",
            elements=(
                build_pmx_display_frame_element(
                    target_type=0,
                    target_index=0,
                ),
                build_pmx_display_frame_element(
                    target_type=1,
                    target_index=0,
                ),
            ),
        )
        fixture_data = build_pmx_structure(
            bones=(build_pmx_bone(local_name="Root"),),
            morphs=(build_pmx_morph(local_name="Smile"),),
            display_frames=(frame,),
        )
        fixture = self.write_fixture("bone_morph_frame.pmx", fixture_data)

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.display_frame_count, 1)
        self.assertEqual(result.display_frames[0].local_name, "Main")
        self.assertFalse(result.display_frames[0].special)
        self.assertEqual(
            [element.target_type for element in result.display_frames[0].elements],
            ["bone", "morph"],
        )
        self.assertEqual(
            [element.target_index for element in result.display_frames[0].elements],
            [0, 0],
        )
        self.assertEqual(result.bytes_consumed, len(fixture_data))

    def test_scans_special_frame(self) -> None:
        fixture = self.write_fixture(
            "special_frame.pmx",
            build_pmx_structure(
                display_frames=(
                    build_pmx_display_frame(
                        local_name="Root",
                        special_flag=1,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertTrue(result.display_frames[0].special)

    def test_scans_utf16_display_frame_names(self) -> None:
        fixture = self.write_fixture(
            "utf16_frame.pmx",
            build_pmx_structure(
                encoding_flag=0,
                display_frames=(
                    build_pmx_display_frame(
                        local_name="表情",
                        universal_name="Expressions",
                        encoding_flag=0,
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.display_frames[0].local_name, "表情")
        self.assertEqual(
            result.display_frames[0].universal_name,
            "Expressions",
        )

    def test_preserves_duplicate_elements(self) -> None:
        duplicate = build_pmx_display_frame_element(
            target_type=0,
            target_index=0,
        )
        fixture = self.write_fixture(
            "duplicate_elements.pmx",
            build_pmx_structure(
                bones=(build_pmx_bone(),),
                display_frames=(
                    build_pmx_display_frame(
                        elements=(duplicate, duplicate),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.display_frames[0].elements), 2)
        self.assertEqual(
            result.display_frames[0].elements[0],
            result.display_frames[0].elements[1],
        )

    def test_supports_all_declared_index_sizes(self) -> None:
        for index_size in (1, 2, 4):
            with self.subTest(index_size=index_size):
                frame = build_pmx_display_frame(
                    elements=(
                        build_pmx_display_frame_element(
                            target_type=0,
                            target_index=0,
                            bone_index_size=index_size,
                            morph_index_size=index_size,
                        ),
                        build_pmx_display_frame_element(
                            target_type=1,
                            target_index=0,
                            bone_index_size=index_size,
                            morph_index_size=index_size,
                        ),
                    ),
                )
                fixture = self.write_fixture(
                    f"index_{index_size}.pmx",
                    build_pmx_structure(
                        bone_index_size=index_size,
                        morph_index_size=index_size,
                        bones=(
                            build_pmx_bone(
                                bone_index_size=index_size,
                            ),
                        ),
                        morphs=(build_pmx_morph(),),
                        display_frames=(frame,),
                    ),
                )

                result = scan_pmx_structure(fixture)

                self.assertEqual(result.status, "ok")
                self.assertEqual(
                    len(result.display_frames[0].elements),
                    2,
                )

    def test_rejects_invalid_display_frame_counts(self) -> None:
        cases = (
            ("negative", -1),
            ("over_limit", MAX_PMX_DISPLAY_FRAME_COUNT + 1),
            ("impossible", 1),
        )

        for label, count in cases:
            with self.subTest(label=label):
                fixture = self.write_fixture(
                    f"frame_count_{label}.pmx",
                    build_pmx_structure(
                        display_frames=(),
                        display_frame_count_override=count,
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any("display-frame count" in error for error in result.errors)
                )

    def test_rejects_invalid_special_flag(self) -> None:
        fixture = self.write_fixture(
            "invalid_special.pmx",
            build_pmx_structure(
                display_frames=(build_pmx_display_frame(special_flag=2),),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "display_frames[0]" in error and "special flag 2" in error
                for error in result.errors
            )
        )

    def test_rejects_invalid_element_counts(self) -> None:
        cases = (
            ("negative", -1),
            ("over_limit", MAX_PMX_DISPLAY_FRAME_ELEMENT_COUNT + 1),
            ("impossible", 3),
        )

        for label, count in cases:
            with self.subTest(label=label):
                fixture = self.write_fixture(
                    f"element_count_{label}.pmx",
                    build_pmx_structure(
                        display_frames=(
                            build_pmx_display_frame(
                                elements=(),
                                element_count_override=count,
                            ),
                        ),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any(
                        "display-frame element count" in error
                        for error in result.errors
                    )
                )

    def test_rejects_invalid_element_type(self) -> None:
        fixture = self.write_fixture(
            "invalid_type.pmx",
            build_pmx_structure(
                display_frames=(
                    build_pmx_display_frame(
                        elements=(
                            build_pmx_display_frame_element(
                                target_type=2,
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "display_frames[0].elements[0]" in error
                and "invalid target type 2" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_bone_index(self) -> None:
        fixture = self.write_fixture(
            "bad_bone_index.pmx",
            build_pmx_structure(
                display_frames=(
                    build_pmx_display_frame(
                        elements=(
                            build_pmx_display_frame_element(
                                target_type=0,
                                target_index=0,
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "display_frames[0].elements[0]" in error and "bone count 0" in error
                for error in result.errors
            )
        )

    def test_rejects_out_of_range_morph_index(self) -> None:
        fixture = self.write_fixture(
            "bad_morph_index.pmx",
            build_pmx_structure(
                display_frames=(
                    build_pmx_display_frame(
                        elements=(
                            build_pmx_display_frame_element(
                                target_type=1,
                                target_index=0,
                            ),
                        ),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "display_frames[0].elements[0]" in error and "morph count 0" in error
                for error in result.errors
            )
        )

    def test_rejects_minus_one_reference_sentinels(self) -> None:
        for target_type, label in ((0, "bone"), (1, "morph")):
            with self.subTest(target_type=label):
                fixture = self.write_fixture(
                    f"minus_one_{label}.pmx",
                    build_pmx_structure(
                        bones=(build_pmx_bone(),),
                        morphs=(build_pmx_morph(),),
                        display_frames=(
                            build_pmx_display_frame(
                                elements=(
                                    build_pmx_display_frame_element(
                                        target_type=target_type,
                                        target_index=-1,
                                    ),
                                ),
                            ),
                        ),
                    ),
                )
                result = scan_pmx_structure(fixture)
                self.assertEqual(result.status, "error")
                self.assertTrue(
                    any("index -1 is invalid" in error for error in result.errors)
                )

    def test_rejects_truncated_display_frame_element(self) -> None:
        fixture_data = build_pmx_structure(
            bones=(build_pmx_bone(),),
            display_frames=(
                build_pmx_display_frame(
                    elements=(
                        build_pmx_display_frame_element(
                            target_type=0,
                            target_index=0,
                        ),
                    ),
                ),
            ),
        )
        fixture = self.write_fixture(
            "truncated_element.pmx",
            fixture_data[:-5],
        )

        result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "display-frame element count" in error and "requires at least" in error
                for error in result.errors
            )
        )

    def test_rejects_total_element_budget_overflow(self) -> None:
        element = build_pmx_display_frame_element(
            target_type=0,
            target_index=0,
        )
        fixture = self.write_fixture(
            "total_budget.pmx",
            build_pmx_structure(
                bones=(build_pmx_bone(),),
                display_frames=(
                    build_pmx_display_frame(elements=(element,)),
                    build_pmx_display_frame(elements=(element,)),
                ),
            ),
        )

        with patch.object(
            model_scanning,
            "MAX_PMX_TOTAL_DISPLAY_FRAME_ELEMENT_COUNT",
            1,
        ):
            result = scan_pmx_structure(fixture)

        self.assertEqual(result.status, "error")
        self.assertTrue(
            any(
                "cumulative display-frame element count 2" in error
                for error in result.errors
            )
        )

    def test_display_frame_result_is_json_serializable(self) -> None:
        fixture = self.write_fixture(
            "frame_json.pmx",
            build_pmx_structure(
                bones=(build_pmx_bone(),),
                display_frames=(
                    build_pmx_display_frame(
                        local_name="Root",
                        special_flag=1,
                        elements=(build_pmx_display_frame_element(),),
                    ),
                ),
            ),
        )

        result = scan_pmx_structure(fixture)
        payload = result.to_dict()
        serialized = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["display_frame_count"], 1)
        self.assertEqual(
            payload["display_frames"][0]["element_count"],
            1,
        )
        self.assertEqual(
            payload["display_frames"][0]["elements"][0],
            {
                "target_type": "bone",
                "target_index": 0,
            },
        )
        self.assertIn('"display_frame_count": 1', serialized)


if __name__ == "__main__":
    unittest.main()
