"""Command-line interface for the MMD Asset Registry."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

import yaml

from mmd_registry import __version__
from mmd_registry.constants import VALID_MODES
from mmd_registry.reporting import (
    build_json_report,
    write_credits_file,
    write_json_report,
)
from mmd_registry.validator import (
    RegistryValidationResult,
    validate_registry,
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


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""

    parser = argparse.ArgumentParser(
        prog="mmd-asset-registry",
        description=(
            "Validate MMD asset provenance, credits, and known usage restrictions."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

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

    return parser


def _resolve_output_path(
    raw_path: str,
    project_root: Path,
) -> Path:
    """Resolve an output path relative to the project root."""

    path = Path(raw_path)

    if path.is_absolute():
        return path

    return project_root / path


def run(argv: Sequence[str] | None = None) -> int:
    """Run the registry command-line application."""

    parser = build_argument_parser()
    arguments = parser.parse_args(argv)

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
