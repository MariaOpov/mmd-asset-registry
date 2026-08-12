"""Privacy-safe negative-path validation for one real PMX model."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from mmd_registry.binary_reader import BinaryParseError
from mmd_registry.pmx import load_pmx, validate_pmx_document
from mmd_registry.pmx.editing.diagnostics import (
    PmxEditPhase,
    diagnostic_from_plan_error,
)
from mmd_registry.pmx.editing.errors import (
    PmxEditPathError,
    PmxEditPlanError,
    PmxEditVerificationError,
)
from mmd_registry.pmx.editing.json_loader import parse_pmx_edit_plan_json
from mmd_registry.pmx.editing.output import write_pmx_edit
from mmd_registry.pmx.editing.preview import dry_run_pmx_edit
from mmd_registry.pmx.errors import PmxValidationError


_VALIDATION_MARKER = "[mmd-asset-registry private failure validation]"


class PmxPrivateFailureValidationError(RuntimeError):
    """Raised when a private-model negative-path invariant is not satisfied."""


@dataclass(frozen=True, slots=True)
class PmxPrivateFailureScenario:
    """One privacy-safe negative-path validation outcome."""

    name: str
    status: str
    code: str | None = None
    phase: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "status": self.status,
        }
        if self.code is not None:
            payload["code"] = self.code
        if self.phase is not None:
            payload["phase"] = self.phase
        return payload


@dataclass(frozen=True, slots=True)
class PmxPrivateFailureValidationResult:
    """Technical metadata from ephemeral real-model failure validation."""

    source_name: str
    version: float
    encoding: str
    source_size_bytes: int
    source_sha256_before: str
    source_sha256_after: str
    scenarios: tuple[PmxPrivateFailureScenario, ...]
    temporary_residue_created: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "ok",
            "source": {
                "name": self.source_name,
                "version": self.version,
                "encoding": self.encoding,
                "size_bytes": self.source_size_bytes,
                "sha256_before": self.source_sha256_before,
                "sha256_after": self.source_sha256_after,
            },
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
            "invariants": {
                "source_unchanged": (
                    self.source_sha256_before == self.source_sha256_after
                ),
                "temporary_residue_created": self.temporary_residue_created,
                "private_asset_persisted": False,
            },
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _temporary_artifact_names(parent: Path) -> frozenset[str]:
    names: set[str] = set()
    for path in parent.iterdir():
        name = path.name
        if name.startswith(".mmd-registry-private-edit-"):
            names.add(name)
            continue
        if name.startswith(".") and name.endswith(".tmp"):
            names.add(name)
    return frozenset(names)


def _build_valid_plan(source_sha256: str, comments: str):
    payload = {
        "schema_version": 1,
        "expected_source_sha256": source_sha256,
        "operations": [
            {
                "op": "set_model_info",
                "local_comments": comments,
            }
        ],
    }
    return parse_pmx_edit_plan_json(
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
    )


def validate_private_pmx_edit_failures(
    source_path: str | Path,
) -> PmxPrivateFailureValidationResult:
    """Exercise expected edit failures without persisting an edited private PMX."""

    source = Path(source_path)
    if not source.exists():
        raise PmxEditPathError(
            f"Private PMX file does not exist: {source.name}"
        )
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
    source_document = load_pmx(io.BytesIO(source_bytes))
    validate_pmx_document(source_document)

    before_artifacts = _temporary_artifact_names(source.parent)
    comments = (
        source_document.model_info.local_comments
        + ("\n" if source_document.model_info.local_comments else "")
        + _VALIDATION_MARKER
    )
    valid_plan = _build_valid_plan(source_sha256, comments)
    scenarios: list[PmxPrivateFailureScenario] = []

    dry_run_pmx_edit(source_bytes, valid_plan)
    scenarios.append(
        PmxPrivateFailureScenario(
            name="valid_dry_run",
            status="passed",
        )
    )

    invalid_payload = json.dumps(
        {
            "schema_version": 1,
            "operations": [{"op": "rename_model"}],
        }
    )
    try:
        parse_pmx_edit_plan_json(invalid_payload)
    except PmxEditPlanError as error:
        diagnostic = diagnostic_from_plan_error(
            error,
            phase=PmxEditPhase.PLAN_VALIDATE,
        )
        scenarios.append(
            PmxPrivateFailureScenario(
                name="plan_validation_failure",
                status="passed",
                code=diagnostic.code.value,
                phase=diagnostic.phase.value,
            )
        )
    else:
        raise PmxPrivateFailureValidationError(
            "invalid private validation plan was unexpectedly accepted."
        )

    mismatch_plan = _build_valid_plan("0" * 64, comments)
    try:
        dry_run_pmx_edit(source_bytes, mismatch_plan)
    except PmxEditPlanError as error:
        diagnostic = diagnostic_from_plan_error(
            error,
            phase=PmxEditPhase.PREFLIGHT,
        )
        scenarios.append(
            PmxPrivateFailureScenario(
                name="source_hash_mismatch",
                status="passed",
                code=diagnostic.code.value,
                phase=diagnostic.phase.value,
            )
        )
    else:
        raise PmxPrivateFailureValidationError(
            "source-hash mismatch was unexpectedly accepted."
        )

    try:
        write_pmx_edit(
            source,
            source,
            valid_plan,
            overwrite=True,
        )
    except PmxEditPathError:
        scenarios.append(
            PmxPrivateFailureScenario(
                name="input_output_alias_refusal",
                status="passed",
                code="path_policy_refused",
                phase=PmxEditPhase.PREFLIGHT.value,
            )
        )
    else:
        raise PmxPrivateFailureValidationError(
            "input/output alias was unexpectedly accepted."
        )

    source_after = source.read_bytes()
    source_sha256_after = _sha256_bytes(source_after)
    if len(source_after) != source_size:
        raise PmxPrivateFailureValidationError(
            "private source size changed during failure validation."
        )
    if source_sha256_after != source_sha256:
        raise PmxPrivateFailureValidationError(
            "private source SHA-256 changed during failure validation."
        )

    after_artifacts = _temporary_artifact_names(source.parent)
    residue_created = bool(after_artifacts - before_artifacts)
    if residue_created:
        raise PmxPrivateFailureValidationError(
            "private failure validation created temporary residue."
        )
    scenarios.append(
        PmxPrivateFailureScenario(
            name="temporary_residue",
            status="passed",
        )
    )

    return PmxPrivateFailureValidationResult(
        source_name=source.name,
        version=source_document.header.version,
        encoding=source_document.header.encoding,
        source_size_bytes=source_size,
        source_sha256_before=source_sha256,
        source_sha256_after=source_sha256_after,
        scenarios=tuple(scenarios),
        temporary_residue_created=False,
    )


def render_private_failure_validation_text(
    result: PmxPrivateFailureValidationResult,
) -> str:
    if not isinstance(result, PmxPrivateFailureValidationResult):
        raise TypeError(
            "result must be a PmxPrivateFailureValidationResult instance."
        )
    lines = [
        "PMX PRIVATE FAILURE VALIDATION",
        "Status: ok",
        f"Source name: {result.source_name}",
        f"Version: {result.version:.1f}",
        f"Encoding: {result.encoding}",
        f"Source size: {result.source_size_bytes}",
        f"Source SHA-256 before: {result.source_sha256_before}",
        f"Source SHA-256 after: {result.source_sha256_after}",
    ]
    for scenario in result.scenarios:
        suffix = ""
        if scenario.code is not None:
            suffix += f" | code={scenario.code}"
        if scenario.phase is not None:
            suffix += f" | phase={scenario.phase}"
        lines.append(f"{scenario.name}: {scenario.status}{suffix}")
    lines.extend(
        (
            "Source unchanged: yes",
            "Temporary residue created: no",
            "Private asset persisted: no",
        )
    )
    return "\n".join(lines) + "\n"


def render_private_failure_validation_json(
    result: PmxPrivateFailureValidationResult,
) -> str:
    if not isinstance(result, PmxPrivateFailureValidationResult):
        raise TypeError(
            "result must be a PmxPrivateFailureValidationResult instance."
        )
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
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            continue


def main(argv: Sequence[str] | None = None) -> int:
    """Run privacy-safe real-model failure validation."""

    _configure_utf8_standard_streams()
    parser = argparse.ArgumentParser(
        description=(
            "Exercise expected PMX edit failures on one private model without "
            "persisting any edited private output."
        )
    )
    parser.add_argument("source", help="Path to the private PMX model.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a privacy-safe JSON result.",
    )
    arguments = parser.parse_args(argv)

    try:
        result = validate_private_pmx_edit_failures(arguments.source)
    except (
        BinaryParseError,
        PmxEditPlanError,
        PmxEditVerificationError,
        PmxPrivateFailureValidationError,
        PmxValidationError,
    ):
        message = "Private failure validation did not satisfy an invariant."
        exit_code = 1
    except (OSError, PmxEditPathError, TypeError, ValueError):
        message = "Private failure validation could not read or validate the source."
        exit_code = 2
    except Exception:
        message = "Unexpected private failure-validation error."
        exit_code = 3
    else:
        if arguments.json:
            sys.stdout.write(render_private_failure_validation_json(result))
        else:
            sys.stdout.write(render_private_failure_validation_text(result))
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
                allow_nan=False,
                indent=2,
            )
            + "\n"
        )
    else:
        print(f"[ERROR] private failure validation: {message}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
