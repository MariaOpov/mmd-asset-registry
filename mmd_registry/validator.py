"""Schema and usage-mode validation for MMD assets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mmd_registry.constants import (
    LATEST_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    UNKNOWN_TEXT_VALUES,
    VALID_ASSET_TYPES,
    VALID_MODES,
    VALID_STATUSES,
    VALID_USAGE_VALUES,
)


ASSET_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(slots=True)
class AssetValidationResult:
    """Validation result for one asset."""

    asset_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "error"

        if self.warnings:
            return "warning"

        return "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "id": self.asset_id,
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "infos": list(self.infos),
        }


@dataclass(slots=True)
class RegistryValidationResult:
    """Validation result for a complete registry."""

    mode: str
    registry_version: str | None = None
    assets: list[AssetValidationResult] = field(default_factory=list)
    registry_errors: list[str] = field(default_factory=list)
    registry_warnings: list[str] = field(default_factory=list)
    registry_infos: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.registry_errors) + sum(
            len(asset.errors) for asset in self.assets
        )

    @property
    def warning_count(self) -> int:
        return len(self.registry_warnings) + sum(
            len(asset.warnings) for asset in self.assets
        )

    @property
    def info_count(self) -> int:
        return len(self.registry_infos) + sum(len(asset.infos) for asset in self.assets)

    @property
    def status(self) -> str:
        if self.error_count:
            return "failed"

        if self.warning_count:
            return "passed_with_warnings"

        return "passed"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return {
            "registry_version": self.registry_version,
            "mode": self.mode,
            "status": self.status,
            "summary": {
                "assets": len(self.assets),
                "warnings": self.warning_count,
                "errors": self.error_count,
                "infos": self.info_count,
            },
            "registry_errors": list(self.registry_errors),
            "registry_warnings": list(self.registry_warnings),
            "registry_infos": list(self.registry_infos),
            "assets": [asset.to_dict() for asset in self.assets],
        }


def _non_empty_string(value: Any) -> str | None:
    """Return a stripped string or None for invalid/empty values."""

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    return value


def _is_unknown_text(value: Any) -> bool:
    """Return True when a text value is absent or explicitly unknown."""

    text = _non_empty_string(value)

    if text is None:
        return True

    return text.lower() in UNKNOWN_TEXT_VALUES


def _validate_optional_string(
    mapping: dict[str, Any],
    field_name: str,
    label: str,
    result: AssetValidationResult,
) -> None:
    """Validate a field that may contain a string or null."""

    if field_name not in mapping:
        return

    value = mapping[field_name]

    if value is not None and not isinstance(value, str):
        result.errors.append(f"{label} must be a string or null.")


def _resolve_source_path(
    source_path: str,
    project_root: Path,
) -> Path:
    """Resolve an asset path relative to the registry project."""

    path = Path(source_path)

    if path.is_absolute():
        return path

    return project_root / path


def _validate_usage_value(
    usage_rules: dict[str, Any],
    field_name: str,
    result: AssetValidationResult,
) -> str | None:
    """Validate and return one usage-rule value."""

    value = _non_empty_string(usage_rules.get(field_name))

    if value is None:
        result.errors.append(f"usage_rules.{field_name} must be a non-empty string.")
        return None

    if value not in VALID_USAGE_VALUES:
        allowed_values = ", ".join(sorted(VALID_USAGE_VALUES))
        result.errors.append(
            f"Invalid usage_rules.{field_name} value "
            f"'{value}'. Expected one of: {allowed_values}."
        )
        return None

    return value


def validate_asset(
    asset: Any,
    index: int,
    project_root: Path,
    mode: str = "private",
) -> AssetValidationResult:
    """Validate one asset using the selected usage mode."""

    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported validation mode: {mode}")

    if not isinstance(asset, dict):
        result = AssetValidationResult(asset_id=f"asset_{index}")
        result.errors.append("Asset entry must be a YAML object.")
        return result

    raw_asset_id = asset.get("id")
    asset_id = _non_empty_string(raw_asset_id) or f"asset_{index}"
    result = AssetValidationResult(asset_id=asset_id)

    if _non_empty_string(raw_asset_id) is None:
        result.errors.append("id must be a non-empty string.")
    elif not ASSET_ID_PATTERN.fullmatch(asset_id):
        result.errors.append(
            "id may contain only lowercase letters, numbers, underscores, and hyphens."
        )

    display_name = _non_empty_string(asset.get("display_name"))

    if display_name is None:
        result.errors.append("display_name must be a non-empty string.")

    asset_type = _non_empty_string(asset.get("asset_type"))

    if asset_type is None:
        result.errors.append("asset_type must be a non-empty string.")
    elif asset_type not in VALID_ASSET_TYPES:
        allowed_types = ", ".join(sorted(VALID_ASSET_TYPES))
        result.errors.append(
            f"Invalid asset_type '{asset_type}'. Expected one of: {allowed_types}."
        )

    pipeline_character = asset.get("pipeline_character")

    if asset_type == "character_model":
        if _non_empty_string(pipeline_character) is None:
            result.errors.append("pipeline_character is required for character models.")
    elif pipeline_character is not None and not isinstance(
        pipeline_character,
        str,
    ):
        result.errors.append("pipeline_character must be a string or null.")

    source_path = _non_empty_string(asset.get("source_path"))

    if source_path is None:
        result.errors.append("source_path must be a non-empty string.")
    else:
        resolved_path = _resolve_source_path(source_path, project_root)

        if not resolved_path.exists():
            result.errors.append(f"Source file not found: {resolved_path}")
        elif not resolved_path.is_file():
            result.errors.append(f"source_path is not a file: {resolved_path}")

    status = _non_empty_string(asset.get("status"))

    if status is None:
        result.errors.append("status must be a non-empty string.")
    elif status not in VALID_STATUSES:
        allowed_statuses = ", ".join(sorted(VALID_STATUSES))
        result.errors.append(
            f"Invalid status '{status}'. Expected one of: {allowed_statuses}."
        )
    elif status == "blocked":
        result.errors.append("Asset status is blocked.")
    elif status == "archived":
        result.warnings.append("Asset status is archived.")
    elif status == "review":
        result.infos.append("Asset is still under review.")

    creator = asset.get("creator")

    if not isinstance(creator, dict):
        result.errors.append("creator must be a YAML object.")
    else:
        creator_name = creator.get("name")

        if _non_empty_string(creator_name) is None:
            result.errors.append("creator.name must be a non-empty string.")
        elif _is_unknown_text(creator_name):
            result.warnings.append("Creator name has not been recorded.")

        _validate_optional_string(
            creator,
            "profile_url",
            "creator.profile_url",
            result,
        )

    source = asset.get("source")

    if not isinstance(source, dict):
        result.errors.append("source must be a YAML object.")
    else:
        _validate_optional_string(
            source,
            "page_url",
            "source.page_url",
            result,
        )
        _validate_optional_string(
            source,
            "downloaded_at",
            "source.downloaded_at",
            result,
        )

        if _is_unknown_text(source.get("page_url")):
            if mode == "private":
                result.infos.append("Original source page has not been recorded.")
            else:
                result.warnings.append("Original source page has not been recorded.")

    credit = asset.get("credit")

    if not isinstance(credit, dict):
        result.errors.append("credit must be a YAML object.")
    else:
        credit_required = credit.get("required")

        if not isinstance(credit_required, bool):
            result.errors.append("credit.required must be true or false.")

        _validate_optional_string(
            credit,
            "text",
            "credit.text",
            result,
        )
        _validate_optional_string(
            credit,
            "url",
            "credit.url",
            result,
        )

        if credit_required is True and _is_unknown_text(credit.get("text")):
            message = "Credit is required, but credit.text is missing."

            if mode == "private":
                result.warnings.append(message)
            else:
                result.errors.append(message)

    usage_rules = asset.get("usage_rules")

    if not isinstance(usage_rules, dict):
        result.errors.append("usage_rules must be a YAML object.")
    else:
        editing = _validate_usage_value(
            usage_rules,
            "editing",
            result,
        )
        redistribution = _validate_usage_value(
            usage_rules,
            "redistribution",
            result,
        )
        commercial_use = _validate_usage_value(
            usage_rules,
            "commercial_use",
            result,
        )

        _validate_optional_string(
            usage_rules,
            "notes",
            "usage_rules.notes",
            result,
        )

        if editing == "unclear":
            if mode == "private":
                result.infos.append("Editing rule has not been recorded.")
            else:
                result.warnings.append("Editing rule has not been recorded.")
        elif editing == "prohibited":
            result.warnings.append("Editing is marked as prohibited.")

        if redistribution in {"unclear", "prohibited"}:
            result.infos.append(
                "Redistribution rule does not affect normal video output."
            )

        if mode == "commercial":
            if commercial_use == "prohibited":
                result.errors.append("Commercial use is prohibited.")
            elif commercial_use == "unclear":
                result.errors.append("Commercial-use rule has not been recorded.")
            elif commercial_use == "conditional":
                result.warnings.append(
                    "Commercial use is conditional; review the notes."
                )

    tags = asset.get("tags")

    if tags is not None:
        if not isinstance(tags, list):
            result.errors.append("tags must be a YAML list.")
        elif any(_non_empty_string(tag) is None for tag in tags):
            result.errors.append("Every tag must be a non-empty string.")

    notes = asset.get("notes")

    if notes is not None and not isinstance(notes, str):
        result.errors.append("notes must be a string or null.")

    return result


def validate_registry(
    registry: Any,
    project_root: Path,
    mode: str = "private",
) -> RegistryValidationResult:
    """Validate a complete registry using a supported schema version."""

    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported validation mode: {mode}")

    result = RegistryValidationResult(mode=mode)

    if not isinstance(registry, dict):
        result.registry_errors.append("Registry root must be a YAML object.")
        return result

    registry_version = _non_empty_string(registry.get("registry_version"))
    result.registry_version = registry_version

    if registry_version is None:
        result.registry_errors.append("registry_version must be a non-empty string.")
    elif registry_version not in SUPPORTED_SCHEMA_VERSIONS:
        supported_versions = ", ".join(sorted(SUPPORTED_SCHEMA_VERSIONS))
        result.registry_errors.append(
            f"Unsupported registry_version '{registry_version}'. "
            f"Supported versions: {supported_versions}."
        )
    elif registry_version != LATEST_SCHEMA_VERSION:
        result.registry_infos.append(
            f"Registry schema {registry_version} is supported for backward "
            f"compatibility; latest is {LATEST_SCHEMA_VERSION}."
        )

    assets = registry.get("assets")

    if not isinstance(assets, list):
        result.registry_errors.append("'assets' must be a YAML list.")
        return result

    if not assets:
        result.registry_warnings.append("No assets are registered.")
        return result

    seen_ids: set[str] = set()

    for index, asset in enumerate(assets, start=1):
        asset_result = validate_asset(
            asset=asset,
            index=index,
            project_root=project_root,
            mode=mode,
        )

        if asset_result.asset_id in seen_ids:
            asset_result.errors.append(f"Duplicate asset id: {asset_result.asset_id}")
        else:
            seen_ids.add(asset_result.asset_id)

        result.assets.append(asset_result)

    return result
