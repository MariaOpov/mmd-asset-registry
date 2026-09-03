"""CLI adapters for structural transaction-plan authoring."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Final

from mmd_registry.diagnostics import (
    PmxServiceDiagnosticCode,
    PmxServiceError,
)
from mmd_registry.pmx.reference_model import PmxReferenceTargetKind
from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlanExplanation,
    get_pmx_structural_transaction_plan_template,
    render_pmx_structural_transaction_plan_json,
)
from mmd_registry.services import load_document
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringCatalogPage,
    PmxStructuralAuthoringCatalogServiceDiagnosticCode,
    PmxStructuralAuthoringCatalogServiceError,
    PmxStructuralAuthoringCatalogSummary,
    inspect_structural_authoring_catalog,
    summarize_structural_authoring_catalog,
)
from mmd_registry.services.structural_authoring_diff import (
    PmxStructuralAuthoringDiff,
    PmxStructuralAuthoringDiffServiceError,
    build_structural_authoring_diff,
)
from mmd_registry.services.structural_authoring_builder import (
    PmxStructuralAuthoringBuilderServiceError,
    build_structural_authoring_plan,
    compile_structural_authoring_insert_before,
    render_structural_authoring_plan,
)
from mmd_registry.services.structural_authoring_selector import (
    PmxStructuralAuthoringSelector,
    PmxStructuralAuthoringSelectorField,
    PmxStructuralAuthoringSelectorServiceError,
    resolve_structural_authoring_selector,
)
from mmd_registry.services.structural_texture import (
    PmxStructuralTextureInsertion,
)
from mmd_registry.services.structural_transaction_plan import (
    PmxStructuralTransactionPlanServiceDiagnosticCode,
    PmxStructuralTransactionPlanServiceError,
    PmxStructuralTransactionPlanValidationResult,
    explain_structural_transaction_plan,
    load_structural_transaction_plan,
)
from mmd_registry.services.structural_transaction_plan_preview import (
    PmxStructuralTransactionPlanPreviewServiceDiagnosticCode,
    PmxStructuralTransactionPlanPreviewServiceError,
    PmxStructuralTransactionPlanPreviewResult,
    preview_structural_transaction_plan,
)
from mmd_registry.services.structural_transaction_plan_apply import (
    PmxStructuralTransactionPlanApplyServiceDiagnosticCode,
    PmxStructuralTransactionPlanApplyServiceError,
    PmxStructuralTransactionPlanApplyResult,
    apply_structural_transaction_plan,
)


TRANSACTION_PLAN_COMMAND_NAME: Final[str] = "transaction-plan"
_TRANSACTION_PLAN_ACTIONS: Final[tuple[str, ...]] = (
    "template",
    "inspect",
    "build",
    "validate",
    "explain",
    "preview",
    "apply",
)


def _top_level_subparsers(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction:
    actions = [
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]
    if len(actions) != 1:
        raise RuntimeError(
            "runtime parser must contain exactly one top-level subparser action."
        )
    return actions[0]


def add_transaction_plan_parser(parser: argparse.ArgumentParser) -> None:
    """Add the additive transaction-plan authoring, preview, and apply command."""

    subparsers = _top_level_subparsers(parser)
    if TRANSACTION_PLAN_COMMAND_NAME in subparsers.choices:
        raise RuntimeError("transaction-plan parser is already registered.")

    transaction_plan_parser = subparsers.add_parser(
        TRANSACTION_PLAN_COMMAND_NAME,
        help=(
            "Inspect models and author, validate, explain, preview, and "
            "apply structural transaction plans."
        ),
        description=(
            "Inspect one PMX through the bounded read-only authoring catalog, "
            "generate a safe empty structural transaction-plan template, "
            "validate or explain one strict UTF-8 JSON plan, preview it "
            "against one source-bound PMX snapshot, or atomically apply it "
            "through the released structural transaction authority."
        ),
    )
    action_subparsers = transaction_plan_parser.add_subparsers(
        dest="transaction_plan_action",
        metavar="ACTION",
        required=True,
    )

    action_subparsers.add_parser(
        "template",
        help="Print a safe empty schema-one structural transaction-plan template.",
    )

    inspect_parser = action_subparsers.add_parser(
        "inspect",
        help="Inspect one PMX through the bounded structural authoring catalog.",
    )
    inspect_parser.add_argument(
        "source",
        metavar="SOURCE",
        help="Path to the PMX source loaded through the stable document service.",
    )
    inspect_parser.add_argument(
        "--kind",
        choices=tuple(kind.value for kind in PmxReferenceTargetKind),
        default=None,
        help="Show one bounded target-kind page; omit for counts-only summary.",
    )
    inspect_parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Zero-based source-index offset for a detailed page.",
    )
    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Detailed page size from 1 through 1000.",
    )
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Print deterministic Unicode-safe catalog JSON.",
    )

    build_parser = action_subparsers.add_parser(
        "build",
        help=(
            "Build one canonical schema-one plan from bounded "
            "human-friendly authoring input."
        ),
    )
    build_kind_subparsers = build_parser.add_subparsers(
        dest="transaction_plan_build_kind",
        metavar="KIND",
        required=True,
    )
    build_texture_parser = build_kind_subparsers.add_parser(
        "texture",
        help="Build one texture insertion plan.",
    )
    build_texture_parser.add_argument(
        "source",
        metavar="SOURCE",
        help=(
            "Path to the PMX source used only for exact selector resolution "
            "and source validation."
        ),
    )
    build_texture_parser.add_argument(
        "--path",
        required=True,
        help="Exact new texture path stored in the schema-one insertion.",
    )
    anchor_group = build_texture_parser.add_mutually_exclusive_group()
    anchor_group.add_argument(
        "--before-index",
        type=int,
        default=None,
        help="Insert before one exact captured-source texture index.",
    )
    anchor_group.add_argument(
        "--before-path",
        default=None,
        help="Insert before one exact captured-source texture path.",
    )
    build_texture_parser.add_argument(
        "--new-id",
        default=None,
        help="Optional request-local schema-one identity.",
    )
    build_texture_parser.add_argument(
        "--expected-source-sha256",
        default=None,
        help=(
            "Optional lowercase SHA-256 declaration passed through to the "
            "schema-one plan; the CLI never computes it."
        ),
    )

    validate_parser = action_subparsers.add_parser(
        "validate",
        help="Validate one strict structural transaction-plan JSON file.",
    )
    validate_parser.add_argument(
        "plan",
        metavar="PLAN",
        help="Path to the strict UTF-8 JSON transaction plan.",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print stable Unicode-safe JSON validation evidence.",
    )

    explain_parser = action_subparsers.add_parser(
        "explain",
        help="Explain one structural transaction plan without executing it.",
    )
    explain_parser.add_argument(
        "plan",
        metavar="PLAN",
        help="Path to the strict UTF-8 JSON transaction plan.",
    )
    explain_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the value-free explanation as stable Unicode-safe JSON.",
    )

    preview_parser = action_subparsers.add_parser(
        "preview",
        help="Preview one plan against one captured source PMX snapshot.",
    )
    preview_parser.add_argument(
        "source",
        metavar="SOURCE",
        help="Path to the source PMX file captured once for preview.",
    )
    preview_parser.add_argument(
        "plan",
        metavar="PLAN",
        help="Path to the strict UTF-8 JSON transaction plan.",
    )
    preview_parser.add_argument(
        "--diff",
        action="store_true",
        help=(
            "Project the single certified preview into bounded rich diff "
            "evidence; never performs a second preview."
        ),
    )
    preview_parser.add_argument(
        "--json",
        action="store_true",
        help="Print source-bound released preview evidence as stable JSON.",
    )

    apply_parser = action_subparsers.add_parser(
        "apply",
        help="Atomically apply one source-bound structural transaction plan.",
    )
    apply_parser.add_argument(
        "source",
        metavar="SOURCE",
        help="Path to the source PMX file captured by the atomic writer.",
    )
    apply_parser.add_argument(
        "plan",
        metavar="PLAN",
        help="Path to the strict UTF-8 JSON transaction plan.",
    )
    apply_parser.add_argument(
        "output",
        metavar="OUTPUT",
        help="Path to the distinct structural transaction output PMX.",
    )
    apply_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace an existing separate output path.",
    )
    apply_parser.add_argument(
        "--json",
        action="store_true",
        help="Print bounded committed apply evidence as stable JSON.",
    )


def _render_json(payload: dict[str, object]) -> str:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    )


def _render_catalog_summary_text(
    result: PmxStructuralAuthoringCatalogSummary,
) -> str:
    counts = result.to_dict()["counts"]
    if not isinstance(counts, dict):
        raise RuntimeError("catalog summary counts must be a dictionary.")
    return "\n".join(
        (
            "STRUCTURAL AUTHORING CATALOG",
            f"Vertices: {counts['vertex']}",
            f"Textures: {counts['texture']}",
            f"Materials: {counts['material']}",
            f"Bones: {counts['bone']}",
            f"Morphs: {counts['morph']}",
            f"Rigid bodies: {counts['rigid_body']}",
            "Detailed entries: no",
            "",
        )
    )


def _render_catalog_entry_text(
    target_kind: PmxReferenceTargetKind,
    payload: dict[str, object],
) -> str:
    source_index = payload["source_index"]
    if target_kind is PmxReferenceTargetKind.VERTEX:
        return (
            f"[{source_index}] position={payload['position']!r} "
            f"deform_type={payload['deform_type']}"
        )
    if target_kind is PmxReferenceTargetKind.TEXTURE:
        return f"[{source_index}] path={payload['path']!r}"
    return (
        f"[{source_index}] local_name={payload['local_name']!r} "
        f"universal_name={payload['universal_name']!r}"
    )


def _render_catalog_page_text(
    result: PmxStructuralAuthoringCatalogPage,
) -> str:
    lines = [
        "STRUCTURAL AUTHORING CATALOG",
        f"Target kind: {result.target_kind.value}",
        f"Total: {result.total_count}",
        f"Offset: {result.offset}",
        f"Limit: {result.limit}",
        f"Returned: {result.returned_count}",
    ]
    for entry in result.entries:
        lines.append(
            _render_catalog_entry_text(result.target_kind, entry.to_dict())
        )
    lines.append("")
    return "\n".join(lines)


def _document_failure_policy(
    error: PmxServiceError,
) -> tuple[str, int]:
    code = error.diagnostic.code
    if code is PmxServiceDiagnosticCode.SOURCE_INVALID:
        return "source_invalid", 1
    if code is PmxServiceDiagnosticCode.IO_FAILED:
        return "io", 2
    if code is PmxServiceDiagnosticCode.INVALID_ARGUMENT:
        return "usage", 2
    return "internal", 3


def _catalog_failure_policy(
    error: PmxStructuralAuthoringCatalogServiceError,
) -> tuple[str, int]:
    if (
        error.diagnostic.code
        is PmxStructuralAuthoringCatalogServiceDiagnosticCode.INVALID_ARGUMENT
    ):
        return "usage", 2
    return "internal", 3


def _print_inspect_error(
    *,
    error: PmxServiceError | PmxStructuralAuthoringCatalogServiceError,
    json_output: bool,
) -> int:
    if isinstance(error, PmxServiceError):
        error_type, exit_code = _document_failure_policy(error)
    else:
        error_type, exit_code = _catalog_failure_policy(error)
    if json_output:
        sys.stdout.write(
            _render_json(
                {
                    "status": "error",
                    "command": TRANSACTION_PLAN_COMMAND_NAME,
                    "action": "inspect",
                    "error_type": error_type,
                    "errors": [error.diagnostic.message],
                    "error": error.to_dict(),
                }
            )
        )
    else:
        print(
            (
                f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} inspect: "
                f"{error.diagnostic.message}"
            ),
            file=sys.stderr,
        )
    return exit_code


def _render_validation_text(
    result: PmxStructuralTransactionPlanValidationResult,
) -> str:
    return "\n".join(
        (
            "STRUCTURAL TRANSACTION PLAN VALID",
            f"Schema version: {result.schema_version}",
            f"Operations: {result.operation_count}",
            (
                "Expected source SHA-256 declared: "
                + ("yes" if result.expected_source_sha256_declared else "no")
            ),
            "",
        )
    )


def _render_explanation_text(
    explanation: PmxStructuralTransactionPlanExplanation,
) -> str:
    lines = [
        "STRUCTURAL TRANSACTION PLAN EXPLANATION",
        f"Schema version: {explanation.schema_version}",
        f"Operations: {explanation.operation_count}",
        (
            "Expected source SHA-256 declared: "
            + ("yes" if explanation.expected_source_sha256_declared else "no")
        ),
    ]

    for item in explanation.operations:
        fields = (
            ", ".join(item.canonical_fields)
            if item.canonical_fields
            else "(none)"
        )
        lines.extend(
            (
                "",
                f"[{item.operation_index}] {item.operation_type.value}",
                f"    Purpose: {item.purpose}",
                f"    Fields: {fields}",
            )
        )

    return "\n".join(lines) + "\n"


def _render_preview_text(
    result: PmxStructuralTransactionPlanPreviewResult,
) -> str:
    payload = result.to_dict()
    effects = payload["effects"]
    if not isinstance(effects, dict):
        raise RuntimeError("preview effects must be a dictionary.")
    changed_targets = effects["changed_targets"]
    if not isinstance(changed_targets, list):
        raise RuntimeError("preview changed_targets must be a list.")
    changed = ", ".join(changed_targets) if changed_targets else "(none)"
    return "\n".join(
        (
            "STRUCTURAL TRANSACTION PLAN PREVIEW",
            f"Status: {result.status}",
            f"Source identity: {result.source_identity_status}",
            f"Changed targets: {changed}",
            f"Inserted: {effects['inserted_count']}",
            f"Deleted: {effects['deleted_count']}",
            f"Reordered targets: {effects['reordered_target_count']}",
            "Output written: no",
            "",
        )
    )


def _render_rich_diff_text(
    result: PmxStructuralAuthoringDiff,
) -> str:
    changed = (
        ", ".join(item.value for item in result.changed_targets)
        if result.changed_targets
        else "(none)"
    )
    lines = [
        "STRUCTURAL TRANSACTION PLAN DIFF",
        f"Status: {result.status}",
        f"Source identity: {result.source_identity_status}",
        f"Changed targets: {changed}",
        f"Inserted: {result.inserted_count}",
        f"Deleted: {result.deleted_count}",
        f"Reordered targets: {result.reordered_target_count}",
        "Collections:",
    ]

    changed_collections = tuple(
        item for item in result.collections if item.changed
    )
    if not changed_collections:
        lines.append("    (none)")
    for collection in changed_collections:
        delta = collection.count_delta
        delta_label = f"+{delta}" if delta >= 0 else str(delta)
        lines.append(
            (
                f"    {collection.target_kind.value}: "
                f"{collection.captured_count} -> {collection.final_count} "
                f"({delta_label}); inserted={collection.inserted_count}, "
                f"deleted={collection.deleted_count}, "
                f"reordered={'yes' if collection.reordered else 'no'}"
            )
        )
        for insertion in collection.insertions:
            lines.append(
                (
                    f"        request #{insertion.request_ordinal} "
                    f"-> final #{insertion.final_index}"
                )
            )

    dependency_order = (
        ", ".join(
            item.value for item in result.dependency_materialization_order
        )
        if result.dependency_materialization_order
        else "(none)"
    )
    lines.extend(
        (
            (
                "Resolved local references: "
                f"{result.resolved_local_reference_count}"
            ),
            (
                "Remapped existing references: "
                f"{result.remapped_existing_reference_count}"
            ),
            f"Materialization order: {dependency_order}",
            (
                "Capacity representable: "
                + ("yes" if result.capacity_all_representable else "no")
            ),
            "Output written: no",
            "",
        )
    )
    return "\n".join(lines)


def _print_rich_diff_service_error(
    *,
    error: PmxStructuralAuthoringDiffServiceError,
    json_output: bool,
) -> int:
    message = "Certified structural preview diff projection failed."
    if json_output:
        sys.stdout.write(
            _render_json(
                {
                    "status": "error",
                    "command": TRANSACTION_PLAN_COMMAND_NAME,
                    "action": "preview",
                    "error_type": "diff_projection_failed",
                    "errors": [message],
                    "error": error.to_dict(),
                }
            )
        )
    else:
        print(
            (
                f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} preview: "
                f"{message}"
            ),
            file=sys.stderr,
        )
    return 3


def _print_build_error(
    *,
    error: (
        PmxServiceError
        | PmxStructuralAuthoringSelectorServiceError
        | PmxStructuralAuthoringBuilderServiceError
        | TypeError
        | ValueError
    ),
) -> int:
    if isinstance(error, PmxServiceError):
        error_type, exit_code = _document_failure_policy(error)
        message = error.diagnostic.message
    elif isinstance(error, PmxStructuralAuthoringSelectorServiceError):
        code = error.diagnostic.code.value
        exit_code = 2 if code == "invalid_argument" else 1
        message = error.diagnostic.message
    elif isinstance(error, PmxStructuralAuthoringBuilderServiceError):
        exit_code = 1
        message = error.diagnostic.message
    else:
        exit_code = 2
        message = "Invalid structural authoring build input."

    print(
        (
            f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} build: "
            f"{message}"
        ),
        file=sys.stderr,
    )
    return exit_code


def _render_apply_text(
    result: PmxStructuralTransactionPlanApplyResult,
) -> str:
    payload = result.to_dict()
    output = payload["output"]
    verification = payload["verification"]
    if not isinstance(output, dict):
        raise RuntimeError("apply output evidence must be a dictionary.")
    if not isinstance(verification, dict):
        raise RuntimeError("apply verification evidence must be a dictionary.")
    return "\n".join(
        (
            "STRUCTURAL TRANSACTION PLAN APPLY",
            f"Status: {result.status}",
            f"Source identity: {result.source_identity_status}",
            (
                "Output written: "
                + ("yes" if output.get("written") is True else "no")
            ),
            f"Output size bytes: {result.output_size_bytes}",
            (
                "Input unchanged: "
                + (
                    "yes"
                    if verification.get("input_unchanged") is True
                    else "unknown"
                )
            ),
            "",
        )
    )


def _service_failure_policy(
    error: PmxStructuralTransactionPlanServiceError,
) -> tuple[str, int]:
    code = error.diagnostic.code
    if code is PmxStructuralTransactionPlanServiceDiagnosticCode.PLAN_INVALID:
        return "invalid_plan", 1
    if code is PmxStructuralTransactionPlanServiceDiagnosticCode.IO_FAILED:
        return "io", 2
    if code is PmxStructuralTransactionPlanServiceDiagnosticCode.INVALID_ARGUMENT:
        return "usage", 2
    return "internal", 3


def _print_service_error(
    *,
    action: str,
    error: PmxStructuralTransactionPlanServiceError,
    json_output: bool,
) -> int:
    error_type, exit_code = _service_failure_policy(error)

    if json_output:
        payload = {
            "status": "error",
            "command": TRANSACTION_PLAN_COMMAND_NAME,
            "action": action,
            "error_type": error_type,
            "errors": [error.diagnostic.message],
            "error": error.to_dict(),
        }
        sys.stdout.write(_render_json(payload))
    else:
        print(
            (
                f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} {action}: "
                f"{error.diagnostic.message}"
            ),
            file=sys.stderr,
        )

    return exit_code


def _preview_failure_policy(
    error: PmxStructuralTransactionPlanPreviewServiceError,
) -> tuple[str, int]:
    code = error.diagnostic.code
    if (
        code
        is PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
        .SOURCE_IDENTITY_MISMATCH
    ):
        return "source_identity_mismatch", 1
    if (
        code
        is PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
        .SOURCE_INVALID
    ):
        return "source_invalid", 1
    if (
        code
        is PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
        .PREVIEW_FAILED
    ):
        return "preview_failed", 1
    if (
        code
        is PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
        .SOURCE_IO_FAILED
    ):
        return "io", 2
    if (
        code
        is PmxStructuralTransactionPlanPreviewServiceDiagnosticCode
        .INVALID_ARGUMENT
    ):
        return "usage", 2
    return "internal", 3


def _print_preview_service_error(
    *,
    error: PmxStructuralTransactionPlanPreviewServiceError,
    json_output: bool,
) -> int:
    error_type, exit_code = _preview_failure_policy(error)

    if json_output:
        sys.stdout.write(
            _render_json(
                {
                    "status": "error",
                    "command": TRANSACTION_PLAN_COMMAND_NAME,
                    "action": "preview",
                    "error_type": error_type,
                    "errors": [error.diagnostic.message],
                    "error": error.to_dict(),
                }
            )
        )
    else:
        print(
            (
                f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} preview: "
                f"{error.diagnostic.message}"
            ),
            file=sys.stderr,
        )

    return exit_code


def _apply_failure_policy(
    error: PmxStructuralTransactionPlanApplyServiceError,
) -> tuple[str, int]:
    code = error.diagnostic.code
    if (
        code
        is PmxStructuralTransactionPlanApplyServiceDiagnosticCode
        .SOURCE_IDENTITY_MISMATCH
    ):
        return "source_identity_mismatch", 1
    if (
        code
        is PmxStructuralTransactionPlanApplyServiceDiagnosticCode
        .SOURCE_INVALID
    ):
        return "source_invalid", 1
    if (
        code
        is PmxStructuralTransactionPlanApplyServiceDiagnosticCode
        .OUTPUT_PATH_UNSAFE
    ):
        return "output_path_unsafe", 1
    if (
        code
        is PmxStructuralTransactionPlanApplyServiceDiagnosticCode
        .EXECUTION_FAILED
    ):
        return "execution_failed", 1
    if (
        code
        is PmxStructuralTransactionPlanApplyServiceDiagnosticCode
        .IO_FAILED
    ):
        return "io", 2
    if (
        code
        is PmxStructuralTransactionPlanApplyServiceDiagnosticCode
        .INVALID_ARGUMENT
    ):
        return "usage", 2
    return "internal", 3


def _print_apply_service_error(
    *,
    error: PmxStructuralTransactionPlanApplyServiceError,
    json_output: bool,
) -> int:
    error_type, exit_code = _apply_failure_policy(error)

    if json_output:
        sys.stdout.write(
            _render_json(
                {
                    "status": "error",
                    "command": TRANSACTION_PLAN_COMMAND_NAME,
                    "action": "apply",
                    "error_type": error_type,
                    "errors": [error.diagnostic.message],
                    "error": error.to_dict(),
                }
            )
        )
    else:
        print(
            (
                f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} apply: "
                f"{error.diagnostic.message}"
            ),
            file=sys.stderr,
        )

    return exit_code


def run_transaction_plan_command(arguments: argparse.Namespace) -> int:
    """Run one structural transaction-plan authoring, preview, or apply action."""

    action = arguments.transaction_plan_action

    if action == "template":
        template = get_pmx_structural_transaction_plan_template()
        sys.stdout.write(
            render_pmx_structural_transaction_plan_json(template)
        )
        return 0

    if action == "inspect":
        try:
            document = load_document(arguments.source)
        except PmxServiceError as error:
            return _print_inspect_error(
                error=error,
                json_output=arguments.json,
            )
        try:
            if arguments.kind is None:
                result = summarize_structural_authoring_catalog(document)
            else:
                result = inspect_structural_authoring_catalog(
                    document,
                    PmxReferenceTargetKind(arguments.kind),
                    offset=arguments.offset,
                    limit=arguments.limit,
                )
        except PmxStructuralAuthoringCatalogServiceError as error:
            return _print_inspect_error(
                error=error,
                json_output=arguments.json,
            )
        if arguments.json:
            sys.stdout.write(_render_json(result.to_dict()))
        elif isinstance(result, PmxStructuralAuthoringCatalogSummary):
            sys.stdout.write(_render_catalog_summary_text(result))
        else:
            sys.stdout.write(_render_catalog_page_text(result))
        return 0

    if action == "build":
        if arguments.transaction_plan_build_kind != "texture":
            raise RuntimeError(
                "Unsupported transaction-plan build kind: "
                f"{arguments.transaction_plan_build_kind}"
            )
        try:
            document = load_document(arguments.source)
            insertion = PmxStructuralTextureInsertion(
                path=arguments.path,
                new_id=arguments.new_id,
            )
            if arguments.before_index is not None:
                selection = PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.TEXTURE,
                    field=PmxStructuralAuthoringSelectorField.SOURCE_INDEX,
                    value=arguments.before_index,
                )
                resolution = resolve_structural_authoring_selector(
                    document,
                    selection,
                )
                insertion = compile_structural_authoring_insert_before(
                    insertion,
                    resolution,
                )
            elif arguments.before_path is not None:
                selection = PmxStructuralAuthoringSelector(
                    target_kind=PmxReferenceTargetKind.TEXTURE,
                    field=PmxStructuralAuthoringSelectorField.PATH,
                    value=arguments.before_path,
                )
                resolution = resolve_structural_authoring_selector(
                    document,
                    selection,
                )
                insertion = compile_structural_authoring_insert_before(
                    insertion,
                    resolution,
                )
            plan = build_structural_authoring_plan(
                (insertion,),
                expected_source_sha256=arguments.expected_source_sha256,
            )
            sys.stdout.write(render_structural_authoring_plan(plan))
            return 0
        except (
            PmxServiceError,
            PmxStructuralAuthoringSelectorServiceError,
            PmxStructuralAuthoringBuilderServiceError,
            TypeError,
            ValueError,
        ) as error:
            return _print_build_error(error=error)

    if action not in {"validate", "explain", "preview", "apply"}:
        raise RuntimeError(f"Unsupported transaction-plan action: {action}")

    try:
        validated = load_structural_transaction_plan(arguments.plan)
    except PmxStructuralTransactionPlanServiceError as error:
        return _print_service_error(
            action=action,
            error=error,
            json_output=arguments.json,
        )

    if action == "validate":
        if arguments.json:
            sys.stdout.write(_render_json(validated.to_dict()))
        else:
            sys.stdout.write(_render_validation_text(validated))
        return 0

    if action == "preview":
        try:
            result = preview_structural_transaction_plan(
                arguments.source,
                validated,
            )
        except PmxStructuralTransactionPlanPreviewServiceError as error:
            return _print_preview_service_error(
                error=error,
                json_output=arguments.json,
            )
        if arguments.diff:
            try:
                rich_diff = build_structural_authoring_diff(result)
            except PmxStructuralAuthoringDiffServiceError as error:
                return _print_rich_diff_service_error(
                    error=error,
                    json_output=arguments.json,
                )
            if arguments.json:
                sys.stdout.write(_render_json(rich_diff.to_dict()))
            else:
                sys.stdout.write(_render_rich_diff_text(rich_diff))
        elif arguments.json:
            sys.stdout.write(_render_json(result.to_dict()))
        else:
            sys.stdout.write(_render_preview_text(result))
        return 0

    if action == "apply":
        try:
            result = apply_structural_transaction_plan(
                arguments.source,
                arguments.output,
                validated,
                overwrite=arguments.overwrite,
            )
        except PmxStructuralTransactionPlanApplyServiceError as error:
            return _print_apply_service_error(
                error=error,
                json_output=arguments.json,
            )
        if arguments.json:
            sys.stdout.write(_render_json(result.to_dict()))
        else:
            sys.stdout.write(_render_apply_text(result))
        return 0

    try:
        explanation = explain_structural_transaction_plan(validated.plan)
    except PmxStructuralTransactionPlanServiceError as error:
        return _print_service_error(
            action=action,
            error=error,
            json_output=arguments.json,
        )

    if arguments.json:
        sys.stdout.write(_render_json(explanation.to_dict()))
    else:
        sys.stdout.write(_render_explanation_text(explanation))
    return 0


def print_unexpected_transaction_plan_error(
    *,
    action: str | None,
    json_output: bool,
) -> None:
    """Render one process-boundary failure without exception internals."""

    action_label = action if action in _TRANSACTION_PLAN_ACTIONS else "unknown"
    message = "Unexpected internal transaction-plan failure."

    if json_output:
        sys.stdout.write(
            _render_json(
                {
                    "status": "error",
                    "command": TRANSACTION_PLAN_COMMAND_NAME,
                    "action": action_label,
                    "error_type": "internal",
                    "errors": [message],
                }
            )
        )
        return

    print(
        (
            f"[ERROR] {TRANSACTION_PLAN_COMMAND_NAME} "
            f"{action_label}: {message}"
        ),
        file=sys.stderr,
    )


__all__ = (
    "TRANSACTION_PLAN_COMMAND_NAME",
    "add_transaction_plan_parser",
    "run_transaction_plan_command",
    "print_unexpected_transaction_plan_error",
)
