"""CLI adapters for structural transaction-plan authoring."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Final

from mmd_registry.pmx.transaction_plan import (
    PmxStructuralTransactionPlanExplanation,
    get_pmx_structural_transaction_plan_template,
    render_pmx_structural_transaction_plan_json,
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


TRANSACTION_PLAN_COMMAND_NAME: Final[str] = "transaction-plan"
_TRANSACTION_PLAN_ACTIONS: Final[tuple[str, ...]] = (
    "template",
    "validate",
    "explain",
    "preview",
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
    """Add the additive transaction-plan authoring and preview command."""

    subparsers = _top_level_subparsers(parser)
    if TRANSACTION_PLAN_COMMAND_NAME in subparsers.choices:
        raise RuntimeError("transaction-plan parser is already registered.")

    transaction_plan_parser = subparsers.add_parser(
        TRANSACTION_PLAN_COMMAND_NAME,
        help="Author, validate, explain, and preview structural transaction plans.",
        description=(
            "Generate a safe empty structural transaction-plan template, "
            "validate or explain one strict UTF-8 JSON plan, or preview it "
            "against one source-bound PMX snapshot without publication."
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
        "--json",
        action="store_true",
        help="Print source-bound released preview evidence as stable JSON.",
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


def run_transaction_plan_command(arguments: argparse.Namespace) -> int:
    """Run one structural transaction-plan authoring or preview action."""

    action = arguments.transaction_plan_action

    if action == "template":
        template = get_pmx_structural_transaction_plan_template()
        sys.stdout.write(
            render_pmx_structural_transaction_plan_json(template)
        )
        return 0

    if action not in {"validate", "explain", "preview"}:
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
        if arguments.json:
            sys.stdout.write(_render_json(result.to_dict()))
        else:
            sys.stdout.write(_render_preview_text(result))
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
