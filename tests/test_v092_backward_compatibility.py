"""Cross-generation backward-compatibility regression gates for v0.9.2."""

from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path

import mmd_registry
import mmd_registry.services as services
from mmd_registry import cli
from mmd_registry.diagnostics import PmxServiceDiagnosticCode, PmxServiceError
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.plan import PMX_EDIT_PLAN_SCHEMA_VERSION
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_texture import PmxStructuralTextureInsertion
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


EDIT_REPORT_KEYS = {
    "preview_schema_version",
    "status",
    "dry_run",
    "source",
    "plan",
    "output",
    "verification",
    "audit",
}


def _clean_document():
    return replace(
        load_pmx(io.BytesIO(build_pmx_roundtrip_fixture(version=2.1))),
        trailing_data=b"",
    )


def _legacy_texture_request(document):
    order = tuple(reversed(range(len(document.texture_paths))))
    edit = services.PmxStructuralCollectionEdit(
        services.PmxReferenceTargetKind.TEXTURE,
        order,
    )
    return services.PmxStructuralPreviewRequest((edit,))


def _insertion_request(path: str = "textures/__cp23_compat_insert__.png"):
    return services.PmxStructuralPreviewRequest(
        texture_insertions=(PmxStructuralTextureInsertion(path),),
    )


def _invalid_insertion_request(document):
    return services.PmxStructuralPreviewRequest(
        texture_insertions=(
            PmxStructuralTextureInsertion(
                "textures/__cp23_invalid_insert__.png",
                position="insert_before",
                source_index=len(document.texture_paths),
            ),
        ),
    )


def _legacy_edit_plan(source_bytes: bytes):
    payload = {
        "schema_version": 1,
        "expected_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "operations": [
            {
                "op": "set_model_info",
                "local_name": "CP23 Legacy Compatibility",
            }
        ],
    }
    return parse_pmx_edit_plan_json(json.dumps(payload))


def _capture_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = cli.run(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class V092BackwardCompatibilityTests(unittest.TestCase):
    """Protect released v0.8/v0.9.x behavior while v0.9.2 insertion exists."""

    def test_legacy_request_positional_construction_keeps_new_fields_empty(self) -> None:
        document = _clean_document()
        order = tuple(reversed(range(len(document.texture_paths))))
        edit = services.PmxStructuralCollectionEdit(
            services.PmxReferenceTargetKind.TEXTURE,
            order,
        )

        positional = services.PmxStructuralPreviewRequest((edit,))
        keyword = services.PmxStructuralPreviewRequest(collection_edits=(edit,))

        self.assertEqual(positional, keyword)
        self.assertEqual(positional.collection_edits, (edit,))
        self.assertEqual(positional.texture_insertions, ())
        self.assertEqual(positional.material_insertions, ())
        self.assertEqual(positional.bone_insertions, ())
        self.assertEqual(positional.morph_insertions, ())
        self.assertEqual(positional.rigid_body_insertions, ())
        self.assertEqual(positional.vertex_insertions, ())
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )

    def test_legacy_preview_is_identical_before_and_after_insertion_preview(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        legacy_request = _legacy_texture_request(document)

        before = services.preview_structural_edit(document, legacy_request)
        insertion = services.preview_structural_edit(document, _insertion_request())
        after = services.preview_structural_edit(document, legacy_request)

        self.assertEqual(before.to_dict(), after.to_dict())
        self.assertEqual(before.document, after.document)
        self.assertEqual(
            len(insertion.document.texture_paths),
            len(document.texture_paths) + 1,
        )
        self.assertEqual(serialize_pmx(document), source_bytes)

    def test_insertion_failure_does_not_change_next_legacy_preview(self) -> None:
        document = _clean_document()
        legacy_request = _legacy_texture_request(document)
        baseline = services.preview_structural_edit(document, legacy_request)

        with self.assertRaises(PmxServiceError) as raised:
            services.preview_structural_edit(
                document,
                _invalid_insertion_request(document),
            )

        self.assertEqual(
            raised.exception.diagnostic.code,
            PmxServiceDiagnosticCode.STRUCTURAL_PREVIEW_FAILED,
        )
        after = services.preview_structural_edit(document, legacy_request)
        self.assertEqual(after.to_dict(), baseline.to_dict())
        self.assertEqual(after.document, baseline.document)

    def test_v091_legacy_execution_stays_on_collection_transform_semantics(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        legacy_request = _legacy_texture_request(document)
        legacy_preview = services.preview_structural_edit(document, legacy_request)

        services.preview_structural_edit(document, _insertion_request())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output_one = root / "legacy-one.pmx"
            output_two = root / "legacy-two.pmx"
            source.write_bytes(source_bytes)

            first = services.apply_structural_edit(source, output_one, legacy_request)
            second = services.apply_structural_edit(source, output_two, legacy_request)

            self.assertEqual(first.document, legacy_preview.document)
            self.assertEqual(second.document, legacy_preview.document)
            self.assertEqual(load_pmx(output_one), legacy_preview.document)
            self.assertEqual(output_one.read_bytes(), output_two.read_bytes())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_v091_default_no_clobber_survives_insertion_activity(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        legacy_request = _legacy_texture_request(document)
        services.preview_structural_edit(document, _insertion_request())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output = root / "existing.pmx"
            sentinel = b"cp23-existing-destination"
            source.write_bytes(source_bytes)
            output.write_bytes(sentinel)

            with self.assertRaises(PmxServiceError) as raised:
                services.apply_structural_edit(source, output, legacy_request)

            self.assertEqual(
                raised.exception.diagnostic.code,
                PmxServiceDiagnosticCode.STRUCTURAL_PATH_UNSAFE,
            )
            self.assertEqual(output.read_bytes(), sentinel)
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_v08_edit_preview_and_write_reports_are_isolated_from_insertion(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        plan = _legacy_edit_plan(source_bytes)

        baseline = dry_run_pmx_edit(source_bytes, plan).to_dict()

        services.preview_structural_edit(document, _insertion_request())
        with self.assertRaises(PmxServiceError):
            services.preview_structural_edit(
                document,
                _invalid_insertion_request(document),
            )

        after = dry_run_pmx_edit(source_bytes, plan).to_dict()
        self.assertEqual(after, baseline)
        self.assertEqual(set(after), EDIT_REPORT_KEYS)
        self.assertEqual(PMX_EDIT_PLAN_SCHEMA_VERSION, 1)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy-source.pmx"
            output = root / "legacy-output.pmx"
            source.write_bytes(source_bytes)

            write_payload = write_pmx_edit(source, output, plan).to_dict()

            self.assertEqual(set(write_payload), EDIT_REPORT_KEYS)
            self.assertFalse(write_payload["dry_run"])
            self.assertEqual(
                write_payload["verification"]["semantic"],
                "passed",
            )
            self.assertIs(
                write_payload["verification"]["input_unchanged"],
                True,
            )
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertTrue(output.is_file())

    def test_legacy_cli_json_diagnostic_is_identical_after_insertion_failure(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            plan_path = root / "invalid-plan.json"
            source.write_bytes(source_bytes)
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "operations": [
                            {
                                "op": "rename_model",
                                "local_name": "unsupported",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            arguments = [
                "edit",
                str(source),
                "--plan",
                str(plan_path),
                "--dry-run",
                "--json",
            ]

            before = _capture_cli(arguments)
            with self.assertRaises(PmxServiceError):
                services.preview_structural_edit(
                    document,
                    _invalid_insertion_request(document),
                )
            after = _capture_cli(arguments)

        self.assertEqual(after, before)
        exit_code, output, error_output = after
        payload = json.loads(output)
        self.assertEqual(exit_code, 1)
        self.assertEqual(error_output, "")
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "invalid_plan")
        self.assertEqual(payload["error"]["code"], "edit_plan_invalid")
        self.assertEqual(payload["error"]["phase"], "plan_validate")

    def test_insertion_legacy_edit_insertion_and_capability_state_are_isolated(self) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        insertion_request = _insertion_request(
            "textures/__cp23_state_isolation__.png"
        )
        request_repr = repr(insertion_request)

        first = services.preview_structural_edit(document, insertion_request)
        manifest_before = services.get_capabilities().to_dict()
        mutated_copy = services.get_capabilities().to_dict()
        targets = mutated_copy["structural_target_kinds"]
        self.assertIsInstance(targets, list)
        targets.append("unsupported")  # type: ignore[union-attr]

        plan = _legacy_edit_plan(source_bytes)
        legacy_preview = dry_run_pmx_edit(source_bytes, plan)
        self.assertEqual(legacy_preview.to_dict()["plan"]["schema_version"], 1)

        second = services.preview_structural_edit(document, insertion_request)
        manifest_after = services.get_capabilities().to_dict()

        self.assertEqual(second.to_dict(), first.to_dict())
        self.assertEqual(second.document, first.document)
        self.assertEqual(repr(insertion_request), request_repr)
        self.assertEqual(manifest_after, manifest_before)
        self.assertNotIn(
            "unsupported",
            manifest_after["structural_target_kinds"],
        )
        self.assertEqual(mmd_registry.__version__, "0.9.1")
        self.assertNotIn("structural_insert", manifest_after)
        self.assertIs(
            services.PmxStructuralEditRequest,
            services.PmxStructuralPreviewRequest,
        )


if __name__ == "__main__":
    unittest.main()
