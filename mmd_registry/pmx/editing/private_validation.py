"""Ephemeral real-model validation for the safe PMX edit pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.pmx import PmxDocument, load_pmx, validate_pmx_document
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditPlanError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.editing.json_loader import load_pmx_edit_plan
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from mmd_registry.pmx.errors import PmxValidationError


_VALIDATION_MARKER = "[mmd-asset-registry private edit validation]"


class PmxPrivateValidationError(RuntimeError):
    """Raised when a private-model invariant is not satisfied."""


@dataclass(frozen=True, slots=True)
class PmxPrivateValidationResult:
    """Privacy-safe report from one ephemeral real-model edit validation."""

    source_name: str
    version: float
    encoding: str
    material_index: int
    source_size_bytes: int
    source_sha256: str
    output_sha256: str
    changed_fields: int
    section_counts: tuple[tuple[str, int], ...]
    temporary_files_removed: bool

    def to_dict(self) -> dict[str, object]:
        """Return a deterministic report without an absolute private path."""

        return {
            "status": "ok",
            "source": {
                "name": self.source_name,
                "version": self.version,
                "encoding": self.encoding,
                "size_bytes": self.source_size_bytes,
                "sha256_before": self.source_sha256,
                "sha256_after": self.source_sha256,
            },
            "edit": {
                "material_index": self.material_index,
                "changed_fields": self.changed_fields,
                "metadata": "passed",
                "material_text": "passed",
                "material_property": "passed",
            },
            "output": {
                "temporary": True,
                "sha256": self.output_sha256,
                "parse_validation": "passed",
                "semantic_verification": "passed",
            },
            "invariants": {
                "source_unchanged": True,
                "section_counts_unchanged": True,
                "unrelated_sections_unchanged": True,
                "references_valid": True,
                "temporary_files_removed": self.temporary_files_removed,
                "private_asset_persisted": False,
            },
            "section_counts": dict(self.section_counts),
        }


def _sha256_bytes(data: bytes) -> str:
    """Return one lowercase SHA-256 digest."""

    return hashlib.sha256(data).hexdigest()


def _section_counts(document: PmxDocument) -> tuple[tuple[str, int], ...]:
    """Return counts that must remain fixed during v0.8 editing."""

    return (
        ("vertices", len(document.vertices)),
        ("surface_indices", len(document.surface_indices)),
        ("textures", len(document.texture_paths)),
        ("materials", len(document.materials)),
        ("bones", len(document.bones)),
        ("morphs", len(document.morphs)),
        ("display_frames", len(document.display_frames)),
        ("rigid_bodies", len(document.rigid_bodies)),
        ("joints", len(document.joints)),
        ("soft_bodies", len(document.soft_bodies)),
        ("trailing_bytes", len(document.trailing_data)),
    )


def _appended_marker(value: str) -> str:
    """Return an exact reversible-in-temporary-output text edit."""

    separator = "\n" if value else ""
    return f"{value}{separator}{_VALIDATION_MARKER}"


def _changed_edge_scale(value: float) -> float:
    """Return one exactly representable safe material property value."""

    return 0.0 if value != 0.0 else 1.0


def _validate_only_intended_changes(
    source: PmxDocument,
    output: PmxDocument,
    *,
    material_index: int,
    expected_comments: str,
    expected_memo: str,
    expected_edge_scale: float,
) -> None:
    """Require exact edits and semantic equality everywhere else."""

    expected_model_info = replace(
        source.model_info,
        local_comments=expected_comments,
    )
    if output.model_info != expected_model_info:
        raise PmxPrivateValidationError(
            "private validation metadata edit did not match exactly."
        )

    expected_materials = list(source.materials)
    expected_materials[material_index] = replace(
        expected_materials[material_index],
        memo=expected_memo,
        edge_scale=expected_edge_scale,
    )
    if output.materials != tuple(expected_materials):
        raise PmxPrivateValidationError(
            "private validation material edits did not match exactly."
        )

    unchanged_fields = (
        "header",
        "geometry",
        "texture_paths",
        "bones",
        "morphs",
        "display_frames",
        "rigid_bodies",
        "joints",
        "soft_bodies",
        "trailing_data",
    )
    for field_name in unchanged_fields:
        if getattr(output, field_name) != getattr(source, field_name):
            raise PmxPrivateValidationError(
                f"private validation unexpectedly changed {field_name}."
            )

    if _section_counts(output) != _section_counts(source):
        raise PmxPrivateValidationError(
            "private validation changed one or more PMX section counts."
        )


def validate_private_pmx_edit(
    source_path: str | Path,
    *,
    material_index: int = 0,
) -> PmxPrivateValidationResult:
    """Validate real-model editing using only self-cleaning temporary files."""

    if not isinstance(material_index, int) or isinstance(material_index, bool):
        raise TypeError("material_index must be an integer.")
    if material_index < 0:
        raise ValueError("material_index cannot be negative.")

    source = Path(source_path)
    if not source.exists():
        raise PmxEditPathError(f"Private PMX file does not exist: {source.name}")
    if not source.is_file():
        raise PmxEditPathError(
            f"Private PMX path is not a file: {source.name}"
        )
    if source.suffix.lower() != ".pmx":
        raise PmxEditPathError("Private model must use the .pmx extension.")
    source = source.resolve(strict=True)

    source_bytes = source.read_bytes()
    source_sha256 = _sha256_bytes(source_bytes)
    source_size = len(source_bytes)
    source_document = load_pmx(source)
    validate_pmx_document(source_document)
    if material_index >= len(source_document.materials):
        raise PmxPrivateValidationError(
            f"material_index {material_index} is out of range for "
            f"{len(source_document.materials)} materials."
        )

    material = source_document.materials[material_index]
    expected_comments = _appended_marker(
        source_document.model_info.local_comments
    )
    expected_memo = _appended_marker(material.memo)
    expected_edge_scale = _changed_edge_scale(material.edge_scale)
    plan_payload = {
        "schema_version": 1,
        "expected_source_sha256": source_sha256,
        "operations": [
            {
                "op": "set_model_info",
                "local_comments": expected_comments,
            },
            {
                "op": "update_material",
                "material_index": material_index,
                "memo": expected_memo,
                "edge_scale": expected_edge_scale,
            },
        ],
    }

    output_sha256 = ""
    changed_fields = 0
    temporary_root: Path | None = None
    with tempfile.TemporaryDirectory(
        prefix=".mmd-registry-private-edit-",
        dir=source.parent,
    ) as temporary_directory:
        temporary_root = Path(temporary_directory)
        plan_path = temporary_root / "validation-plan.json"
        output_path = temporary_root / "validation-output.pmx"
        plan_path.write_text(
            json.dumps(
                plan_payload,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        plan = load_pmx_edit_plan(plan_path)
        intended = dry_run_pmx_edit(source_bytes, plan)
        write_result = write_pmx_edit(source, output_path, plan)

        output_document = load_pmx(output_path)
        validate_pmx_document(output_document)
        if output_document != intended.document:
            raise PmxPrivateValidationError(
                "temporary output differs from the intended edited document."
            )
        if output_document != write_result.preview.document:
            raise PmxPrivateValidationError(
                "temporary output differs from the verified write result."
            )
        _validate_only_intended_changes(
            source_document,
            output_document,
            material_index=material_index,
            expected_comments=expected_comments,
            expected_memo=expected_memo,
            expected_edge_scale=expected_edge_scale,
        )
        output_sha256 = write_result.output_sha256
        changed_fields = write_result.preview.audit.changed_fields

        if source.stat().st_size != source_size:
            raise PmxPrivateValidationError(
                "private source size changed during validation."
            )
        if _sha256_bytes(source.read_bytes()) != source_sha256:
            raise PmxPrivateValidationError(
                "private source SHA-256 changed during validation."
            )

    assert temporary_root is not None
    temporary_files_removed = not temporary_root.exists()
    if not temporary_files_removed:
        raise PmxPrivateValidationError(
            "private validation temporary files were not removed."
        )
    return PmxPrivateValidationResult(
        source_name=source.name,
        version=source_document.header.version,
        encoding=source_document.header.encoding,
        material_index=material_index,
        source_size_bytes=source_size,
        source_sha256=source_sha256,
        output_sha256=output_sha256,
        changed_fields=changed_fields,
        section_counts=_section_counts(source_document),
        temporary_files_removed=temporary_files_removed,
    )


def render_private_validation_text(result: PmxPrivateValidationResult) -> str:
    """Render a compact report safe to paste without a private path."""

    if not isinstance(result, PmxPrivateValidationResult):
        raise TypeError("result must be a PmxPrivateValidationResult instance.")
    lines = (
        "PMX PRIVATE EDIT VALIDATION",
        "Status: ok",
        f"Source name: {result.source_name}",
        f"Version: {result.version:.1f}",
        f"Encoding: {result.encoding}",
        f"Source size: {result.source_size_bytes}",
        f"Source SHA-256: {result.source_sha256}",
        f"Output SHA-256: {result.output_sha256}",
        f"Changed fields: {result.changed_fields}",
        "Metadata edit: passed",
        "Material text/property edit: passed",
        "Unrelated sections unchanged: yes",
        "Source unchanged: yes",
        "Temporary files removed: yes",
        "Private asset persisted: no",
    )
    return "\n".join(lines) + "\n"


def render_private_validation_json(
    result: PmxPrivateValidationResult,
) -> str:
    """Render stable privacy-safe JSON followed by a newline."""

    if not isinstance(result, PmxPrivateValidationResult):
        raise TypeError("result must be a PmxPrivateValidationResult instance.")
    return (
        json.dumps(
            result.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
        + "\n"
    )


def _configure_utf8_standard_streams() -> None:
    """Use UTF-8 for redirected private-validation reports on Windows."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            continue


def main(argv: Sequence[str] | None = None) -> int:
    """Run ephemeral private-model validation without retaining the model."""

    _configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(
        description=(
            "Validate safe PMX editing on one private model. The generated "
            "plan and output are temporary and removed automatically."
        )
    )
    parser.add_argument("source", help="Path to the private PMX model.")
    parser.add_argument(
        "--material-index",
        type=int,
        default=0,
        help="Material used for temporary text/property edits (default: 0).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a privacy-safe JSON report.",
    )
    arguments = parser.parse_args(argv)

    try:
        result = validate_private_pmx_edit(
            arguments.source,
            material_index=arguments.material_index,
        )
    except (
        BinaryParseError,
        PmxEditPlanError,
        PmxEditVerificationError,
        PmxPrivateValidationError,
        PmxValidationError,
    ) as error:
        message = str(error)
        exit_code = 1
    except (OSError, PmxEditPathError, TypeError, ValueError) as error:
        message = str(error)
        exit_code = 2
    except Exception as error:
        message = f"Unexpected private-validation failure: {error}"
        exit_code = 3
    else:
        if arguments.json:
            sys.stdout.write(render_private_validation_json(result))
        else:
            sys.stdout.write(render_private_validation_text(result))
        return 0

    if arguments.json:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "error",
                    "errors": [message],
                    "private_asset_persisted": False,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    else:
        print(f"[ERROR] private edit validation: {message}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
