"""CLI adapter for v0.9.5.5 read-only Smart Inspect."""

from __future__ import annotations

import argparse
import sys
from typing import Final

from mmd_registry.diagnostics import PmxServiceDiagnosticCode, PmxServiceError
from mmd_registry.services._smart_inspection import (
    SmartInspectionResult,
    inspect_smart_parts,
)
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringCatalogServiceDiagnosticCode,
    PmxStructuralAuthoringCatalogServiceError,
)
from mmd_registry.smart_part_confidence import (
    SmartPartConfidence,
    SmartPartConfidenceAssessment,
    SmartPartConfidenceCandidate,
)
from mmd_registry.smart_part_explainability import (
    SmartPartEvidenceExplanation,
    SmartPartExplanation,
)
from mmd_registry.smart_parts import SmartPartKind


SMART_COMMAND_NAME: Final[str] = "smart"

_DISPLAY_LABELS: Final[dict[SmartPartKind, str]] = {
    SmartPartKind.EYES: "Eyes",
    SmartPartKind.HAIR: "Hair",
    SmartPartKind.FACE: "Face",
    SmartPartKind.SKIN: "Skin",
    SmartPartKind.CHEST: "Chest",
    SmartPartKind.UPPER_BODY: "Upper body",
    SmartPartKind.LOWER_BODY: "Lower body",
    SmartPartKind.ARMS: "Arms",
    SmartPartKind.HANDS: "Hands",
    SmartPartKind.LEGS: "Legs",
    SmartPartKind.FEET: "Feet",
    SmartPartKind.CLOTHING: "Clothes",
    SmartPartKind.SHOES: "Shoes",
    SmartPartKind.ACCESSORIES: "Accessories",
    SmartPartKind.MATERIALS: "Materials",
}
_SMART_PART_ORDER: Final[tuple[SmartPartKind, ...]] = tuple(SmartPartKind)


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


def add_smart_parser(parser: argparse.ArgumentParser) -> None:
    """Add the runtime-only read-only Smart command."""

    subparsers = _top_level_subparsers(parser)
    if SMART_COMMAND_NAME in subparsers.choices:
        raise RuntimeError("smart parser is already registered.")

    smart_parser = subparsers.add_parser(
        SMART_COMMAND_NAME,
        help="Inspect PMX models through deterministic Smart semantic analysis.",
        description=(
            "Analyze one PMX through the existing deterministic Smart Part "
            "detector, explainability, and confidence authorities without "
            "modifying the model."
        ),
    )
    smart_actions = smart_parser.add_subparsers(
        dest="smart_action",
        metavar="ACTION",
        required=True,
    )

    inspect_parser = smart_actions.add_parser(
        "inspect",
        help="Show deterministic read-only semantic Smart Parts.",
    )
    inspect_parser.add_argument(
        "source",
        metavar="SOURCE",
        help="Path to the PMX source model.",
    )


def _document_failure_policy(error: PmxServiceError) -> int:
    code = error.diagnostic.code
    if code is PmxServiceDiagnosticCode.SOURCE_INVALID:
        return 1
    if code in {
        PmxServiceDiagnosticCode.IO_FAILED,
        PmxServiceDiagnosticCode.INVALID_ARGUMENT,
    }:
        return 2
    return 3


def _catalog_failure_policy(
    error: PmxStructuralAuthoringCatalogServiceError,
) -> int:
    if (
        error.diagnostic.code
        is PmxStructuralAuthoringCatalogServiceDiagnosticCode.INVALID_ARGUMENT
    ):
        return 2
    return 3


def _print_inspect_error(
    error: PmxServiceError | PmxStructuralAuthoringCatalogServiceError,
) -> int:
    if isinstance(error, PmxServiceError):
        exit_code = _document_failure_policy(error)
    else:
        exit_code = _catalog_failure_policy(error)
    print(
        f"[ERROR] smart inspect: {error.diagnostic.message}",
        file=sys.stderr,
    )
    return exit_code


def _assessment_sort_key(
    assessment: SmartPartConfidenceAssessment,
) -> int:
    return _SMART_PART_ORDER.index(assessment.candidates[0].kind)


def _assessment_label(
    assessment: SmartPartConfidenceAssessment,
) -> str:
    return " / ".join(
        _DISPLAY_LABELS[candidate.kind]
        for candidate in assessment.candidates
    )


def _quote_evidence_text(value: str) -> str:
    if type(value) is not str:
        raise TypeError("evidence text must be a string.")
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def _render_evidence_item(item: SmartPartEvidenceExplanation) -> str:
    """Render one concise line directly from explainability-authority provenance."""

    if not isinstance(item, SmartPartEvidenceExplanation):
        raise TypeError("item must be a SmartPartEvidenceExplanation value.")
    return (
        f"    {item.evidence.source_kind.value}[{item.evidence.source_index}] "
        f"{item.source_field}={_quote_evidence_text(item.source_value)} "
        f"exact_alias={_quote_evidence_text(item.matched_alias)}"
    )


def _resolved_explanation(
    result: SmartInspectionResult,
    assessment: SmartPartConfidenceAssessment,
) -> SmartPartExplanation | None:
    if len(assessment.candidates) != 1:
        return None

    kind = assessment.candidates[0].kind
    matches = tuple(
        explanation
        for explanation in result.explanations
        if explanation.kind is kind
    )
    if len(matches) != 1:
        raise RuntimeError(
            "Smart Inspect resolved assessment/explanation provenance mismatch."
        )
    return matches[0]


def _render_ambiguous_candidate(
    candidate: SmartPartConfidenceCandidate,
) -> tuple[str, ...]:
    """Render one ambiguity candidate without resolving or reclassifying it."""

    if not isinstance(candidate, SmartPartConfidenceCandidate):
        raise TypeError("candidate must be a SmartPartConfidenceCandidate value.")

    return (
        f"    {_DISPLAY_LABELS[candidate.kind]}",
        "      Evidence:",
        *tuple(
            f"    {_render_evidence_item(item)}"
            for item in candidate.evidence
        ),
    )


def _render_basic_text(result: SmartInspectionResult) -> str:
    lines = ["SMART PART INSPECTION"]

    if not result.assessments:
        lines.append("No Smart Parts detected.")
        return "\n".join(lines) + "\n"

    for assessment in sorted(
        result.assessments,
        key=_assessment_sort_key,
    ):
        lines.append(
            f"{_assessment_label(assessment):<24}"
            f"{assessment.confidence.value.upper()}"
        )

        if assessment.confidence is SmartPartConfidence.AMBIGUOUS:
            lines.append("  Candidates:")
            for candidate in assessment.candidates:
                lines.extend(_render_ambiguous_candidate(candidate))
            continue

        explanation = _resolved_explanation(result, assessment)
        if explanation is not None:
            lines.append("  Evidence:")
            lines.extend(
                _render_evidence_item(item)
                for item in explanation.evidence
            )

    return "\n".join(lines) + "\n"


_UNEXPECTED_INSPECT_ERROR: Final[str] = (
    "Unexpected internal Smart Inspect failure."
)


def _print_unexpected_inspect_error() -> int:
    """Render one redacted unexpected Smart Inspect process failure."""

    print(
        f"[ERROR] smart inspect: {_UNEXPECTED_INSPECT_ERROR}",
        file=sys.stderr,
    )
    return 3


def run_smart_command(arguments: argparse.Namespace) -> int:
    """Run one read-only Smart command."""

    if arguments.smart_action != "inspect":
        raise RuntimeError(f"unsupported Smart action: {arguments.smart_action!r}")

    try:
        result = inspect_smart_parts(arguments.source)
        rendered = _render_basic_text(result)
    except (PmxServiceError, PmxStructuralAuthoringCatalogServiceError) as error:
        return _print_inspect_error(error)
    except Exception:
        return _print_unexpected_inspect_error()

    sys.stdout.write(rendered)
    return 0
