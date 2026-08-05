"""Constants shared by the registry validator."""

from typing import Final


LATEST_SCHEMA_VERSION: Final[str] = "0.3"

SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset(
    {
        "0.2",
        "0.3",
    }
)

# Compatibility alias for callers that previously imported SCHEMA_VERSION.
SCHEMA_VERSION: Final[str] = LATEST_SCHEMA_VERSION

VALID_MODES: Final[frozenset[str]] = frozenset(
    {
        "private",
        "publish",
        "commercial",
    }
)

VALID_ASSET_TYPES: Final[frozenset[str]] = frozenset(
    {
        "character_model",
        "stage",
        "motion",
        "camera_motion",
        "accessory",
        "effect",
        "texture_pack",
        "audio",
        "other",
    }
)

VALID_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "ready",
        "review",
        "blocked",
        "archived",
    }
)

VALID_USAGE_VALUES: Final[frozenset[str]] = frozenset(
    {
        "allowed",
        "prohibited",
        "conditional",
        "unclear",
        "not_applicable",
    }
)

UNKNOWN_TEXT_VALUES: Final[frozenset[str]] = frozenset(
    {
        "",
        "unknown",
        "unclear",
        "tbd",
        "not_verified",
        "not verified",
    }
)