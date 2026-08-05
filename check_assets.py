import json
import sys
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
REGISTRY_FILE = PROJECT_ROOT / "assets.yaml"
REPORTS_DIR = PROJECT_ROOT / "reports"
REPORT_FILE = REPORTS_DIR / "validation_report.json"

REQUIRED_ASSET_FIELDS = (
    "id",
    "display_name",
    "pipeline_character",
    "source_path",
    "creator",
    "license",
    "status",
    "notes",
)

REQUIRED_LICENSE_FIELDS = (
    "commercial_use",
    "redistribution",
    "modification",
)

UNKNOWN_VALUES = {
    "",
    "unknown",
    "tbd",
    "not_verified",
    "not verified",
    None,
}


def load_registry(file_path: Path) -> dict[str, Any]:
    """Read and parse the YAML registry."""

    if not file_path.exists():
        raise FileNotFoundError(f"Registry file does not exist: {file_path}")

    try:
        with file_path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except yaml.YAMLError as error:
        raise ValueError(f"Invalid YAML syntax in {file_path.name}: {error}") from error

    if data is None:
        raise ValueError("Registry file is empty.")

    if not isinstance(data, dict):
        raise ValueError("Registry root must be a YAML object.")

    return data


def is_unknown(value: Any) -> bool:
    """Return True when a registry value has not been verified."""

    if isinstance(value, str):
        return value.strip().lower() in UNKNOWN_VALUES

    return value in UNKNOWN_VALUES


def resolve_source_path(source_path: str) -> Path:
    """Resolve relative paths from the project directory."""

    path = Path(source_path)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def validate_asset(
    asset: Any,
    index: int,
) -> tuple[str, list[str], list[str]]:
    """Validate one asset and return its errors and warnings."""

    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(asset, dict):
        return (
            f"asset_{index}",
            ["Asset entry must be a YAML object."],
            [],
        )

    asset_id = str(asset.get("id") or f"asset_{index}")

    for field in REQUIRED_ASSET_FIELDS:
        if field not in asset:
            errors.append(f"Missing required field: {field}")

    source_path = asset.get("source_path")

    if source_path is not None:
        if not isinstance(source_path, str) or not source_path.strip():
            errors.append("source_path must be a non-empty string.")
        else:
            resolved_path = resolve_source_path(source_path)

            if not resolved_path.exists():
                errors.append(f"Source file not found: {resolved_path}")
            elif not resolved_path.is_file():
                errors.append(f"source_path is not a file: {resolved_path}")

    creator = asset.get("creator")

    if is_unknown(creator):
        warnings.append("Creator information is unknown.")

    license_data = asset.get("license")

    if license_data is not None:
        if not isinstance(license_data, dict):
            errors.append("license must be a YAML object.")
        else:
            for field in REQUIRED_LICENSE_FIELDS:
                if field not in license_data:
                    errors.append(f"Missing required license field: license.{field}")
                elif is_unknown(license_data[field]):
                    warnings.append(f"License value is unknown: license.{field}")

    status = asset.get("status")

    if is_unknown(status):
        warnings.append("Asset status is unknown.")

    return asset_id, errors, warnings


def write_report(report: dict[str, Any]) -> None:
    """Write the validation result as a JSON report."""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with REPORT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")


def main() -> int:
    """Run registry validation and generate a JSON report."""

    print("MMD Asset & License Registry v0.1")
    print(f"Registry: {REGISTRY_FILE}")
    print("-" * 60)

    report: dict[str, Any] = {
        "registry_version": None,
        "registry_file": str(REGISTRY_FILE),
        "status": "failed",
        "summary": {
            "assets": 0,
            "warnings": 0,
            "errors": 0,
        },
        "assets": [],
    }

    try:
        registry = load_registry(REGISTRY_FILE)
    except (FileNotFoundError, ValueError) as error:
        error_message = str(error)

        print(f"[ERROR] registry: {error_message}")

        report["summary"]["errors"] = 1
        report["registry_errors"] = [error_message]

        write_report(report)
        print(f"Report: {REPORT_FILE}")

        return 1

    report["registry_version"] = registry.get("registry_version")

    assets = registry.get("assets")

    if not isinstance(assets, list):
        error_message = "'assets' must be a YAML list."

        print(f"[ERROR] registry: {error_message}")

        report["summary"]["errors"] = 1
        report["registry_errors"] = [error_message]

        write_report(report)
        print(f"Report: {REPORT_FILE}")

        return 1

    report["summary"]["assets"] = len(assets)

    if not assets:
        print("[WARNING] registry: No assets are registered.")

        report["status"] = "passed_with_warnings"
        report["summary"]["warnings"] = 1
        report["registry_warnings"] = ["No assets are registered."]

        write_report(report)
        print(f"Report: {REPORT_FILE}")

        return 0

    total_errors = 0
    total_warnings = 0
    seen_ids: set[str] = set()
    asset_reports: list[dict[str, Any]] = []

    for index, asset in enumerate(assets, start=1):
        asset_id, errors, warnings = validate_asset(asset, index)

        if asset_id in seen_ids:
            errors.append(f"Duplicate asset id: {asset_id}")
        else:
            seen_ids.add(asset_id)

        if errors:
            asset_status = "error"
        elif warnings:
            asset_status = "warning"
        else:
            asset_status = "ok"

        asset_reports.append(
            {
                "id": asset_id,
                "status": asset_status,
                "warnings": warnings,
                "errors": errors,
            }
        )

        if not errors and not warnings:
            print(f"[OK] {asset_id}")
        else:
            for warning in warnings:
                print(f"[WARNING] {asset_id}: {warning}")

            for error in errors:
                print(f"[ERROR] {asset_id}: {error}")

        total_warnings += len(warnings)
        total_errors += len(errors)

    report["assets"] = asset_reports
    report["summary"] = {
        "assets": len(assets),
        "warnings": total_warnings,
        "errors": total_errors,
    }

    if total_errors > 0:
        report["status"] = "failed"
    elif total_warnings > 0:
        report["status"] = "passed_with_warnings"
    else:
        report["status"] = "passed"

    write_report(report)

    print("-" * 60)
    print(
        f"Assets: {len(assets)} | Warnings: {total_warnings} | Errors: {total_errors}"
    )
    print(f"Report: {REPORT_FILE}")

    if total_errors > 0:
        print("Validation failed.")
        return 1

    print("Validation completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
