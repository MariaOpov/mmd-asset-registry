"""Command-line interface for the MMD Asset Registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import yaml

from mmd_registry import __version__
from mmd_registry.constants import VALID_MODES
from mmd_registry.hashing import check_file_sha256
from mmd_registry.model_inspection import inspect_model_header
from mmd_registry.model_scanning import (
    PmxHeaderScanResult,
    scan_pmx_structure,
)
from mmd_registry.reporting import (
    build_json_report,
    write_credits_file,
    write_json_report,
)
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
    }
)


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
            "PMX/PMD headers, and structurally scan PMX models."
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

    parser.error(f"Unsupported command: {arguments.command}")
    return 2


def main() -> None:
    """Command-line entry point."""

    try:
        exit_code = run()
    except Exception as error:
        print(
            f"[ERROR] internal: {error}",
            file=sys.stderr,
        )
        exit_code = 3

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
