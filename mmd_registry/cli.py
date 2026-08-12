"""Command-line interface for the MMD Asset Registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import yaml

from mmd_registry import __version__
from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.bone_cli import run_bones_command
from mmd_registry.constants import VALID_MODES
from mmd_registry.dependency_diagnostics import (
    TextureDependencyDiagnostics,
    diagnose_texture_dependencies,
)
from mmd_registry.hashing import check_file_sha256
from mmd_registry.model_inspection import inspect_model_header
from mmd_registry.model_scanning import (
    PmxHeaderScanResult,
    scan_pmx_structure,
)
from mmd_registry.pmx.editing import (
    PmxEditDiagnostic,
    PmxEditPathError,
    PmxEditPhase,
    PmxEditPlanDecodeError,
    PmxEditPlanError,
    PmxEditVerificationError,
    default_diagnostic_code,
    diagnostic_from_plan_error,
    dry_run_pmx_edit,
    load_pmx_edit_plan,
    render_pmx_edit_diagnostic_text,
    render_pmx_edit_preview_json,
    render_pmx_edit_preview_text,
    render_pmx_edit_write_json,
    render_pmx_edit_write_text,
    write_pmx_edit,
)
from mmd_registry.pmx.errors import PmxValidationError
from mmd_registry.pmx.roundtrip import (
    PmxRoundTripPathError,
    PmxRoundTripResult,
    PmxRoundTripVerificationError,
    roundtrip_pmx,
)
from mmd_registry.reporting import (
    build_json_report,
    write_credits_file,
    write_json_report,
)
from mmd_registry.rig_cli import run_rig_command
from mmd_registry.validator import (
    RegistryValidationResult,
    validate_registry,
)


COMMAND_NAMES = frozenset(
    {
        "validate",
        "hash",
        "inspect",
        "scan",
        "roundtrip",
        "doctor",
        "bones",
        "rig",
        "edit",
    }
)


def _configure_utf8_standard_streams() -> None:
    """Use UTF-8 for redirected CLI output when supported."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)

        if not callable(reconfigure):
            continue

        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            # In-memory and third-party streams may not support changing
            # their encoding. Keep their existing behavior in that case.
            continue


class RegistryLoadError(Exception):
    """Raised when a registry file cannot be loaded."""


def load_registry(registry_file: Path) -> Any:
    """Read a YAML registry file."""

    if not registry_file.exists():
        raise RegistryLoadError(f"Registry file does not exist: {registry_file}")

    if not registry_file.is_file():
        raise RegistryLoadError(f"Registry path is not a file: {registry_file}")

    try:
        with registry_file.open("r", encoding="utf-8") as file:
            return yaml.safe_load(file)
    except OSError as error:
        raise RegistryLoadError(f"Unable to read registry file: {error}") from error
    except yaml.YAMLError as error:
        raise RegistryLoadError(f"Invalid YAML syntax: {error}") from error


def print_validation_result(
    result: RegistryValidationResult,
) -> None:
    """Print validation messages to the terminal."""

    for message in result.registry_infos:
        print(f"[INFO] registry: {message}")

    for message in result.registry_warnings:
        print(f"[WARNING] registry: {message}")

    for message in result.registry_errors:
        print(f"[ERROR] registry: {message}")

    for asset in result.assets:
        if not asset.errors and not asset.warnings and not asset.infos:
            print(f"[OK] {asset.asset_id}")
            continue

        for message in asset.infos:
            print(f"[INFO] {asset.asset_id}: {message}")

        for message in asset.warnings:
            print(f"[WARNING] {asset.asset_id}: {message}")

        for message in asset.errors:
            print(f"[ERROR] {asset.asset_id}: {message}")

    print("-" * 60)
    print(
        f"Assets: {len(result.assets)} | "
        f"Infos: {result.info_count} | "
        f"Warnings: {result.warning_count} | "
        f"Errors: {result.error_count}"
    )
    print(f"Status: {result.status}")


def _add_validate_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    """Add registry-validation arguments to a parser."""

    parser.add_argument(
        "--registry",
        default="assets.yaml",
        help="Path to the YAML registry.",
    )

    parser.add_argument(
        "--mode",
        choices=sorted(VALID_MODES),
        default="private",
        help="Usage profile used for validation.",
    )

    parser.add_argument(
        "--report",
        default="reports/validation_report.json",
        help="Path for the generated JSON report.",
    )

    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not generate a JSON report.",
    )

    parser.add_argument(
        "--credits",
        nargs="?",
        const="reports/CREDITS.md",
        default=None,
        metavar="PATH",
        help=("Generate a Markdown credit file. Defaults to reports/CREDITS.md."),
    )


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        prog="mmd-asset-registry",
        description=(
            "Validate MMD assets, calculate SHA-256 hashes, inspect "
            "PMX/PMD headers, structurally scan PMX models, and "
            "diagnose texture dependencies, explore PMX bones, or "
            "analyze PMX rigs, with explicit safe PMX round-trip output."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        required=True,
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an asset registry.",
        description=(
            "Validate MMD asset provenance, credits, integrity, "
            "headers, and known usage restrictions."
        ),
    )
    _add_validate_arguments(validate_parser)

    hash_parser = subparsers.add_parser(
        "hash",
        help="Calculate or verify a file SHA-256 hash.",
    )
    hash_parser.add_argument(
        "path",
        help="Path to the file to hash.",
    )
    hash_parser.add_argument(
        "--expected",
        default=None,
        metavar="SHA256",
        help="Expected SHA-256 digest to verify.",
    )
    hash_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result as JSON.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a PMX or PMD model header.",
    )
    inspect_parser.add_argument(
        "path",
        help="Path to the PMX or PMD file.",
    )
    inspect_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the result as JSON.",
    )

    scan_parser = subparsers.add_parser(
        "scan",
        help="Structurally scan a PMX model.",
        description=(
            "Safely scan all PMX 2.0 or PMX 2.1 structural sections "
            "and collect texture references without modifying the model."
        ),
    )
    scan_parser.add_argument(
        "path",
        help="Path to the PMX file.",
    )
    scan_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete scan result as JSON.",
    )

    roundtrip_parser = subparsers.add_parser(
        "roundtrip",
        help="Write a verified PMX copy to a distinct output path.",
        description=(
            "Parse, validate, serialize, and semantically verify one PMX before "
            "writing a distinct output file. The input is never modified."
        ),
    )
    roundtrip_parser.add_argument(
        "input",
        help="Path to the source PMX file.",
    )
    roundtrip_parser.add_argument(
        "output",
        help="Path for the new PMX file.",
    )
    roundtrip_parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Replace an existing distinct output file. Input and output may "
            "never refer to the same file."
        ),
    )
    roundtrip_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the verified round-trip result as JSON.",
    )

    edit_parser = subparsers.add_parser(
        "edit",
        help="Preview or safely write a declarative PMX edit plan.",
        description=(
            "Load and validate a strict JSON edit plan, apply it entirely in "
            "memory, semantically verify serialization, and either preview "
            "the result or atomically write a distinct output PMX."
        ),
    )
    edit_parser.add_argument(
        "input",
        help="Path to the source PMX file.",
    )
    edit_parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help=(
            "Distinct output PMX path. Required in write mode and never "
            "modified during dry-run."
        ),
    )
    edit_parser.add_argument(
        "--plan",
        required=True,
        metavar="PATH",
        help="Path to the strict UTF-8 JSON edit plan.",
    )
    edit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview and verify all edits without writing a PMX output.",
    )
    edit_parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Atomically replace an existing separate output file. Input and "
            "output aliases are always refused."
        ),
    )
    edit_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the preview or write result as stable Unicode-safe JSON.",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Scan a PMX model and diagnose texture dependencies.",
        description=(
            "Structurally scan a PMX model, resolve its declared texture "
            "paths, and report missing or non-portable dependencies "
            "without modifying any files."
        ),
    )
    doctor_parser.add_argument(
        "path",
        help="Path to the PMX file.",
    )
    doctor_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the combined doctor result as JSON.",
    )

    bones_parser = subparsers.add_parser(
        "bones",
        help="Explore PMX bones in a human-readable form.",
        description=(
            "Scan and explore PMX bones as a compact table, "
            "hierarchy tree, individual detail report, or JSON "
            "without modifying the model."
        ),
    )
    bones_parser.add_argument(
        "path",
        help="Path to the PMX file.",
    )
    bones_parser.add_argument(
        "--tree",
        action="store_true",
        help="Render the complete parent-child hierarchy.",
    )
    bones_parser.add_argument(
        "--details",
        type=int,
        default=None,
        metavar="INDEX",
        help="Show a detailed report for one bone index.",
    )
    bones_parser.add_argument(
        "--search",
        default=None,
        metavar="QUERY",
        help="Search local, universal, and display names or an index.",
    )
    bones_parser.add_argument(
        "--ik-only",
        action="store_true",
        help="Show only bones with the IK capability.",
    )
    bones_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the Bone Explorer result as JSON.",
    )

    rig_parser = subparsers.add_parser(
        "rig",
        help="Analyze PMX bone semantics and rig diagnostics.",
        description=(
            "Resolve PMX bone semantics, diagnose hierarchy and IK issues, "
            "and build a read-only canonical bone map."
        ),
    )
    rig_parser.add_argument(
        "path",
        help="Path to the PMX file.",
    )
    rig_parser.add_argument(
        "--unmapped",
        action="store_true",
        help="Show only semantically unresolved bones.",
    )
    rig_parser.add_argument(
        "--role",
        default=None,
        metavar="ROLE",
        help="Show bones for one canonical role, such as left_knee.",
    )
    rig_parser.add_argument(
        "--export-map",
        default=None,
        metavar="PATH",
        help="Write the canonical bone map to a JSON file.",
    )
    rig_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete rig analysis as JSON.",
    )

    return parser


def normalize_arguments(
    argv: Sequence[str] | None,
) -> list[str]:
    """Preserve the legacy validation-only command syntax."""

    arguments = list(sys.argv[1:] if argv is None else argv)

    if not arguments:
        return ["validate"]

    first_argument = arguments[0]

    if first_argument in COMMAND_NAMES:
        return arguments

    if first_argument in {"-h", "--help", "--version"}:
        return arguments

    return ["validate", *arguments]


def _resolve_output_path(
    raw_path: str,
    project_root: Path,
) -> Path:
    """Resolve an output path relative to the project root."""

    path = Path(raw_path)

    if path.is_absolute():
        return path

    return project_root / path


def _validate_input_file(
    path: Path,
) -> str | None:
    """Return a user-facing error for an invalid input path."""

    if not path.exists():
        return f"File does not exist: {path}"

    if not path.is_file():
        return f"Path is not a file: {path}"

    return None


def _run_validate(arguments: argparse.Namespace) -> int:
    """Run registry validation."""

    registry_file = Path(arguments.registry).resolve()
    project_root = registry_file.parent

    print(f"MMD Asset & License Registry v{__version__}")
    print(f"Mode: {arguments.mode}")
    print(f"Registry: {registry_file}")
    print("-" * 60)

    try:
        registry = load_registry(registry_file)
    except RegistryLoadError as error:
        print(f"[ERROR] registry: {error}")
        return 2

    result = validate_registry(
        registry=registry,
        project_root=project_root,
        mode=arguments.mode,
    )

    print_validation_result(result)

    if not arguments.no_report:
        report_file = _resolve_output_path(
            arguments.report,
            project_root,
        )

        report = build_json_report(
            result=result,
            registry_file=registry_file,
            project_root=project_root,
        )

        write_json_report(
            report=report,
            report_file=report_file,
        )

        print(f"Report: {report_file}")

    if arguments.credits is not None:
        credits_file = _resolve_output_path(
            arguments.credits,
            project_root,
        )

        write_credits_file(
            registry=registry,
            credits_file=credits_file,
        )

        print(f"Credits: {credits_file}")

    if result.error_count:
        return 1

    return 0


def _run_hash(arguments: argparse.Namespace) -> int:
    """Calculate or verify one file SHA-256 digest."""

    file_path = Path(arguments.path)
    input_error = _validate_input_file(file_path)

    if input_error is not None:
        print(f"[ERROR] hash: {input_error}")
        return 2

    try:
        result = check_file_sha256(
            file_path,
            arguments.expected,
        )
    except OSError as error:
        print(f"[ERROR] hash: Unable to read file: {error}")
        return 2

    payload = {
        "path": file_path.as_posix(),
        "algorithm": result.algorithm,
        "expected": result.expected,
        "actual": result.actual,
        "status": result.status,
        "size_bytes": result.size_bytes,
    }

    if arguments.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"File: {payload['path']}")
        print(f"Algorithm: {result.algorithm}")
        print(f"SHA-256: {result.actual}")
        print(f"Size bytes: {result.size_bytes}")

        if result.expected is not None:
            print(f"Expected: {result.expected}")

        print(f"Status: {result.status}")

    if result.status in {"mismatched", "invalid_expected"}:
        return 1

    return 0


def _run_inspect(arguments: argparse.Namespace) -> int:
    """Inspect one PMX or PMD model header."""

    file_path = Path(arguments.path)
    input_error = _validate_input_file(file_path)

    if input_error is not None:
        print(f"[ERROR] inspect: {input_error}")
        return 2

    result = inspect_model_header(file_path)
    payload = {
        "path": file_path.as_posix(),
        **result.to_dict(),
    }

    if arguments.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"File: {payload['path']}")
        print(f"Status: {result.status}")
        print(
            "Format: "
            + (
                result.detected_format.upper()
                if result.detected_format is not None
                else "unknown"
            )
        )
        print(f"Magic: {result.magic}")
        print(f"Version: {result.version}")
        print(f"Encoding: {result.encoding}")
        print(f"Model name: {result.model_name}")

        for message in result.warnings:
            print(f"[WARNING] {message}")

        for message in result.errors:
            print(f"[ERROR] {message}")

    if result.errors:
        return 1

    return 0


def _format_scan_value(value: object | None) -> str:
    """Format one optional scan value for human-readable output."""

    if value is None:
        return "unknown"

    return str(value)


def _print_scan_section_summary(
    result: PmxHeaderScanResult,
) -> None:
    """Print aggregate PMX section counts."""

    summary = result.section_summary

    if summary is None:
        return

    print("Sections:")
    print(f"  Vertices: {summary.vertex_count}")
    print(f"  Surface indices: {summary.surface_index_count}")
    print(f"  Triangles: {summary.triangle_count}")
    print(f"  Textures: {summary.texture_count}")
    print(f"  Materials: {summary.material_count}")
    print(f"  Bones: {summary.bone_count}")
    print(f"  IK chains: {summary.ik_count}")
    print(f"  IK links: {summary.ik_link_count}")
    print(f"  Morphs: {summary.morph_count}")
    print(f"  Morph offsets: {summary.morph_offset_count}")
    print(f"  Display frames: {summary.display_frame_count}")
    print(f"  Display-frame elements: {summary.display_frame_element_count}")
    print(f"  Rigid bodies: {summary.rigid_body_count}")
    print(f"  Joints: {summary.joint_count}")
    print(f"  Soft bodies: {summary.soft_body_count}")
    print(f"  Soft-body anchors: {summary.soft_body_anchor_count}")
    print(f"  Pinned vertices: {summary.pinned_vertex_count}")


def _print_scan_dependency_summary(
    result: PmxHeaderScanResult,
) -> None:
    """Print PMX texture-reference summary."""

    summary = result.dependency_summary

    if summary is None:
        return

    print("Texture dependencies:")
    print(f"  Declared paths: {summary.declared_texture_path_count}")
    print(f"  Material texture references: {summary.material_texture_reference_count}")
    print(f"  Sphere texture references: {summary.sphere_texture_reference_count}")
    print(f"  Toon texture references: {summary.toon_texture_reference_count}")
    print(f"  Total references: {summary.total_texture_reference_count}")

    if summary.referenced_texture_paths:
        print("  Referenced paths:")
        for texture_index, texture_path in zip(
            summary.referenced_texture_indices,
            summary.referenced_texture_paths,
            strict=True,
        ):
            print(f"    [{texture_index}] {texture_path}")

    if summary.unreferenced_texture_paths:
        print("  Unreferenced paths:")
        for texture_index, texture_path in zip(
            summary.unreferenced_texture_indices,
            summary.unreferenced_texture_paths,
            strict=True,
        ):
            print(f"    [{texture_index}] {texture_path}")


def _print_scan_result(
    file_path: Path,
    result: PmxHeaderScanResult,
) -> None:
    """Print one human-readable PMX structural scan result."""

    model_name = result.model_info.local_name if result.model_info is not None else None
    detected_format = (
        result.detected_format.upper()
        if result.detected_format is not None
        else "unknown"
    )

    print(f"File: {file_path.as_posix()}")
    print(f"Status: {result.status}")
    print(f"Format: {detected_format}")
    print(f"Version: {_format_scan_value(result.version)}")
    print(f"Encoding: {_format_scan_value(result.encoding)}")
    print(f"Model name: {_format_scan_value(model_name)}")
    print(f"Scan complete: {'yes' if result.scan_complete else 'no'}")
    print(f"File size: {_format_scan_value(result.file_size)}")
    print(f"Bytes consumed: {result.bytes_consumed}")
    print(f"Bytes remaining: {_format_scan_value(result.bytes_remaining)}")
    print(f"Trailing bytes: {_format_scan_value(result.trailing_byte_count)}")

    _print_scan_section_summary(result)
    _print_scan_dependency_summary(result)

    for message in result.warnings:
        print(f"[WARNING] {message}")

    for message in result.errors:
        print(f"[ERROR] {message}")


def _run_scan(arguments: argparse.Namespace) -> int:
    """Structurally scan one PMX model file."""

    file_path = Path(arguments.path)
    input_error = _validate_input_file(file_path)

    if input_error is not None:
        print(f"[ERROR] scan: {input_error}")
        return 2

    try:
        result = scan_pmx_structure(file_path)
    except Exception as error:
        message = f"Internal scan failure: {error}"

        if arguments.json:
            print(
                json.dumps(
                    {
                        "path": file_path.as_posix(),
                        "status": "error",
                        "internal_error": True,
                        "errors": [message],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(
                f"[ERROR] scan: {message}",
                file=sys.stderr,
            )

        return 3

    payload = {
        "path": file_path.as_posix(),
        **result.to_dict(),
    }

    if arguments.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_scan_result(file_path, result)

    if result.errors:
        return 1

    return 0


def _print_roundtrip_result(result: PmxRoundTripResult) -> None:
    """Print one successful verified PMX round-trip report."""

    print(f"Input: {result.input_path.as_posix()}")
    print(f"Output: {result.output_path.as_posix()}")
    print("Status: ok")
    print(f"Version: {result.version:.1f}")
    print(f"Encoding: {result.encoding}")
    print(f"Model name: {result.model_name}")
    print("Semantic equality: yes")
    print(f"Byte-identical: {'yes' if result.byte_identical else 'no'}")
    print(f"Input size: {result.input_size}")
    print(f"Output size: {result.output_size}")
    print(f"Input SHA-256: {result.input_sha256}")
    print(f"Output SHA-256: {result.output_sha256}")
    print("Sections:")
    for name, count in result.section_counts:
        print(f"  {name}: {count}")


def _print_roundtrip_error(
    input_path: Path,
    output_path: Path,
    message: str,
    *,
    json_output: bool,
    error_type: str,
) -> None:
    """Print one stable path, document, or verification failure."""

    if json_output:
        print(
            json.dumps(
                {
                    "status": "error",
                    "input_path": input_path.as_posix(),
                    "output_path": output_path.as_posix(),
                    "error_type": error_type,
                    "errors": [diagnostic.message],
                    "error": diagnostic.to_dict(),
                },
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
        return

    print(f"[ERROR] roundtrip: {message}", file=sys.stderr)


def _run_roundtrip(arguments: argparse.Namespace) -> int:
    """Write one explicitly requested and semantically verified PMX copy."""

    input_path = Path(arguments.input)
    output_path = Path(arguments.output)
    try:
        result = roundtrip_pmx(
            input_path,
            output_path,
            overwrite=arguments.overwrite,
        )
    except PmxRoundTripPathError as error:
        _print_roundtrip_error(
            input_path,
            output_path,
            str(error),
            json_output=arguments.json,
            error_type="path_policy",
        )
        return 2
    except (BinaryParseError, PmxValidationError) as error:
        _print_roundtrip_error(
            input_path,
            output_path,
            str(error),
            json_output=arguments.json,
            error_type="invalid_pmx",
        )
        return 1
    except PmxRoundTripVerificationError as error:
        _print_roundtrip_error(
            input_path,
            output_path,
            str(error),
            json_output=arguments.json,
            error_type="verification",
        )
        return 3
    except OSError as error:
        _print_roundtrip_error(
            input_path,
            output_path,
            f"File operation failed: {error}",
            json_output=arguments.json,
            error_type="io",
        )
        return 2

    if arguments.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_roundtrip_result(result)
    return 0


def _new_edit_diagnostic(
    phase: PmxEditPhase,
    message: str,
) -> PmxEditDiagnostic:
    """Build one simple stable diagnostic for an expected CLI failure."""

    return PmxEditDiagnostic(
        code=default_diagnostic_code(phase),
        phase=phase,
        message=message,
    )


def _phase_for_runtime_plan_error(error: PmxEditPlanError) -> PmxEditPhase:
    """Map one validated-plan runtime failure to its deterministic phase."""

    if error.operation_index is None and error.field == "expected_source_sha256":
        return PmxEditPhase.PREFLIGHT
    return PmxEditPhase.APPLY


def _new_edit_io_diagnostic(
    phase: PmxEditPhase,
    message: str,
    error: OSError,
) -> PmxEditDiagnostic:
    """Build one stable filesystem diagnostic without exposing OS repr text."""

    details = ((("errno", error.errno),) if type(error.errno) is int else ())
    return PmxEditDiagnostic(
        code=default_diagnostic_code(phase),
        phase=phase,
        message=message,
        details=details,
    )


def _print_edit_error(
    input_path: Path,
    plan_path: Path,
    output_path: Path | None,
    diagnostic: PmxEditDiagnostic,
    *,
    json_output: bool,
    error_type: str,
    dry_run: bool,
) -> None:
    """Print one stable expected edit failure in text or JSON form."""

    if json_output:
        print(
            json.dumps(
                {
                    "status": "error",
                    "dry_run": dry_run,
                    "input_path": input_path.as_posix(),
                    "plan_path": plan_path.as_posix(),
                    "output_path": (
                        output_path.as_posix()
                        if output_path is not None
                        else None
                    ),
                    "error_type": error_type,
                    "errors": [diagnostic.message],
                "error": diagnostic.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    rendered = render_pmx_edit_diagnostic_text(diagnostic).rstrip("\n")
    print(f"[ERROR] edit: {rendered}", file=sys.stderr)


def _edit_path_error(path: Path, label: str) -> str | None:
    """Return one role-specific error for an unreadable edit input path."""

    if not path.exists():
        return f"{label} file does not exist: {path}"
    if not path.is_file():
        return f"{label} path is not a file: {path}"
    return None


def _run_edit(arguments: argparse.Namespace) -> int:
    """Preview or atomically write one verified PMX edit plan."""

    input_path = Path(arguments.input)
    plan_path = Path(arguments.plan)
    output_path = Path(arguments.output) if arguments.output is not None else None

    def print_error(
        diagnostic: PmxEditDiagnostic,
        error_type: str,
    ) -> None:
        _print_edit_error(
            input_path,
            plan_path,
            output_path,
            diagnostic,
            json_output=arguments.json,
            error_type=error_type,
            dry_run=arguments.dry_run,
        )

    if arguments.overwrite and output_path is None:
        print_error(
            _new_edit_diagnostic(
                PmxEditPhase.PREFLIGHT,
                "--overwrite requires an output path.",
            ),
            "usage",
        )
        return 2
    if not arguments.dry_run and output_path is None:
        print_error(
            _new_edit_diagnostic(
                PmxEditPhase.PREFLIGHT,
                "Output path is required unless --dry-run is used.",
            ),
            "usage",
        )
        return 2

    for path, label in ((input_path, "Input"), (plan_path, "Plan")):
        path_error = _edit_path_error(path, label)
        if path_error is not None:
            print_error(
                _new_edit_diagnostic(PmxEditPhase.PREFLIGHT, path_error),
                "path_policy",
            )
            return 2

    try:
        plan = load_pmx_edit_plan(plan_path)
    except PmxEditPlanDecodeError as error:
        print_error(
            diagnostic_from_plan_error(
                error,
                phase=PmxEditPhase.PLAN_DECODE,
            ),
            "invalid_plan",
        )
        return 1
    except PmxEditPlanError as error:
        print_error(
            diagnostic_from_plan_error(
                error,
                phase=PmxEditPhase.PLAN_VALIDATE,
            ),
            "invalid_plan",
        )
        return 1
    except OSError as error:
        print_error(
            _new_edit_io_diagnostic(
                PmxEditPhase.PLAN_READ,
                "Unable to read edit-plan file.",
                error,
            ),
            "io",
        )
        return 2

    if arguments.dry_run:
        try:
            source_bytes = input_path.read_bytes()
        except OSError as error:
            print_error(
                _new_edit_io_diagnostic(
                    PmxEditPhase.SOURCE_READ,
                    "Unable to read source PMX file.",
                    error,
                ),
                "io",
            )
            return 2

        try:
            preview = dry_run_pmx_edit(source_bytes, plan)
        except PmxEditPlanError as error:
            print_error(
                diagnostic_from_plan_error(
                    error,
                    phase=_phase_for_runtime_plan_error(error),
                ),
                "invalid_plan",
            )
            return 1
        except BinaryParseError as error:
            print_error(
                _new_edit_diagnostic(PmxEditPhase.SOURCE_PARSE, str(error)),
                "invalid_pmx",
            )
            return 1
        except PmxValidationError as error:
            print_error(
                _new_edit_diagnostic(
                    PmxEditPhase.DOCUMENT_VALIDATE,
                    str(error),
                ),
                "invalid_pmx",
            )
            return 1
        except PmxEditVerificationError as error:
            print_error(
                _new_edit_diagnostic(
                    PmxEditPhase.SEMANTIC_VERIFY,
                    str(error),
                ),
                "verification",
            )
            return 1

        if arguments.json:
            sys.stdout.write(render_pmx_edit_preview_json(preview))
        else:
            sys.stdout.write(
                render_pmx_edit_preview_text(
                    preview,
                    include_changes=False,
                )
            )
        return 0

    assert output_path is not None
    try:
        result = write_pmx_edit(
            input_path,
            output_path,
            plan,
            overwrite=arguments.overwrite,
        )
    except PmxEditPathError as error:
        print_error(
            _new_edit_diagnostic(PmxEditPhase.PREFLIGHT, str(error)),
            "path_policy",
        )
        return 2
    except PmxEditPlanError as error:
        print_error(
            diagnostic_from_plan_error(
                error,
                phase=_phase_for_runtime_plan_error(error),
            ),
            "invalid_plan",
        )
        return 1
    except BinaryParseError as error:
        print_error(
            _new_edit_diagnostic(PmxEditPhase.SOURCE_PARSE, str(error)),
            "invalid_pmx",
        )
        return 1
    except PmxValidationError as error:
        print_error(
            _new_edit_diagnostic(
                PmxEditPhase.DOCUMENT_VALIDATE,
                str(error),
            ),
            "invalid_pmx",
        )
        return 1
    except PmxEditVerificationError as error:
        print_error(
            _new_edit_diagnostic(
                PmxEditPhase.SEMANTIC_VERIFY,
                str(error),
            ),
            "verification",
        )
        return 1
    except OSError as error:
        print_error(
            _new_edit_io_diagnostic(
                PmxEditPhase.OUTPUT_COMMIT,
                "File operation failed.",
                error,
            ),
            "io",
        )
        return 2

    if arguments.json:
        sys.stdout.write(render_pmx_edit_write_json(result))
    else:
        sys.stdout.write(render_pmx_edit_write_text(result))
    return 0


def _doctor_status(
    scan_result: PmxHeaderScanResult,
    diagnostics: TextureDependencyDiagnostics | None,
) -> str:
    """Return the highest severity from scan and dependency diagnostics."""

    if scan_result.errors:
        return "error"

    if diagnostics is not None and diagnostics.error_count:
        return "error"

    if scan_result.warnings:
        return "warning"

    if diagnostics is not None and diagnostics.warning_count:
        return "warning"

    return "ok"


def _doctor_payload(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    diagnostics: TextureDependencyDiagnostics | None,
) -> dict[str, Any]:
    """Build one stable, JSON-serializable doctor payload."""

    return {
        "path": file_path.as_posix(),
        "status": _doctor_status(scan_result, diagnostics),
        "scan": scan_result.to_dict(),
        "texture_diagnostics": (
            diagnostics.to_dict() if diagnostics is not None else None
        ),
    }


def _print_texture_diagnostics(
    diagnostics: TextureDependencyDiagnostics,
) -> None:
    """Print filesystem diagnostics for declared PMX texture paths."""

    print("Texture filesystem diagnostics:")
    print(f"  Status: {diagnostics.status}")
    print(f"  Declared: {diagnostics.declared_texture_count}")
    print(f"  Referenced: {diagnostics.referenced_texture_count}")
    print(f"  Unreferenced: {diagnostics.unreferenced_texture_count}")
    print(f"  Existing files: {diagnostics.existing_file_count}")
    print(f"  Missing files: {diagnostics.missing_file_count}")
    print(f"  Unresolved paths: {diagnostics.unresolved_path_count}")
    print(f"  Portable paths: {diagnostics.portable_path_count}")
    print(f"  Non-portable paths: {diagnostics.non_portable_path_count}")
    print(f"  Warnings: {diagnostics.warning_count}")
    print(f"  Errors: {diagnostics.error_count}")

    if not diagnostics.dependencies:
        return

    print("Dependencies:")
    for dependency in diagnostics.dependencies:
        reference_label = "referenced" if dependency.is_referenced else "unreferenced"
        print(
            f"  [{dependency.texture_index}] "
            f"{dependency.status} | {reference_label} | "
            f"{dependency.raw_path}"
        )

        if dependency.resolved_path is not None:
            print(f"    Resolved: {dependency.resolved_path}")

        for issue in dependency.issues:
            print(f"    [{issue.severity.upper()}] {issue.code}: {issue.message}")


def _print_doctor_result(
    file_path: Path,
    scan_result: PmxHeaderScanResult,
    diagnostics: TextureDependencyDiagnostics | None,
) -> None:
    """Print a combined structural and texture dependency diagnosis."""

    model_name = (
        scan_result.model_info.local_name
        if scan_result.model_info is not None
        else None
    )
    detected_format = (
        scan_result.detected_format.upper()
        if scan_result.detected_format is not None
        else "unknown"
    )

    print(f"File: {file_path.as_posix()}")
    print(f"Status: {_doctor_status(scan_result, diagnostics)}")
    print("Structural scan:")
    print(f"  Status: {scan_result.status}")
    print(f"  Format: {detected_format}")
    print(f"  Version: {_format_scan_value(scan_result.version)}")
    print(f"  Model name: {_format_scan_value(model_name)}")
    print(f"  Complete: {'yes' if scan_result.scan_complete else 'no'}")
    print(f"  Trailing bytes: {_format_scan_value(scan_result.trailing_byte_count)}")

    for message in scan_result.warnings:
        print(f"  [WARNING] {message}")

    for message in scan_result.errors:
        print(f"  [ERROR] {message}")

    if diagnostics is not None:
        _print_texture_diagnostics(diagnostics)


def _print_doctor_error(
    file_path: Path,
    message: str,
    *,
    json_output: bool,
    internal_error: bool,
) -> None:
    """Print one path or internal doctor error in the requested format."""

    if json_output:
        print(
            json.dumps(
                {
                    "path": file_path.as_posix(),
                    "status": "error",
                    "internal_error": internal_error,
                    "errors": [message],
                    "scan": None,
                    "texture_diagnostics": None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    print(f"[ERROR] doctor: {message}", file=sys.stderr)


def _run_doctor(arguments: argparse.Namespace) -> int:
    """Scan one PMX model and diagnose its texture dependencies."""

    file_path = Path(arguments.path)
    input_error = _validate_input_file(file_path)

    if input_error is not None:
        _print_doctor_error(
            file_path,
            input_error,
            json_output=arguments.json,
            internal_error=False,
        )
        return 2

    try:
        scan_result = scan_pmx_structure(file_path)
    except Exception as error:
        _print_doctor_error(
            file_path,
            f"Internal scan failure: {error}",
            json_output=arguments.json,
            internal_error=True,
        )
        return 3

    diagnostics: TextureDependencyDiagnostics | None = None

    if not scan_result.errors and scan_result.scan_complete:
        dependency_summary = scan_result.dependency_summary

        if dependency_summary is None:
            _print_doctor_error(
                file_path,
                "Complete PMX scan did not produce a dependency summary.",
                json_output=arguments.json,
                internal_error=True,
            )
            return 3

        try:
            diagnostics = diagnose_texture_dependencies(
                model_path=file_path,
                texture_paths=scan_result.texture_paths,
                referenced_texture_indices=(
                    dependency_summary.referenced_texture_indices
                ),
            )
        except Exception as error:
            _print_doctor_error(
                file_path,
                f"Internal dependency diagnostic failure: {error}",
                json_output=arguments.json,
                internal_error=True,
            )
            return 3

    payload = _doctor_payload(
        file_path,
        scan_result,
        diagnostics,
    )

    if arguments.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_doctor_result(
            file_path,
            scan_result,
            diagnostics,
        )

    if scan_result.errors:
        return 1

    if diagnostics is not None and diagnostics.error_count:
        return 1

    return 0


def run(argv: Sequence[str] | None = None) -> int:
    """Run the registry command-line application."""

    parser = build_argument_parser()
    arguments = parser.parse_args(normalize_arguments(argv))

    if arguments.command == "validate":
        return _run_validate(arguments)

    if arguments.command == "hash":
        return _run_hash(arguments)

    if arguments.command == "inspect":
        return _run_inspect(arguments)

    if arguments.command == "scan":
        return _run_scan(arguments)

    if arguments.command == "roundtrip":
        return _run_roundtrip(arguments)

    if arguments.command == "edit":
        return _run_edit(arguments)

    if arguments.command == "doctor":
        return _run_doctor(arguments)

    if arguments.command == "bones":
        return run_bones_command(
            path=arguments.path,
            tree=arguments.tree,
            details=arguments.details,
            search_query=arguments.search,
            ik_only=arguments.ik_only,
            json_output=arguments.json,
        )

    if arguments.command == "rig":
        return run_rig_command(
            path=arguments.path,
            unmapped=arguments.unmapped,
            role=arguments.role,
            export_map=arguments.export_map,
            json_output=arguments.json,
        )

    parser.error(f"Unsupported command: {arguments.command}")
    return 2


def _print_unexpected_edit_error(*, json_output: bool) -> None:
    """Render one process-boundary edit failure without exception internals."""

    diagnostic = _new_edit_diagnostic(
        PmxEditPhase.INTERNAL,
        "Unexpected internal edit failure.",
    )
    if json_output:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error_type": "internal",
                    "errors": [diagnostic.message],
                    "error": diagnostic.to_dict(),
                },
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
        return

    rendered = render_pmx_edit_diagnostic_text(diagnostic).rstrip("\n")
    print(f"[ERROR] edit: {rendered}", file=sys.stderr)


def main() -> None:
    """Command-line entry point."""

    _configure_utf8_standard_streams()

    try:
        exit_code = run()
    except Exception as error:
        normalized_arguments = normalize_arguments(None)
        if normalized_arguments and normalized_arguments[0] == "edit":
            _print_unexpected_edit_error(
                json_output="--json" in normalized_arguments,
            )
        else:
            print(
                f"[ERROR] internal: {error}",
                file=sys.stderr,
            )
        exit_code = 3

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
