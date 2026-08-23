"""CP24 structural-transaction state-isolation and adversarial gates."""

from __future__ import annotations

from dataclasses import replace
import importlib
import io
import operator
from pathlib import Path
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

import mmd_registry.pmx.editing.output as edit_output
import mmd_registry.services as services
from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.pmx.reference_model import (
    PmxReferenceSourceSection,
    PmxReferenceTargetKind,
)
from mmd_registry.pmx.writer import serialize_pmx
from mmd_registry.services.structural_material import (
    PmxStructuralMaterialInsertion,
)
from mmd_registry.services.structural_reference import (
    PmxStructuralNewReference,
)
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
    apply_structural_transaction,
    preview_structural_transaction,
)
from tests.pmx_roundtrip_fixtures import build_pmx_roundtrip_fixture


COMPOSITION_MODULE = importlib.import_module(
    "mmd_registry.pmx.structural_transaction_composition"
)
DEPENDENCY_MODULE = importlib.import_module(
    "mmd_registry.pmx.structural_transaction_dependency"
)
INSERTION_MODULE = importlib.import_module(
    "mmd_registry.pmx.structural_transaction_insertion"
)
PREVIEW_MODULE = importlib.import_module(
    "mmd_registry.pmx.structural_transaction_preview"
)
TARGET_ATTRIBUTES = (
    (PmxReferenceTargetKind.VERTEX, "vertices"),
    (PmxReferenceTargetKind.TEXTURE, "texture_paths"),
    (PmxReferenceTargetKind.MATERIAL, "materials"),
    (PmxReferenceTargetKind.BONE, "bones"),
    (PmxReferenceTargetKind.MORPH, "morphs"),
    (PmxReferenceTargetKind.RIGID_BODY, "rigid_bodies"),
)


def _clean_document(*, version: float = 2.1, index_size: int = 1):
    return replace(
        load_pmx(
            io.BytesIO(
                build_pmx_roundtrip_fixture(
                    version=version,
                    index_size=index_size,
                )
            )
        ),
        trailing_data=b"",
    )


def _forward_reference_request(label: str) -> PmxStructuralTransactionRequest:
    identity = f"{label}.texture"
    return PmxStructuralTransactionRequest(
        (
            PmxStructuralMaterialInsertion(
                f"{label} material",
                texture_index=PmxStructuralNewReference(
                    "texture",
                    identity,
                ),
            ),
            PmxStructuralTextureInsertion(
                f"textures/{label}.png",
                new_id=identity,
            ),
        )
    )


def _unknown_reference_request() -> PmxStructuralTransactionRequest:
    return PmxStructuralTransactionRequest(
        (
            PmxStructuralMaterialInsertion(
                "unknown reference",
                texture_index=PmxStructuralNewReference(
                    "texture",
                    "missing.texture",
                ),
            ),
        )
    )


def _identity_request(document) -> PmxStructuralTransactionRequest:
    return PmxStructuralTransactionRequest(
        tuple(
            services.PmxStructuralCollectionEdit(
                target_kind,
                tuple(range(len(getattr(document, attribute)))),
            )
            for target_kind, attribute in TARGET_ATTRIBUTES
        )
    )


def _details(error: PmxServiceError) -> dict[str, object]:
    details = error.to_dict()["details"]
    assert isinstance(details, dict)
    return details


def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
    return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))


class V093StructuralTransactionAdversarialIsolationTests(unittest.TestCase):
    def test_transaction_lookup_tables_are_exact_and_read_only(self) -> None:
        target_rank = {
            target_kind: rank
            for rank, target_kind in enumerate(PmxReferenceTargetKind)
        }
        source_rank = {
            section: rank
            for rank, section in enumerate(PmxReferenceSourceSection)
        }
        materialization_rank = {
            target_kind: rank
            for rank, target_kind in enumerate(
                (
                    PmxReferenceTargetKind.TEXTURE,
                    PmxReferenceTargetKind.MATERIAL,
                    PmxReferenceTargetKind.BONE,
                    PmxReferenceTargetKind.VERTEX,
                    PmxReferenceTargetKind.RIGID_BODY,
                    PmxReferenceTargetKind.MORPH,
                )
            )
        }
        owner_targets = {
            PmxReferenceSourceSection.VERTICES: (
                PmxReferenceTargetKind.VERTEX
            ),
            PmxReferenceSourceSection.MATERIALS: (
                PmxReferenceTargetKind.MATERIAL
            ),
            PmxReferenceSourceSection.BONES: PmxReferenceTargetKind.BONE,
            PmxReferenceSourceSection.MORPHS: PmxReferenceTargetKind.MORPH,
            PmxReferenceSourceSection.RIGID_BODIES: (
                PmxReferenceTargetKind.RIGID_BODY
            ),
        }
        stage_provenance = {
            "transaction_normalization": "transaction_plan",
            "reference_resolution": "transaction_plan",
            "dependency_resolution": "transaction_plan",
            "capacity_preflight": "transaction_plan",
            "transform": "structural_pipeline",
            "structural_certification": "structural_pipeline",
        }
        tables = (
            (COMPOSITION_MODULE, "_TARGET_KIND_RANK", target_rank),
            (DEPENDENCY_MODULE, "_MATERIALIZATION_RANK", materialization_rank),
            (INSERTION_MODULE, "_TARGET_KIND_RANK", target_rank),
            (PREVIEW_MODULE, "_TARGET_KIND_RANK", target_rank),
            (PREVIEW_MODULE, "_SOURCE_SECTION_RANK", source_rank),
            (PREVIEW_MODULE, "_OWNER_TARGETS", owner_targets),
            (PREVIEW_MODULE, "_STAGE_PROVENANCE", stage_provenance),
            (
                PREVIEW_MODULE,
                "_TARGET_COLLECTION_ATTRIBUTES",
                dict(TARGET_ATTRIBUTES),
            ),
        )

        for module, name, expected in tables:
            with self.subTest(module=module.__name__, table=name):
                table = getattr(module, name)
                self.assertIsInstance(table, MappingProxyType)
                self.assertNotIsInstance(table, (dict, list, set))
                self.assertEqual(dict(table), expected)
                key = next(iter(table))
                with self.assertRaises(TypeError):
                    operator.setitem(table, key, object())
                with self.assertRaises(TypeError):
                    operator.delitem(table, key)
                self.assertEqual(dict(table), expected)

    def test_all_target_identity_matrix_is_order_isolated(self) -> None:
        document = _clean_document()
        requests = tuple(
            PmxStructuralTransactionRequest(
                (
                    services.PmxStructuralCollectionEdit(
                        target_kind,
                        tuple(range(len(getattr(document, attribute)))),
                    ),
                )
            )
            for target_kind, attribute in TARGET_ATTRIBUTES
        )
        first = tuple(
            preview_structural_transaction(document, request)
            for request in requests
        )
        repeated = tuple(
            reversed(
                tuple(
                    preview_structural_transaction(document, request)
                    for request in reversed(requests)
                )
            )
        )

        for position, (before, after) in enumerate(zip(first, repeated)):
            with self.subTest(target_kind=TARGET_ATTRIBUTES[position][0].value):
                self.assertEqual(before.document, document)
                self.assertEqual(after.document, document)
                self.assertEqual(before.plan_sha256, after.plan_sha256)
                self.assertEqual(before.to_dict(), after.to_dict())

    def test_a_b_a_preview_and_public_evidence_are_isolated(self) -> None:
        source_a = _clean_document(version=2.1, index_size=1)
        source_b = _clean_document(version=2.0, index_size=2)
        request = _forward_reference_request("shared")
        source_a_snapshot = source_a
        request_snapshot = repr(request)

        a_before = preview_structural_transaction(source_a, request)
        b_result = preview_structural_transaction(source_b, request)
        a_after = preview_structural_transaction(source_a, request)

        self.assertNotEqual(a_before.plan_sha256, b_result.plan_sha256)
        self.assertEqual(a_before.plan_sha256, a_after.plan_sha256)
        self.assertEqual(a_before.document, a_after.document)
        self.assertEqual(a_before.to_dict(), a_after.to_dict())
        self.assertEqual(source_a, source_a_snapshot)
        self.assertEqual(repr(request), request_snapshot)

        detached = a_before.to_dict()
        detached["status"] = "caller mutation"
        self.assertEqual(a_before.to_dict(), a_after.to_dict())
        self.assertNotEqual(detached, a_before.to_dict())

    def test_local_identity_and_preview_failures_do_not_leak(self) -> None:
        with self.assertRaisesRegex(ValueError, "globally unique"):
            PmxStructuralTransactionRequest(
                (
                    PmxStructuralTextureInsertion(
                        "textures/duplicate-a.png",
                        new_id="reusable.identity",
                    ),
                    PmxStructuralTextureInsertion(
                        "textures/duplicate-b.png",
                        new_id="reusable.identity",
                    ),
                )
            )

        document = _clean_document()
        good = _forward_reference_request("reusable")
        bad = _unknown_reference_request()
        with self.assertRaises(PmxServiceError) as first_failure:
            preview_structural_transaction(document, bad)
        first_success = preview_structural_transaction(document, good)
        with self.assertRaises(PmxServiceError) as second_failure:
            preview_structural_transaction(document, bad)
        second_success = preview_structural_transaction(document, good)

        self.assertEqual(
            first_failure.exception.to_dict(),
            second_failure.exception.to_dict(),
        )
        self.assertEqual(first_success.document, second_success.document)
        self.assertEqual(first_success.to_dict(), second_success.to_dict())

    def test_preview_blocker_stage_matrix_has_no_cross_call_state(self) -> None:
        document = _clean_document(index_size=1)
        capacity_document = replace(
            document,
            texture_paths=tuple(
                f"textures/{index}.png" for index in range(128)
            ),
        )
        cases = (
            (
                document,
                PmxStructuralTransactionRequest(
                    (
                        services.PmxStructuralCollectionEdit(
                            PmxReferenceTargetKind.TEXTURE,
                            (1, 2),
                        ),
                        PmxStructuralTextureInsertion(
                            "textures/deleted-anchor.png",
                            position="insert_before",
                            source_index=0,
                        ),
                    )
                ),
                "transaction_normalization",
            ),
            (document, _unknown_reference_request(), "reference_resolution"),
            (
                capacity_document,
                PmxStructuralTransactionRequest(
                    (
                        PmxStructuralTextureInsertion(
                            "textures/overflow.png"
                        ),
                    )
                ),
                "capacity_preflight",
            ),
        )

        for source, bad_request, expected_stage in cases:
            with self.subTest(stage=expected_stage):
                good_request = _identity_request(source)
                before = preview_structural_transaction(source, good_request)
                with self.assertRaises(PmxServiceError) as first_failure:
                    preview_structural_transaction(source, bad_request)
                middle = preview_structural_transaction(source, good_request)
                with self.assertRaises(PmxServiceError) as second_failure:
                    preview_structural_transaction(source, bad_request)
                after = preview_structural_transaction(source, good_request)

                self.assertEqual(
                    _details(first_failure.exception)["stage"],
                    expected_stage,
                )
                self.assertEqual(
                    first_failure.exception.to_dict(),
                    second_failure.exception.to_dict(),
                )
                self.assertEqual(before.to_dict(), middle.to_dict())
                self.assertEqual(before.to_dict(), after.to_dict())
                self.assertEqual(before.document, source)
                self.assertEqual(after.document, source)

    def test_preview_execute_preview_and_cross_request_outputs_are_isolated(
        self,
    ) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        request_a = _forward_reference_request("execution-a")
        request_b = PmxStructuralTransactionRequest()
        before = preview_structural_transaction(document, request_a)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            output_a1 = root / "a1.pmx"
            output_b = root / "b.pmx"
            output_a2 = root / "a2.pmx"
            source.write_bytes(source_bytes)

            result_a1 = apply_structural_transaction(
                source,
                output_a1,
                request_a,
            )
            apply_structural_transaction(source, output_b, request_b)
            result_a2 = apply_structural_transaction(
                source,
                output_a2,
                request_a,
            )

            report_a1 = result_a1.to_dict()
            report_a2 = result_a2.to_dict()
            output_evidence_a1 = report_a1["output"]
            output_evidence_a2 = report_a2["output"]
            assert isinstance(output_evidence_a1, dict)
            assert isinstance(output_evidence_a2, dict)
            self.assertEqual(output_evidence_a1["path"], output_a1.as_posix())
            self.assertEqual(output_evidence_a2["path"], output_a2.as_posix())
            output_evidence_a1["path"] = "<caller-destination>"
            output_evidence_a2["path"] = "<caller-destination>"
            self.assertEqual(report_a1, report_a2)
            self.assertEqual(output_a1.read_bytes(), output_a2.read_bytes())
            self.assertEqual(load_pmx(output_a1), result_a1.document)
            self.assertEqual(load_pmx(output_a2), result_a2.document)
            self.assertEqual(source.read_bytes(), source_bytes)
            for destination in (output_a1, output_b, output_a2):
                self.assertEqual(_temporary_outputs(destination), ())

        after = preview_structural_transaction(document, request_a)
        self.assertEqual(before.document, after.document)
        self.assertEqual(before.to_dict(), after.to_dict())

    def test_planning_and_publication_failures_do_not_poison_execution(
        self,
    ) -> None:
        document = _clean_document()
        source_bytes = serialize_pmx(document)
        bad = _unknown_reference_request()
        good = _forward_reference_request("recovery")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pmx"
            source.write_bytes(source_bytes)

            planning_failures: list[dict[str, object]] = []
            for name in ("planning-before.pmx", "planning-after.pmx"):
                if planning_failures:
                    successful = root / "planning-success.pmx"
                    result = apply_structural_transaction(
                        source,
                        successful,
                        good,
                    )
                    self.assertEqual(load_pmx(successful), result.document)
                destination = root / name
                with self.assertRaises(PmxServiceError) as raised:
                    apply_structural_transaction(source, destination, bad)
                planning_failures.append(raised.exception.to_dict())
                self.assertFalse(destination.exists())
                self.assertEqual(_temporary_outputs(destination), ())
            self.assertEqual(planning_failures[0], planning_failures[1])

            publication_failures: list[dict[str, object]] = []
            for name in ("publish-before.pmx", "publish-after.pmx"):
                if publication_failures:
                    successful = root / "publish-success.pmx"
                    result = apply_structural_transaction(
                        source,
                        successful,
                        good,
                    )
                    self.assertEqual(load_pmx(successful), result.document)
                destination = root / name
                with patch.object(
                    edit_output,
                    "_publish_no_clobber",
                    side_effect=PermissionError(13, "private CP24 path"),
                ):
                    with self.assertRaises(PmxServiceError) as raised:
                        apply_structural_transaction(source, destination, good)
                publication_failures.append(raised.exception.to_dict())
                self.assertFalse(destination.exists())
                self.assertEqual(_temporary_outputs(destination), ())
            self.assertEqual(publication_failures[0], publication_failures[1])
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
