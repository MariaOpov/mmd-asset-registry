"""Tests for deterministic safe texture rewrite proposals and edit-plan bridge."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.operations import SetTexturePath
from mmd_registry.texture_rewrite import (
    TextureRewriteCandidateSource,
    TextureRewriteDisposition,
    analyze_texture_rewrites,
    build_texture_rewrite_edit_plan,
)
from mmd_registry.texture_portability import analyze_texture_portability


class TextureRewriteProposalTests(unittest.TestCase):
    """Lock deterministic proposal boundaries without fuzzy path recovery."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_directory = self.project_root / "model"
        self.model_directory.mkdir()
        self.model_path = self.model_directory / "character.pmx"
        self.model_path.write_bytes(b"PMX fixture placeholder")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_texture(
        self,
        relative_path: str,
        data: bytes = b"texture",
    ) -> Path:
        path = self.model_directory.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_canonical_existing_relative_path_needs_no_change(self) -> None:
        self.write_texture("textures/body.png")

        report = analyze_texture_rewrites(
            self.model_path,
            ("textures/body.png",),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertEqual(report.safe_rewrite_count, 0)
        self.assertEqual(report.no_change_count, 1)
        self.assertEqual(report.blocked_count, 0)
        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.NO_CHANGE,
        )
        self.assertIsNone(proposal.candidate_path)
        self.assertTrue(proposal.is_referenced)

    def test_backslash_relative_path_gets_forward_slash_candidate(self) -> None:
        self.write_texture("textures/body.png")

        report = analyze_texture_rewrites(
            self.model_path,
            (r"textures\body.png",),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.SAFE_REWRITE,
        )
        self.assertEqual(proposal.candidate_path, "textures/body.png")
        self.assertIs(
            proposal.candidate_source,
            TextureRewriteCandidateSource.LEXICAL,
        )

    def test_parent_reference_inside_model_is_collapsed_safely(self) -> None:
        self.write_texture("textures/body.png")

        report = analyze_texture_rewrites(
            self.model_path,
            ("textures/sub/../body.png",),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.SAFE_REWRITE,
        )
        self.assertEqual(proposal.candidate_path, "textures/body.png")
        self.assertIn("parent_reference", proposal.source_issue_codes)

    def test_native_absolute_file_inside_model_becomes_model_relative(self) -> None:
        texture = self.write_texture("textures/body.png")

        report = analyze_texture_rewrites(
            self.model_path,
            (str(texture.resolve()),),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.SAFE_REWRITE,
        )
        self.assertEqual(proposal.candidate_path, "textures/body.png")
        self.assertIs(
            proposal.candidate_source,
            TextureRewriteCandidateSource.FILESYSTEM,
        )
        self.assertIn("absolute_path", proposal.source_issue_codes)

    def test_outside_model_file_is_blocked(self) -> None:
        outside = self.project_root / "shared.png"
        outside.write_bytes(b"texture")

        report = analyze_texture_rewrites(
            self.model_path,
            (str(outside.resolve()),),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.BLOCKED,
        )
        self.assertIsNone(proposal.candidate_path)
        self.assertIn("outside_model_directory", proposal.source_issue_codes)

    def test_missing_file_is_blocked_without_fuzzy_matching(self) -> None:
        self.write_texture("textures/body.png")

        report = analyze_texture_rewrites(
            self.model_path,
            ("textures/BODY.PNG",),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.BLOCKED,
        )
        self.assertIsNone(proposal.candidate_path)
        self.assertIn("missing_file", proposal.source_issue_codes)

    def test_foreign_absolute_syntax_without_host_evidence_is_blocked(self) -> None:
        foreign_path = (
            r"C:\MMD\textures\body.png"
            if os.name != "nt"
            else "/opt/mmd/textures/body.png"
        )

        report = analyze_texture_rewrites(
            self.model_path,
            (foreign_path,),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.BLOCKED,
        )
        self.assertIsNone(proposal.candidate_path)

    def test_duplicate_declarations_preserve_index_order_and_reference_state(self) -> None:
        self.write_texture("textures/shared.png")

        report = analyze_texture_rewrites(
            self.model_path,
            (
                r"textures\shared.png",
                r"textures\shared.png",
            ),
            (1,),
        )

        self.assertEqual(
            tuple(proposal.texture_index for proposal in report.proposals),
            (0, 1),
        )
        self.assertEqual(report.safe_rewrite_count, 2)
        self.assertFalse(report.proposals[0].is_referenced)
        self.assertTrue(report.proposals[1].is_referenced)

    def test_proposal_analysis_does_not_modify_model_or_texture_files(self) -> None:
        texture = self.write_texture("textures/body.png", b"original texture")
        model_before = self.model_path.read_bytes()
        texture_before = texture.read_bytes()
        names_before = sorted(
            path.relative_to(self.project_root).as_posix()
            for path in self.project_root.rglob("*")
        )

        analyze_texture_rewrites(
            self.model_path,
            (r"textures\body.png",),
            (0,),
        )

        names_after = sorted(
            path.relative_to(self.project_root).as_posix()
            for path in self.project_root.rglob("*")
        )
        self.assertEqual(self.model_path.read_bytes(), model_before)
        self.assertEqual(texture.read_bytes(), texture_before)
        self.assertEqual(names_after, names_before)


    def test_parent_reference_escape_is_blocked(self) -> None:
        outside = self.project_root / "shared.png"
        outside.write_bytes(b"texture")

        report = analyze_texture_rewrites(
            self.model_path,
            ("../shared.png",),
            (0,),
        )
        proposal = report.proposals[0]

        self.assertIs(
            proposal.disposition,
            TextureRewriteDisposition.BLOCKED,
        )
        self.assertIsNone(proposal.candidate_path)
        self.assertIn("parent_reference", proposal.source_issue_codes)
        self.assertIn("outside_model_directory", proposal.source_issue_codes)

class TextureRewriteEditPlanBridgeTests(unittest.TestCase):
    """Verify reuse of the existing strict set_texture_path plan pipeline."""

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_directory.name)
        self.model_directory = self.project_root / "model"
        self.model_directory.mkdir()
        self.model_path = self.model_directory / "character.pmx"
        self.model_path.write_bytes(b"PMX fixture placeholder")

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_texture(self, relative_path: str) -> None:
        path = self.model_directory.joinpath(*relative_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"texture")

    def test_bridge_emits_only_existing_set_texture_path_operations(self) -> None:
        self.write_texture("textures/body.png")
        self.write_texture("textures/face.png")
        report = analyze_texture_rewrites(
            self.model_path,
            (
                r"textures\body.png",
                "textures/face.png",
            ),
            (0, 1),
        )

        bridge = build_texture_rewrite_edit_plan(report)

        self.assertIsNotNone(bridge.plan)
        assert bridge.plan is not None
        self.assertEqual(len(bridge.plan.operations), 1)
        operation = bridge.plan.operations[0]
        self.assertIsInstance(operation, SetTexturePath)
        self.assertEqual(operation.texture_index, 0)
        self.assertEqual(operation.path, "textures/body.png")

    def test_generated_json_must_roundtrip_through_existing_strict_loader(self) -> None:
        self.write_texture("textures/body.png")
        report = analyze_texture_rewrites(
            self.model_path,
            (r"textures\body.png",),
            (0,),
        )

        bridge = build_texture_rewrite_edit_plan(
            report,
            expected_source_sha256="a" * 64,
        )

        self.assertIsNotNone(bridge.plan)
        self.assertIsNotNone(bridge.json_text)
        assert bridge.plan is not None
        assert bridge.json_text is not None
        strict_loaded = parse_pmx_edit_plan_json(bridge.json_text)
        self.assertEqual(strict_loaded, bridge.plan)
        payload = json.loads(bridge.json_text)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["expected_source_sha256"], "a" * 64)
        self.assertEqual(
            payload["operations"],
            [
                {
                    "op": "set_texture_path",
                    "texture_index": 0,
                    "path": "textures/body.png",
                }
            ],
        )

    def test_bridge_preserves_multiple_rewrite_operation_order(self) -> None:
        self.write_texture("textures/body.png")
        self.write_texture("textures/face.png")
        report = analyze_texture_rewrites(
            self.model_path,
            (
                r"textures\face.png",
                r"textures\body.png",
            ),
            (0, 1),
        )

        bridge = build_texture_rewrite_edit_plan(report)

        self.assertIsNotNone(bridge.plan)
        assert bridge.plan is not None
        self.assertEqual(
            tuple(
                (operation.texture_index, operation.path)
                for operation in bridge.plan.operations
            ),
            (
                (0, "textures/face.png"),
                (1, "textures/body.png"),
            ),
        )

    def test_bridge_returns_no_plan_when_no_rewrite_is_needed(self) -> None:
        self.write_texture("textures/body.png")
        report = analyze_texture_rewrites(
            self.model_path,
            ("textures/body.png",),
            (0,),
        )

        bridge = build_texture_rewrite_edit_plan(report)

        self.assertIsNone(bridge.plan)
        self.assertIsNone(bridge.json_text)
        self.assertFalse(bridge.to_dict()["has_edit_plan"])

    def test_bridge_keeps_unreferenced_safe_rewrites_explicit(self) -> None:
        self.write_texture("textures/unused.png")
        portability = analyze_texture_portability(
            self.model_path,
            (r"textures\unused.png",),
            (),
        )
        from mmd_registry.texture_rewrite import build_texture_rewrite_report

        report = build_texture_rewrite_report(
            model_path=self.model_path,
            portability_report=portability,
        )
        bridge = build_texture_rewrite_edit_plan(report)

        self.assertEqual(report.safe_rewrite_count, 1)
        self.assertFalse(report.proposals[0].is_referenced)
        self.assertIsNotNone(bridge.plan)
        assert bridge.plan is not None
        self.assertEqual(bridge.plan.operations[0].texture_index, 0)


if __name__ == "__main__":
    unittest.main()
