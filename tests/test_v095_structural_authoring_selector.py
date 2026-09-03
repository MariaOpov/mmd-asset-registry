"""v0.9.5 exact selector contracts for structural authoring."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import inspect
import io
import unittest
from unittest.mock import patch

import mmd_registry.services as services
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.services import structural_authoring_selector as selector
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_morph,
    build_pmx_rigid_body,
    build_pmx_structure,
)


def _document():
    source = build_pmx_structure(
        deform_types=(0, 1),
        surface_indices=(),
        texture_paths=(r"textures\Face.png", "テクスチャ/目.png"),
        materials=(
            build_pmx_material(
                local_name="顔",
                universal_name="Face",
                texture_index=0,
                surface_index_count=0,
            ),
        ),
        bones=(
            build_pmx_bone(
                local_name="右腕",
                universal_name="Right Arm",
                parent_bone_index=-1,
            ),
            build_pmx_bone(
                local_name="左腕",
                universal_name="Left Arm",
                parent_bone_index=-1,
            ),
        ),
        morphs=(
            build_pmx_morph(
                local_name="まばたき",
                universal_name="Blink",
                panel=1,
                morph_type=1,
                offsets=(),
            ),
        ),
        rigid_bodies=(
            build_pmx_rigid_body(
                local_name="右腕剛体",
                universal_name="Right Arm Body",
                bone_index=0,
                shape=1,
                physics_mode=0,
            ),
        ),
    )
    return services.load_document(io.BytesIO(source))


class StructuralAuthoringSelectorTests(unittest.TestCase):
    def test_source_index_is_strict_and_compiles_to_exact_index(self) -> None:
        result = selector.resolve_structural_authoring_selector(
            _document(),
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.VERTEX,
                field=selector.PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
                value=1,
            ),
        )
        self.assertEqual(
            result.to_dict(),
            {
                "outcome": "resolved",
                "target_kind": "vertex",
                "source_index": 1,
                "matched_by": "source_index",
            },
        )

        with self.assertRaises(TypeError):
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.VERTEX,
                field=selector.PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
                value=True,
            )
        with self.assertRaises(ValueError):
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.VERTEX,
                field=selector.PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
                value=-1,
            )

    def test_named_selectors_use_exact_local_and_universal_equality(self) -> None:
        document = _document()
        local = selector.resolve_structural_authoring_selector(
            document,
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.BONE,
                field=selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                value="右腕",
            ),
        )
        universal = selector.resolve_structural_authoring_selector(
            document,
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.BONE,
                field=selector.PmxStructuralAuthoringSelectorField.UNIVERSAL_NAME,
                value="Right Arm",
            ),
        )
        self.assertEqual(local.source_index, 0)
        self.assertEqual(universal.source_index, 0)

        for nonmatch in ("right arm", "Right Arm ", " Right Arm", "arm"):
            with self.subTest(nonmatch=nonmatch):
                with self.assertRaises(
                    selector.PmxStructuralAuthoringSelectorServiceError
                ) as raised:
                    selector.resolve_structural_authoring_selector(
                        document,
                        selector.PmxStructuralAuthoringSelector(
                            target_kind=PmxReferenceTargetKind.BONE,
                            field=(
                                selector
                                .PmxStructuralAuthoringSelectorField
                                .UNIVERSAL_NAME
                            ),
                            value=nonmatch,
                        ),
                    )
                self.assertEqual(
                    raised.exception.to_dict()["code"],
                    "selector_not_found",
                )

    def test_texture_path_is_raw_and_never_path_normalized(self) -> None:
        document = _document()
        resolved = selector.resolve_structural_authoring_selector(
            document,
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.TEXTURE,
                field=selector.PmxStructuralAuthoringSelectorField.PATH,
                value=r"textures\Face.png",
            ),
        )
        self.assertEqual(resolved.source_index, 0)

        with self.assertRaises(
            selector.PmxStructuralAuthoringSelectorServiceError
        ) as raised:
            selector.resolve_structural_authoring_selector(
                document,
                selector.PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.TEXTURE,
                    field=selector.PmxStructuralAuthoringSelectorField.PATH,
                    value="textures/Face.png",
                ),
            )
        self.assertEqual(
            raised.exception.to_dict()["code"],
            "selector_not_found",
        )

    def test_selector_field_matrix_is_explicit_and_fail_closed(self) -> None:
        invalid = (
            (
                PmxReferenceTargetKind.VERTEX,
                selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                "x",
            ),
            (
                PmxReferenceTargetKind.TEXTURE,
                selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                "x",
            ),
            (
                PmxReferenceTargetKind.BONE,
                selector.PmxStructuralAuthoringSelectorField.PATH,
                "x",
            ),
        )
        for target_kind, field, value in invalid:
            with self.subTest(target_kind=target_kind, field=field):
                with self.assertRaises(ValueError):
                    selector.PmxStructuralAuthoringSelector(
                        target_kind=target_kind,
                        field=field,
                        value=value,
                    )

    def test_empty_text_is_rejected_without_trim_or_fallback(self) -> None:
        with self.assertRaises(ValueError):
            selector.PmxStructuralAuthoringSelector(
                target_kind=PmxReferenceTargetKind.MATERIAL,
                field=selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                value="",
            )

        with self.assertRaises(
            selector.PmxStructuralAuthoringSelectorServiceError
        ) as raised:
            selector.resolve_structural_authoring_selector(
                _document(),
                selector.PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.MATERIAL,
                    field=selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                    value=" ",
                ),
            )
        self.assertEqual(
            raised.exception.to_dict()["code"],
            "selector_not_found",
        )

    def test_out_of_range_index_is_not_found_and_value_is_not_disclosed(self) -> None:
        with self.assertRaises(
            selector.PmxStructuralAuthoringSelectorServiceError
        ) as raised:
            selector.resolve_structural_authoring_selector(
                _document(),
                selector.PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.BONE,
                    field=(
                        selector
                        .PmxStructuralAuthoringSelectorField
                        .SOURCE_INDEX
                    ),
                    value=999999,
                ),
            )
        payload = raised.exception.to_dict()
        self.assertEqual(payload["code"], "selector_not_found")
        self.assertNotIn("999999", str(payload))

    def test_ambiguity_never_chooses_first_match(self) -> None:
        document = _document()
        duplicate = replace(
            document.bones[1],
            local_name="右腕",
            universal_name="Other",
        )
        ambiguous_document = replace(
            document,
            bones=(document.bones[0], duplicate),
        )

        with self.assertRaises(
            selector.PmxStructuralAuthoringSelectorServiceError
        ) as raised:
            selector.resolve_structural_authoring_selector(
                ambiguous_document,
                selector.PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.BONE,
                    field=selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                    value="右腕",
                ),
            )

        payload = raised.exception.to_dict()
        self.assertEqual(payload["code"], "selector_ambiguous")
        self.assertEqual(
            payload["details"],
            {
                "target_kind": "bone",
                "matched_by": "local_name",
                "candidate_count": 2,
                "candidate_source_indices": [0, 1],
            },
        )
        self.assertNotIn("右腕", str(payload))

    def test_ambiguity_candidates_are_bounded_and_source_ordered(self) -> None:
        document = _document()
        repeated = replace(document.bones[0], local_name="duplicate")
        large_document = replace(
            document,
            bones=(repeated,) * 105,
        )
        with self.assertRaises(
            selector.PmxStructuralAuthoringSelectorServiceError
        ) as raised:
            selector.resolve_structural_authoring_selector(
                large_document,
                selector.PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.BONE,
                    field=selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
                    value="duplicate",
                ),
            )
        details = raised.exception.to_dict()["details"]
        self.assertEqual(details["candidate_count"], 105)
        self.assertEqual(
            details["candidate_source_indices"],
            list(range(100)),
        )
        self.assertTrue(details["candidates_truncated"])

    def test_resolution_is_frozen_repeatable_and_has_no_source_identity(self) -> None:
        document = _document()
        authored = selector.PmxStructuralAuthoringSelector(
            target_kind=PmxReferenceTargetKind.MORPH,
            field=selector.PmxStructuralAuthoringSelectorField.UNIVERSAL_NAME,
            value="Blink",
        )
        first = selector.resolve_structural_authoring_selector(
            document,
            authored,
        )
        second = selector.resolve_structural_authoring_selector(
            document,
            authored,
        )
        self.assertEqual(first, second)
        self.assertNotIn("path", first.to_dict())
        self.assertNotIn("sha256", first.to_dict())
        with self.assertRaises(FrozenInstanceError):
            first.source_index = 99  # type: ignore[misc]

    def test_service_rejects_wrong_arguments_with_redacted_diagnostic(self) -> None:
        secret = "SECRET_SELECTOR_VALUE"
        with self.assertRaises(
            selector.PmxStructuralAuthoringSelectorServiceError
        ) as raised:
            selector.resolve_structural_authoring_selector(
                object(),  # type: ignore[arg-type]
                secret,  # type: ignore[arg-type]
            )
        self.assertEqual(
            raised.exception.to_dict(),
            {
                "code": "invalid_argument",
                "operation": "resolve_structural_authoring_selector",
                "message": "Invalid structural authoring selector input.",
            },
        )
        self.assertNotIn(secret, str(raised.exception.to_dict()))

    def test_service_is_cli_search_execution_and_filesystem_independent(self) -> None:
        source = inspect.getsource(selector)
        for forbidden in (
            "transaction_plan_cli",
            "bone_search",
            "casefold",
            ".strip(",
            "unicodedata",
            "structural_output",
            "index_remap",
            "apply_structural",
            "write_pmx",
            "load_document",
            "Path(",
            ".open(",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

        self.assertNotIn(
            "resolve_structural_authoring_selector",
            services.__all__,
        )

    def test_process_control_exceptions_escape(self) -> None:
        authored = selector.PmxStructuralAuthoringSelector(
            target_kind=PmxReferenceTargetKind.BONE,
            field=selector.PmxStructuralAuthoringSelectorField.LOCAL_NAME,
            value="右腕",
        )
        with patch.object(
            selector,
            "_matching_source_indices",
            side_effect=KeyboardInterrupt(),
        ):
            with self.assertRaises(KeyboardInterrupt):
                selector.resolve_structural_authoring_selector(
                    _document(),
                    authored,
                )


if __name__ == "__main__":
    unittest.main()
