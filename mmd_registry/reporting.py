"""JSON reports and automatic asset-credit generation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mmd_registry import __version__
from mmd_registry.validator import RegistryValidationResult


def _display_path(path: Path, project_root: Path) -> str:
    """Return a portable relative path when possible."""

    resolved_path = path.resolve()
    resolved_root = project_root.resolve()

    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return str(resolved_path)


def _display_source_path(source_path: str, project_root: Path) -> str:
    """Return a portable registered source path when possible."""

    path = Path(source_path)

    if not path.is_absolute():
        return path.as_posix()

    return _display_path(path, project_root)


def build_json_report(
    result: RegistryValidationResult,
    registry_file: Path,
    project_root: Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the JSON-compatible validation report."""

    timestamp = generated_at

    if timestamp is None:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")

    result_data = result.to_dict()
    asset_reports = result_data["assets"]

    for asset_result, asset_report in zip(result.assets, asset_reports):
        if asset_result.source_path is not None:
            asset_report["source_path"] = _display_source_path(
                asset_result.source_path,
                project_root,
            )

    return {
        "tool_version": __version__,
        "generated_at": timestamp,
        "registry_file": _display_path(
            registry_file,
            project_root,
        ),
        **result_data,
    }


def write_json_report(
    report: dict[str, Any],
    report_file: Path,
) -> None:
    """Write a validation report to disk."""

    report_file.parent.mkdir(parents=True, exist_ok=True)

    with report_file.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )
        file.write("\n")


def generate_credits_markdown(registry: Any) -> str:
    """Generate Markdown credits from registry entries."""

    lines = [
        "# Asset Credits",
        "",
        ("This file was generated automatically by MMD Asset & License Registry."),
        "",
    ]

    if not isinstance(registry, dict):
        lines.extend(
            [
                "_Registry data is invalid._",
                "",
            ]
        )
        return "\n".join(lines)

    assets = registry.get("assets")

    if not isinstance(assets, list):
        lines.extend(
            [
                "_No valid asset list was found._",
                "",
            ]
        )
        return "\n".join(lines)

    credit_lines: list[str] = []
    incomplete_assets: list[str] = []

    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, dict):
            incomplete_assets.append(f"Asset #{index}")
            continue

        asset_name = asset.get("display_name")
        asset_id = asset.get("id")

        if not isinstance(asset_name, str) or not asset_name.strip():
            asset_name = (
                asset_id
                if isinstance(asset_id, str) and asset_id.strip()
                else f"Asset #{index}"
            )

        credit = asset.get("credit")

        if not isinstance(credit, dict):
            incomplete_assets.append(str(asset_name))
            continue

        required = credit.get("required")
        credit_text = credit.get("text")
        credit_url = credit.get("url")

        has_credit_text = isinstance(credit_text, str) and bool(credit_text.strip())

        if required is True and not has_credit_text:
            incomplete_assets.append(str(asset_name))
            continue

        if not has_credit_text:
            continue

        line = f"- **{asset_name}** — {credit_text.strip()}"

        if isinstance(credit_url, str) and credit_url.strip():
            line += f" ([source]({credit_url.strip()}))"

        credit_lines.append(line)

    if credit_lines:
        lines.extend(
            [
                "## Credits",
                "",
                *credit_lines,
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Credits",
                "",
                "_No complete credit entries were found._",
                "",
            ]
        )

    if incomplete_assets:
        lines.extend(
            [
                "## Incomplete Credit Information",
                "",
                *[f"- {asset_name}" for asset_name in incomplete_assets],
                "",
            ]
        )

    return "\n".join(lines)


def write_credits_file(
    registry: Any,
    credits_file: Path,
) -> None:
    """Generate and write a Markdown credit file."""

    credits_file.parent.mkdir(parents=True, exist_ok=True)

    content = generate_credits_markdown(registry)

    credits_file.write_text(
        content,
        encoding="utf-8",
    )
