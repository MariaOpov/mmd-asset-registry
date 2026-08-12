"""Read-only CLI workflow for deterministic PMX texture portability."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from mmd_registry.hashing import hash_file_sha256
from mmd_registry.model_scanning import scan_pmx_structure
from mmd_registry.pmx.editing import load_pmx_edit_plan
from mmd_registry.texture_rewrite import (
    TextureRewriteDisposition,
    TextureRewriteEditPlan,
    TextureRewriteReport,
    analyze_texture_rewrites,
    build_texture_rewrite_edit_plan,
)


def _print_error(
    *,
    model_path: Path,
    message: str,
    json_output: bool,
    error_type: str,
    rewrite_report: TextureRewriteReport | None = None,
    plan_path: Path | None = None,
) -> None:
    """Render one stable texture-portability CLI failure."""

    if json_output:
        print(
            json.dumps(
                {
                    "path": model_path.as_posix(),
                    "status": "error",
                    "error_type": error_type,
                    "errors": [message],
                    "rewrite_report": (
                        rewrite_report.to_dict()
                        if rewrite_report is not None
                        else None
                    ),
                    "plan": {
                        "requested": plan_path is not None,
                        "path": (
                            plan_path.as_posix()
                            if plan_path is not None
                            else None
                        ),
                        "written": False,
                    },
                },
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
        return

    print(f"[ERROR] texture-portability: {message}", file=sys.stderr)


def _status_for_report(report: TextureRewriteReport) -> str:
    """Return a stable user-facing workflow status."""

    blocked_referenced = sum(
        proposal.disposition is TextureRewriteDisposition.BLOCKED
        and proposal.is_referenced
        for proposal in report.proposals
    )
    if blocked_referenced:
        return "error"
    if report.blocked_count:
        return "warning"
    if report.safe_rewrite_count:
        return "rewrite_available"
    return "ok"


def _blocked_referenced_count(report: TextureRewriteReport) -> int:
    return sum(
        proposal.disposition is TextureRewriteDisposition.BLOCKED
        and proposal.is_referenced
        for proposal in report.proposals
    )


def _print_report_text(
    *,
    model_path: Path,
    report: TextureRewriteReport,
    plan_path: Path | None,
    plan_written: bool,
) -> None:
    """Render one deterministic human-readable portability report."""

    print(f"File: {model_path.as_posix()}")
    print(f"Status: {_status_for_report(report)}")
    print("Texture portability:")
    print(f"  Declared: {report.declared_texture_count}")
    print(f"  Safe rewrites: {report.safe_rewrite_count}")
    print(f"  No change: {report.no_change_count}")
    print(f"  Blocked: {report.blocked_count}")
    print(f"  Blocked referenced: {_blocked_referenced_count(report)}")

    if report.proposals:
        print("Proposals:")
        for proposal in report.proposals:
            reference_label = (
                "referenced" if proposal.is_referenced else "unreferenced"
            )
            line = (
                f"  [{proposal.texture_index}] "
                f"{proposal.disposition.value} | {reference_label} | "
                f"{proposal.declared_path}"
            )
            if proposal.candidate_path is not None:
                line += f" -> {proposal.candidate_path}"
            print(line)
            if proposal.source_issue_codes:
                print(
                    "    Issues: "
                    + ", ".join(proposal.source_issue_codes)
                )

    if plan_path is None:
        print("Plan: not requested")
    elif plan_written:
        print(f"Plan: {plan_path.as_posix()}")
    elif _blocked_referenced_count(report):
        print("Plan: not generated (referenced blocked dependencies)")
    elif report.safe_rewrite_count == 0:
        print("Plan: not generated (no safe rewrites)")
    else:
        print("Plan: not written")


def _json_payload(
    *,
    model_path: Path,
    report: TextureRewriteReport,
    plan_path: Path | None,
    plan_written: bool,
    bridge: TextureRewriteEditPlan | None,
) -> dict[str, Any]:
    """Build one stable machine-readable workflow payload."""

    return {
        "path": model_path.as_posix(),
        "status": _status_for_report(report),
        "blocked_referenced_count": _blocked_referenced_count(report),
        "rewrite_report": report.to_dict(),
        "plan": {
            "requested": plan_path is not None,
            "path": plan_path.as_posix() if plan_path is not None else None,
            "written": plan_written,
            "operation_count": (
                len(bridge.plan.operations)
                if bridge is not None and bridge.plan is not None
                else 0
            ),
        },
    }


def _validate_plan_output_path(
    *,
    model_path: Path,
    plan_path: Path,
) -> str | None:
    """Return a stable refusal reason for an unsafe plan output path."""

    try:
        if plan_path.resolve(strict=False) == model_path.resolve(strict=False):
            return "Plan output path must be distinct from the source PMX file."
    except (OSError, RuntimeError, ValueError):
        if plan_path.absolute() == model_path.absolute():
            return "Plan output path must be distinct from the source PMX file."

    if plan_path.exists():
        return f"Plan output already exists: {plan_path}"

    parent = plan_path.parent
    if not parent.exists():
        return f"Plan output directory does not exist: {parent}"
    if not parent.is_dir():
        return f"Plan output parent is not a directory: {parent}"

    return None


def _write_verified_plan(
    *,
    plan_path: Path,
    bridge: TextureRewriteEditPlan,
) -> None:
    """Write one new strict JSON plan and verify it through the existing loader."""

    if bridge.plan is None or bridge.json_text is None:
        raise ValueError("rewrite bridge does not contain an edit plan.")

    created = False
    try:
        with plan_path.open(
            "x",
            encoding="utf-8",
            newline="\n",
        ) as file:
            created = True
            file.write(bridge.json_text)

        loaded = load_pmx_edit_plan(plan_path)
        if loaded != bridge.plan:
            raise RuntimeError(
                "strict edit-plan loader changed the written rewrite plan."
            )
    except Exception:
        if created:
            try:
                plan_path.unlink()
            except OSError:
                pass
        raise


def run_texture_portability_command(
    *,
    path: str,
    json_output: bool,
    plan_out: str | None,
) -> int:
    """Analyze PMX texture portability and optionally emit a strict edit plan."""

    model_path = Path(path)
    plan_path = Path(plan_out) if plan_out is not None else None

    if not model_path.exists():
        _print_error(
            model_path=model_path,
            message=f"File does not exist: {model_path}",
            json_output=json_output,
            error_type="path_policy",
            plan_path=plan_path,
        )
        return 2
    if not model_path.is_file():
        _print_error(
            model_path=model_path,
            message=f"Path is not a file: {model_path}",
            json_output=json_output,
            error_type="path_policy",
            plan_path=plan_path,
        )
        return 2

    source_sha256_before: str | None = None
    if plan_path is not None:
        try:
            source_sha256_before, _ = hash_file_sha256(model_path)
        except OSError:
            _print_error(
                model_path=model_path,
                message="Unable to hash source PMX file before portability analysis.",
                json_output=json_output,
                error_type="io",
                plan_path=plan_path,
            )
            return 2

    try:
        scan_result = scan_pmx_structure(model_path)
    except Exception:
        _print_error(
            model_path=model_path,
            message="Internal PMX scan failure.",
            json_output=json_output,
            error_type="internal",
            plan_path=plan_path,
        )
        return 3

    if scan_result.errors or not scan_result.scan_complete:
        message = (
            scan_result.errors[0]
            if scan_result.errors
            else "PMX structural scan did not complete."
        )
        _print_error(
            model_path=model_path,
            message=message,
            json_output=json_output,
            error_type="invalid_pmx",
            plan_path=plan_path,
        )
        return 1

    dependency_summary = scan_result.dependency_summary
    if dependency_summary is None:
        _print_error(
            model_path=model_path,
            message="Complete PMX scan did not produce a dependency summary.",
            json_output=json_output,
            error_type="internal",
            plan_path=plan_path,
        )
        return 3

    try:
        report = analyze_texture_rewrites(
            model_path,
            scan_result.texture_paths,
            dependency_summary.referenced_texture_indices,
        )
    except Exception:
        _print_error(
            model_path=model_path,
            message="Internal texture portability analysis failure.",
            json_output=json_output,
            error_type="internal",
            plan_path=plan_path,
        )
        return 3

    blocked_referenced = _blocked_referenced_count(report)
    bridge: TextureRewriteEditPlan | None = None
    plan_written = False

    if plan_path is not None and blocked_referenced:
        if json_output:
            print(
                json.dumps(
                    _json_payload(
                        model_path=model_path,
                        report=report,
                        plan_path=plan_path,
                        plan_written=False,
                        bridge=None,
                    ),
                    ensure_ascii=False,
                    allow_nan=False,
                    indent=2,
                )
            )
        else:
            _print_report_text(
                model_path=model_path,
                report=report,
                plan_path=plan_path,
                plan_written=False,
            )
        return 1

    if plan_path is not None and report.safe_rewrite_count:
        path_error = _validate_plan_output_path(
            model_path=model_path,
            plan_path=plan_path,
        )
        if path_error is not None:
            _print_error(
                model_path=model_path,
                message=path_error,
                json_output=json_output,
                error_type="plan_output",
                rewrite_report=report,
                plan_path=plan_path,
            )
            return 2

        try:
            source_sha256_after, _ = hash_file_sha256(model_path)
        except OSError:
            _print_error(
                model_path=model_path,
                message="Unable to hash source PMX file after portability analysis.",
                json_output=json_output,
                error_type="io",
                rewrite_report=report,
                plan_path=plan_path,
            )
            return 2

        assert source_sha256_before is not None
        if source_sha256_after != source_sha256_before:
            _print_error(
                model_path=model_path,
                message=(
                    "Source PMX changed during texture portability analysis; "
                    "edit plan was not generated."
                ),
                json_output=json_output,
                error_type="source_changed",
                rewrite_report=report,
                plan_path=plan_path,
            )
            return 1

        try:
            bridge = build_texture_rewrite_edit_plan(
                report,
                expected_source_sha256=source_sha256_before,
            )
            _write_verified_plan(
                plan_path=plan_path,
                bridge=bridge,
            )
            plan_written = True
        except OSError:
            _print_error(
                model_path=model_path,
                message="Unable to write or verify edit-plan output.",
                json_output=json_output,
                error_type="io",
                rewrite_report=report,
                plan_path=plan_path,
            )
            return 2
        except Exception:
            _print_error(
                model_path=model_path,
                message="Internal edit-plan generation or verification failure.",
                json_output=json_output,
                error_type="internal",
                rewrite_report=report,
                plan_path=plan_path,
            )
            return 3

    if json_output:
        print(
            json.dumps(
                _json_payload(
                    model_path=model_path,
                    report=report,
                    plan_path=plan_path,
                    plan_written=plan_written,
                    bridge=bridge,
                ),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
    else:
        _print_report_text(
            model_path=model_path,
            report=report,
            plan_path=plan_path,
            plan_written=plan_written,
        )

    return 1 if blocked_referenced else 0
