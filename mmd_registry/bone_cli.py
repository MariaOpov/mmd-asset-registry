"""Command-line workflow for read-only PMX bone exploration."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal, Sequence, TypeAlias

from mmd_registry.bone_details import (
    build_bone_detail,
    render_bone_detail,
)
from mmd_registry.bone_explorer import (
    build_bone_views,
    render_bone_table,
)
from mmd_registry.bone_hierarchy import (
    build_bone_hierarchy,
    render_bone_tree,
)
from mmd_registry.bone_search import filter_bone_views
from mmd_registry.model_scanning import (
    PmxHeaderScanResult,
    scan_pmx_structure,
)


BoneOutputMode: TypeAlias = Literal[
    "table",
    "tree",
    "details",
]


def _requested_mode(
    *,
    tree: bool,
    details: int | None,
) -> BoneOutputMode:
    """Return the requested Bone Explorer output mode."""

    if details is not None:
        return "details"

    if tree:
        return "tree"

    return "table"


def _validate_mode_options(
    *,
    tree: bool,
    details: int | None,
    search_query: str | None,
    ik_only: bool,
) -> str | None:
    """Return an error for an unsupported option combination."""

    if details is not None and (tree or search_query is not None or ik_only):
        return "--details cannot be combined with --tree, --search, or --ik-only."

    if tree and (search_query is not None or ik_only):
        return "--tree cannot be combined with --search or --ik-only."

    return None


def _validate_input_file(
    file_path: Path,
) -> str | None:
    """Return an error for an invalid Bone Explorer input path."""

    if not file_path.exists():
        return f"File does not exist: {file_path}"

    if not file_path.is_file():
        return f"Path is not a file: {file_path}"

    return None


def _model_name(
    scan_result: PmxHeaderScanResult,
) -> str | None:
    """Return the scanned local model name when available."""

    if scan_result.model_info is None:
        return None

    return scan_result.model_info.local_name


def _error_payload(
    file_path: Path,
    *,
    mode: BoneOutputMode,
    messages: Sequence[str],
    internal_error: bool,
    bone_count: int | None = None,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    """Build one stable machine-readable Bone Explorer error."""

    return {
        "path": file_path.as_posix(),
        "status": "error",
        "internal_error": internal_error,
        "mode": mode,
        "model_name": None,
        "bone_count": bone_count,
        "match_count": 0,
        "filters": None,
        "bones": None,
        "hierarchy": None,
        "detail": None,
        "warnings": list(warnings),
        "errors": list(messages),
    }


def _print_error(
    file_path: Path,
    *,
    mode: BoneOutputMode,
    messages: Sequence[str],
    json_output: bool,
    internal_error: bool,
    bone_count: int | None = None,
    warnings: Sequence[str] = (),
) -> None:
    """Print a Bone Explorer error in the requested format."""

    if json_output:
        print(
            json.dumps(
                _error_payload(
                    file_path,
                    mode=mode,
                    messages=messages,
                    internal_error=internal_error,
                    bone_count=bone_count,
                    warnings=warnings,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    for message in messages:
        print(
            f"[ERROR] bones: {message}",
            file=sys.stderr,
        )


def _base_success_payload(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    *,
    status: str,
    mode: BoneOutputMode,
    match_count: int,
    search_query: str | None,
    ik_only: bool,
    warnings: Sequence[str],
) -> dict[str, Any]:
    """Build shared fields for one successful result."""

    return {
        "path": file_path.as_posix(),
        "status": status,
        "internal_error": False,
        "mode": mode,
        "model_name": _model_name(scan_result),
        "bone_count": len(scan_result.bones),
        "match_count": match_count,
        "filters": {
            "search": search_query,
            "ik_only": ik_only,
        },
        "warnings": list(warnings),
        "errors": [],
    }


def _text_header(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    *,
    status: str,
) -> list[str]:
    """Build shared human-readable Bone Explorer header lines."""

    return [
        f"File: {file_path.as_posix()}",
        f"Status: {status}",
        f"Model: {_model_name(scan_result) or '[not provided]'}",
        f"Bones: {len(scan_result.bones)}",
    ]


def _build_table_output(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    *,
    search_query: str | None,
    ik_only: bool,
) -> tuple[dict[str, Any], str]:
    """Build table-mode JSON and text output."""

    views = build_bone_views(scan_result.bones)
    matches = filter_bone_views(
        views,
        search_query=search_query,
        ik_only=ik_only,
    )
    warnings = tuple(scan_result.warnings)
    status = "warning" if warnings else "ok"

    payload = {
        **_base_success_payload(
            file_path,
            scan_result,
            status=status,
            mode="table",
            match_count=len(matches),
            search_query=search_query,
            ik_only=ik_only,
            warnings=warnings,
        ),
        "bones": [view.to_dict() for view in matches],
        "hierarchy": None,
        "detail": None,
    }

    lines = _text_header(
        file_path,
        scan_result,
        status=status,
    )
    lines.append(f"Showing: {len(matches)}")

    if search_query is not None:
        lines.append(f"Search: {search_query}")

    if ik_only:
        lines.append("IK only: yes")

    for warning in warnings:
        lines.append(f"[WARNING] scan: {warning}")

    lines.extend(
        [
            "",
            render_bone_table(matches),
        ]
    )

    return payload, "\n".join(lines)


def _build_tree_output(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
) -> tuple[dict[str, Any], str]:
    """Build hierarchy-mode JSON and text output."""

    views = build_bone_views(scan_result.bones)
    hierarchy = build_bone_hierarchy(views)
    hierarchy_warnings = tuple(issue.message for issue in hierarchy.issues)
    warnings = (
        *scan_result.warnings,
        *hierarchy_warnings,
    )
    status = "warning" if warnings else "ok"

    payload = {
        **_base_success_payload(
            file_path,
            scan_result,
            status=status,
            mode="tree",
            match_count=len(hierarchy.nodes),
            search_query=None,
            ik_only=False,
            warnings=warnings,
        ),
        "bones": None,
        "hierarchy": hierarchy.to_dict(),
        "detail": None,
    }

    lines = _text_header(
        file_path,
        scan_result,
        status=status,
    )
    lines.extend(
        [
            f"Roots: {len(hierarchy.root_indices)}",
            f"Hierarchy issues: {len(hierarchy.issues)}",
        ]
    )

    for warning in scan_result.warnings:
        lines.append(f"[WARNING] scan: {warning}")

    for issue in hierarchy.issues:
        lines.append(f"[WARNING] hierarchy: {issue.message}")

    lines.extend(
        [
            "",
            render_bone_tree(hierarchy),
        ]
    )

    return payload, "\n".join(lines)


def _build_detail_output(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    *,
    bone_index: int,
) -> tuple[dict[str, Any], str] | None:
    """Build detail-mode output or return None for an invalid index."""

    detail = build_bone_detail(
        scan_result.bones,
        bone_index,
    )

    if detail is None:
        return None

    warnings = tuple(scan_result.warnings)
    status = "warning" if warnings else "ok"

    payload = {
        **_base_success_payload(
            file_path,
            scan_result,
            status=status,
            mode="details",
            match_count=1,
            search_query=None,
            ik_only=False,
            warnings=warnings,
        ),
        "bones": None,
        "hierarchy": None,
        "detail": detail.to_dict(),
    }

    lines = _text_header(
        file_path,
        scan_result,
        status=status,
    )

    for warning in warnings:
        lines.append(f"[WARNING] scan: {warning}")

    lines.extend(
        [
            "",
            render_bone_detail(detail),
        ]
    )

    return payload, "\n".join(lines)


def run_bones_command(
    *,
    path: str,
    tree: bool = False,
    details: int | None = None,
    search_query: str | None = None,
    ik_only: bool = False,
    json_output: bool = False,
) -> int:
    """Run the read-only PMX Bone Explorer command."""

    file_path = Path(path)
    mode = _requested_mode(
        tree=tree,
        details=details,
    )
    option_error = _validate_mode_options(
        tree=tree,
        details=details,
        search_query=search_query,
        ik_only=ik_only,
    )

    if option_error is not None:
        _print_error(
            file_path,
            mode=mode,
            messages=(option_error,),
            json_output=json_output,
            internal_error=False,
        )
        return 2

    input_error = _validate_input_file(file_path)

    if input_error is not None:
        _print_error(
            file_path,
            mode=mode,
            messages=(input_error,),
            json_output=json_output,
            internal_error=False,
        )
        return 2

    try:
        scan_result = scan_pmx_structure(file_path)
    except Exception as error:
        _print_error(
            file_path,
            mode=mode,
            messages=(f"Internal scan failure: {error}",),
            json_output=json_output,
            internal_error=True,
        )
        return 3

    scan_errors = list(scan_result.errors)

    if not scan_result.scan_complete and not scan_errors:
        scan_errors.append("PMX structural scan did not complete.")

    if scan_errors:
        _print_error(
            file_path,
            mode=mode,
            messages=scan_errors,
            json_output=json_output,
            internal_error=False,
            bone_count=len(scan_result.bones),
            warnings=scan_result.warnings,
        )
        return 1

    try:
        if details is not None:
            output = _build_detail_output(
                file_path,
                scan_result,
                bone_index=details,
            )

            if output is None:
                _print_error(
                    file_path,
                    mode=mode,
                    messages=(
                        f"Bone index {details} does not exist; "
                        f"valid range is 0 to "
                        f"{len(scan_result.bones) - 1}.",
                    ),
                    json_output=json_output,
                    internal_error=False,
                    bone_count=len(scan_result.bones),
                    warnings=scan_result.warnings,
                )
                return 2

            payload, text_output = output
        elif tree:
            payload, text_output = _build_tree_output(
                file_path,
                scan_result,
            )
        else:
            payload, text_output = _build_table_output(
                file_path,
                scan_result,
                search_query=search_query,
                ik_only=ik_only,
            )
    except Exception as error:
        _print_error(
            file_path,
            mode=mode,
            messages=(f"Internal Bone Explorer failure: {error}",),
            json_output=json_output,
            internal_error=True,
            bone_count=len(scan_result.bones),
            warnings=scan_result.warnings,
        )
        return 3

    if json_output:
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(text_output)

    return 0
