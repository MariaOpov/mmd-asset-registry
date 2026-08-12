"""Generated regression matrix for deterministic texture portability workflows."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mmd_registry.texture_rewrite import (
    TextureRewriteDisposition,
    analyze_texture_rewrites,
    build_texture_rewrite_edit_plan,
)
from mmd_registry.pmx.editing import parse_pmx_edit_plan_json


class TexturePortabilityGeneratedMatrixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_directory = self.project_root / "model"
        self.model_directory.mkdir()
        self.model_path = self.model_directory / "character.pmx"
        self.model_path.write_bytes(b"PMX portability matrix fixture")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_texture(self, relative_path: str) -> None:
        path = self.model_directory.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"texture")

    def test_generated_declaration_matrix_has_stable_dispositions(self) -> None:
        self.write_texture("textures/body.png")
        outside = self.project_root / "outside.png"
        outside.write_bytes(b"outside")

        cases = (
            (
                "canonical",
                "textures/body.png",
                TextureRewriteDisposition.NO_CHANGE,
                None,
            ),
            (
                "backslash",
                r"textures\body.png",
                TextureRewriteDisposition.SAFE_REWRITE,
                "textures/body.png",
            ),
            (
                "bounded_parent",
                "textures/sub/../body.png",
                TextureRewriteDisposition.SAFE_REWRITE,
                "textures/body.png",
            ),
            (
                "case_mismatch",
                "textures/BODY.PNG",
                TextureRewriteDisposition.BLOCKED,
                None,
            ),
            (
                "missing",
                "textures/missing.png",
                TextureRewriteDisposition.BLOCKED,
                None,
            ),
            (
                "parent_escape",
                "../outside.png",
                TextureRewriteDisposition.BLOCKED,
                None,
            ),
            (
                "empty",
                "",
                TextureRewriteDisposition.BLOCKED,
                None,
            ),
        )

        for (
            label,
            declaration,
            expected_disposition,
            expected_candidate,
        ) in cases:
            with self.subTest(label=label):
                report = analyze_texture_rewrites(
                    self.model_path,
                    (declaration,),
                    (0,),
                )
                proposal = report.proposals[0]
                self.assertIs(
                    proposal.disposition,
                    expected_disposition,
                )
                self.assertEqual(
                    proposal.candidate_path,
                    expected_candidate,
                )

    def test_generated_plan_matrix_roundtrips_only_safe_rewrites(self) -> None:
        self.write_texture("textures/body.png")
        self.write_texture("textures/face.png")

        report = analyze_texture_rewrites(
            self.model_path,
            (
                r"textures\body.png",
                "textures/face.png",
                "textures/missing.png",
            ),
            (0, 1),
        )
        bridge = build_texture_rewrite_edit_plan(
            report,
            expected_source_sha256="b" * 64,
        )

        self.assertEqual(report.safe_rewrite_count, 1)
        self.assertEqual(report.no_change_count, 1)
        self.assertEqual(report.blocked_count, 1)
        self.assertIsNotNone(bridge.plan)
        self.assertIsNotNone(bridge.json_text)
        assert bridge.plan is not None
        assert bridge.json_text is not None
        self.assertEqual(len(bridge.plan.operations), 1)
        self.assertEqual(bridge.plan.operations[0].texture_index, 0)
        strict_loaded = parse_pmx_edit_plan_json(bridge.json_text)
        self.assertEqual(strict_loaded, bridge.plan)


if __name__ == "__main__":
    unittest.main()
