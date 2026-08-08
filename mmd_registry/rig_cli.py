"""Command-line workflow for read-only PMX rig analysis."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal, Sequence, TypeAlias

from mmd_registry.bone_names import split_bone_name_tokens
from mmd_registry.bone_semantics import BoneSemanticResult
from mmd_registry.model_scanning import (
    PmxHeaderScanResult,
    scan_pmx_structure,
)
from mmd_registry.reporting import write_json_report
from mmd_registry.rig_analysis import (
    RigAnalysisReport,
    analyze_rig,
    canonical_bone_map_key,
)


RigSelectionMode: TypeAlias = Literal[
    "unmapped",
    "role",
]

RigSelection: TypeAlias = tuple[
    RigSelectionMode,
    str | None,
    tuple[BoneSemanticResult, ...],
]


def _validate_input_file(file_path: Path) -> str | None:
    """Return an error for an invalid Rig Analyzer input path."""

    if not file_path.exists():
        return f"File does not exist: {file_path}"

    if not file_path.is_file():
        return f"Path is not a file: {file_path}"

    return None


def _normalize_role_query(value: str | None) -> str | None:
    """Normalize one canonical role query safely."""

    if value is None:
        return None

    tokens = split_bone_name_tokens(value)

    if not tokens:
        return ""

    return "_".join(tokens)


def _validate_options(
    file_path: Path,
    *,
    unmapped: bool,
    role: str | None,
    export_map: str | None,
) -> str | None:
    """Return an error for one unsupported or unsafe option."""

    if unmapped and role is not None:
        return "--unmapped cannot be combined with --role."

    if role == "":
        return "--role must contain a non-empty canonical role."

    if export_map is None:
        return None

    export_path = Path(export_map)

    if export_path.suffix.casefold() != ".json":
        return "--export-map must use a .json file path."

    if export_path.resolve() == file_path.resolve():
        return "--export-map cannot overwrite the input PMX file."

    if export_path.exists() and not export_path.is_file():
        return f"Export path is not a file: {export_path}"

    return None


def _model_name(scan_result: PmxHeaderScanResult) -> str | None:
    """Return the scanned local model name when available."""

    if scan_result.model_info is None:
        return None

    return scan_result.model_info.local_name


def _filters_payload(
    *,
    unmapped: bool,
    role: str | None,
) -> dict[str, Any]:
    """Return stable filter metadata."""

    return {
        "unmapped": unmapped,
        "role": role,
    }


def _error_payload(
    file_path: Path,
    *,
    messages: Sequence[str],
    internal_error: bool,
    unmapped: bool,
    role: str | None,
    bone_count: int | None = None,
    scan_warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one stable machine-readable Rig Analyzer error."""

    return {
        "path": file_path.as_posix(),
        "status": "error",
        "internal_error": internal_error,
        "model_name": None,
        "bone_count": bone_count,
        "filters": _filters_payload(
            unmapped=unmapped,
            role=role,
        ),
        "analysis": None,
        "selection": None,
        "exported_map": None,
        "scan_warnings": list(scan_warnings),
        "errors": list(messages),
    }


def _print_error(
    file_path: Path,
    *,
    messages: Sequence[str],
    json_output: bool,
    internal_error: bool,
    unmapped: bool,
    role: str | None,
    bone_count: int | None = None,
    scan_warnings: Sequence[str] = (),
) -> None:
    """Print one Rig Analyzer error in the requested format."""

    if json_output:
        print(
            json.dumps(
                _error_payload(
                    file_path,
                    messages=messages,
                    internal_error=internal_error,
                    unmapped=unmapped,
                    role=role,
                    bone_count=bone_count,
                    scan_warnings=scan_warnings,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    for message in messages:
        print(
            f"[ERROR] rig: {message}",
            file=sys.stderr,
        )


def _select_semantics(
    report: RigAnalysisReport,
    *,
    unmapped: bool,
    role: str | None,
) -> RigSelection | None:
    """Return the requested semantic subset or no selection."""

    if unmapped:
        return (
            "unmapped",
            None,
            tuple(result for result in report.semantics if result.role == "unknown"),
        )

    if role is not None:
        return (
            "role",
            role,
            tuple(
                result
                for result in report.semantics
                if canonical_bone_map_key(
                    result.role,
                    result.side,
                )
                == role
            ),
        )

    return None


def _selection_payload(
    selection: RigSelection | None,
) -> dict[str, Any] | None:
    """Return stable JSON for one optional semantic selection."""

    if selection is None:
        return None

    mode, query, results = selection

    return {
        "mode": mode,
        "query": query,
        "count": len(results),
        "bones": [result.to_dict() for result in results],
    }


def _combined_status(
    report: RigAnalysisReport,
    scan_warnings: Sequence[str],
) -> Literal["ok", "warning", "error"]:
    """Combine diagnostic status with non-fatal scanner warnings."""

    if report.status == "error":
        return "error"

    if report.status == "warning" or scan_warnings:
        return "warning"

    return "ok"


def _success_payload(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    report: RigAnalysisReport,
    *,
    unmapped: bool,
    role: str | None,
    selection: RigSelection | None,
    exported_map: Path | None,
) -> dict[str, Any]:
    """Build one complete machine-readable Rig Analyzer result."""

    scan_warnings = tuple(scan_result.warnings)

    return {
        "path": file_path.as_posix(),
        "status": _combined_status(report, scan_warnings),
        "internal_error": False,
        "model_name": _model_name(scan_result),
        "bone_count": len(scan_result.bones),
        "filters": _filters_payload(
            unmapped=unmapped,
            role=role,
        ),
        "analysis": report.to_dict(),
        "selection": _selection_payload(selection),
        "exported_map": (exported_map.as_posix() if exported_map is not None else None),
        "scan_warnings": list(scan_warnings),
        "errors": [],
    }


def _display_name(result: BoneSemanticResult) -> str:
    """Return one safe, compact source name for text output."""

    universal_name = " ".join(result.universal_name.split())

    if universal_name:
        return universal_name

    local_name = " ".join(result.local_name.split())

    if local_name:
        return local_name

    return "[unnamed]"


def _render_selection(
    selection: RigSelection,
) -> list[str]:
    """Render one role or unmapped selection."""

    mode, query, results = selection
    label = "unmapped" if mode == "unmapped" else f"role {query}"
    lines = [
        f"Selection: {label}",
        f"Matches: {len(results)}",
    ]

    for result in results:
        lines.append(
            f"  [{result.index}] {_display_name(result)} | "
            f"role={result.role} | side={result.side} | "
            f"category={result.category} | confidence={result.confidence}"
        )

    return lines


def _render_text_output(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    report: RigAnalysisReport,
    *,
    selection: RigSelection | None,
    exported_map: Path | None,
) -> str:
    """Render one human-readable complete rig analysis."""

    scan_warnings = tuple(scan_result.warnings)
    summary = report.summary
    lines = [
        f"File: {file_path.as_posix()}",
        f"Status: {_combined_status(report, scan_warnings)}",
        f"Model: {_model_name(scan_result) or '[not provided]'}",
        f"Bones: {summary.bone_count}",
        f"Resolved: {summary.resolved_bone_count}",
        f"Unresolved: {summary.unresolved_bone_count}",
        f"Mapped roles: {summary.mapped_role_count}",
        (
            f"Diagnostics: {summary.info_count} info | "
            f"{summary.warning_count} warning | "
            f"{summary.error_count} error"
        ),
    ]

    for warning in scan_warnings:
        lines.append(f"[WARNING] scan: {warning}")

    if selection is not None:
        lines.append("")
        lines.extend(_render_selection(selection))
    else:
        lines.extend(
            [
                "",
                "Canonical roles:",
            ]
        )

        if report.bone_map.role_index:
            for key, indices in report.bone_map.role_index.items():
                index_text = ", ".join(str(index) for index in indices)
                lines.append(f"  {key}: {index_text}")
        else:
            lines.append("  [none]")

    lines.extend(
        [
            "",
            "Rig diagnostics:",
        ]
    )

    if report.diagnostics.issues:
        for issue in report.diagnostics.issues:
            index_text = (
                ", ".join(str(index) for index in issue.bone_indices)
                if issue.bone_indices
                else "rig"
            )
            lines.append(
                f"  [{issue.severity.upper()}] {issue.code} "
                f"({index_text}): {issue.message}"
            )
    else:
        lines.append("  [none]")

    if exported_map is not None:
        lines.extend(
            [
                "",
                f"Exported map: {exported_map.as_posix()}",
            ]
        )

    return "\n".join(lines)


def run_rig_command(
    *,
    path: str,
    unmapped: bool = False,
    role: str | None = None,
    export_map: str | None = None,
    json_output: bool = False,
) -> int:
    """Run the read-only PMX Rig Analyzer command."""

    file_path = Path(path)
    normalized_role = _normalize_role_query(role)
    option_error = _validate_options(
        file_path,
        unmapped=unmapped,
        role=normalized_role,
        export_map=export_map,
    )

    if option_error is not None:
        _print_error(
            file_path,
            messages=(option_error,),
            json_output=json_output,
            internal_error=False,
            unmapped=unmapped,
            role=normalized_role,
        )
        return 2

    input_error = _validate_input_file(file_path)

    if input_error is not None:
        _print_error(
            file_path,
            messages=(input_error,),
            json_output=json_output,
            internal_error=False,
            unmapped=unmapped,
            role=normalized_role,
        )
        return 2

    try:
        scan_result = scan_pmx_structure(file_path)
    except Exception as error:
        _print_error(
            file_path,
            messages=(f"Internal scan failure: {error}",),
            json_output=json_output,
            internal_error=True,
            unmapped=unmapped,
            role=normalized_role,
        )
        return 3

    scan_errors = list(scan_result.errors)

    if not scan_result.scan_complete and not scan_errors:
        scan_errors.append("PMX structural scan did not complete.")

    if scan_errors:
        _print_error(
            file_path,
            messages=scan_errors,
            json_output=json_output,
            internal_error=False,
            unmapped=unmapped,
            role=normalized_role,
            bone_count=len(scan_result.bones),
            scan_warnings=scan_result.warnings,
        )
        return 1

    try:
        report = analyze_rig(scan_result.bones)
        selection = _select_semantics(
            report,
            unmapped=unmapped,
            role=normalized_role,
        )
    except Exception as error:
        _print_error(
            file_path,
            messages=(f"Internal Rig Analyzer failure: {error}",),
            json_output=json_output,
            internal_error=True,
            unmapped=unmapped,
            role=normalized_role,
            bone_count=len(scan_result.bones),
            scan_warnings=scan_result.warnings,
        )
        return 3

    exported_map = Path(export_map) if export_map is not None else None

    if exported_map is not None:
        try:
            write_json_report(
                report.bone_map.to_dict(),
                exported_map,
            )
        except OSError as error:
            _print_error(
                file_path,
                messages=(f"Unable to export bone map: {error}",),
                json_output=json_output,
                internal_error=False,
                unmapped=unmapped,
                role=normalized_role,
                bone_count=len(scan_result.bones),
                scan_warnings=scan_result.warnings,
            )
            return 3
        except Exception as error:
            _print_error(
                file_path,
                messages=(f"Internal bone-map export failure: {error}",),
                json_output=json_output,
                internal_error=True,
                unmapped=unmapped,
                role=normalized_role,
                bone_count=len(scan_result.bones),
                scan_warnings=scan_result.warnings,
            )
            return 3

    if json_output:
        payload = _success_payload(
            file_path,
            scan_result,
            report,
            unmapped=unmapped,
            role=normalized_role,
            selection=selection,
            exported_map=exported_map,
        )
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            _render_text_output(
                file_path,
                scan_result,
                report,
                selection=selection,
                exported_map=exported_map,
            )
        )

    if report.status in {"warning", "error"}:
        return 1

    return 0
