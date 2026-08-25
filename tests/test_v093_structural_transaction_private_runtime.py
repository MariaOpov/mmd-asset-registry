"""Optional privacy-safe real-PMX validation for structural transactions."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from mmd_registry.diagnostics import PmxServiceError
from mmd_registry.pmx.reader import load_pmx
from mmd_registry.services import (
    PmxReferenceTargetKind,
    PmxStructuralCollectionEdit,
)
from mmd_registry.services.structural_transaction import (
    PmxStructuralTransactionRequest,
    apply_structural_transaction,
    preview_structural_transaction,
)


_PRIVATE_PMX_ENV = "MMD_REGISTRY_PRIVATE_PMX"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _transaction_request(document) -> PmxStructuralTransactionRequest:
    texture_count = len(document.texture_paths)
    order = tuple(range(texture_count))
    if texture_count > 1:
        order = (*order[1:], order[0])
    return PmxStructuralTransactionRequest(
        (
            PmxStructuralCollectionEdit(
                PmxReferenceTargetKind.TEXTURE,
                order,
            ),
        )
    )


def _invalid_request(document) -> PmxStructuralTransactionRequest:
    return PmxStructuralTransactionRequest(
        (
            PmxStructuralCollectionEdit(
                PmxReferenceTargetKind.TEXTURE,
                (len(document.texture_paths),),
            ),
        )
    )


class V093StructuralTransactionPrivateRuntimeTests(unittest.TestCase):
    """Validate the complete transaction pipeline without retaining private data."""

    @classmethod
    def setUpClass(cls) -> None:
        raw_path = os.environ.get(_PRIVATE_PMX_ENV)
        if not raw_path:
            raise unittest.SkipTest(
                f"set {_PRIVATE_PMX_ENV} to enable private-model validation"
            )

        candidate = Path(raw_path).expanduser()
        if not candidate.exists():
            raise AssertionError("private PMX runtime path does not exist")
        if not candidate.is_file():
            raise AssertionError("private PMX runtime path is not a file")
        if candidate.suffix.lower() != ".pmx":
            raise AssertionError("private PMX runtime path must use .pmx")
        cls.source_path = candidate.resolve(strict=True)

    def setUp(self) -> None:
        self.source_size = self.source_path.stat().st_size
        self.source_sha256 = _sha256_file(self.source_path)
        self.document = load_pmx(self.source_path)
        self.request = _transaction_request(self.document)

    def _assert_source_unchanged(self) -> None:
        if self.source_path.stat().st_size != self.source_size:
            self.fail("private source size changed during CP26 validation")
        if _sha256_file(self.source_path) != self.source_sha256:
            self.fail("private source content changed during CP26 validation")
        if load_pmx(self.source_path) != self.document:
            self.fail("private source semantics changed during CP26 validation")

    def _assert_private_identity_absent(self, text: str) -> None:
        normalized = text.casefold()
        candidates = {
            str(self.source_path).casefold(),
            self.source_path.as_posix().casefold(),
            self.source_path.name.casefold(),
        }
        if any(candidate and candidate in normalized for candidate in candidates):
            self.fail("public transaction evidence exposed private source identity")

    @staticmethod
    def _temporary_outputs(destination: Path) -> tuple[Path, ...]:
        return tuple(destination.parent.glob(f".{destination.name}.*.tmp"))

    def test_private_preview_is_deterministic_and_read_only(self) -> None:
        first = preview_structural_transaction(self.document, self.request)
        second = preview_structural_transaction(self.document, self.request)

        if first.to_dict() != second.to_dict():
            self.fail("private transaction preview evidence was not deterministic")
        if first.document != second.document:
            self.fail("private transaction preview documents differed")
        if first.plan_sha256 != second.plan_sha256:
            self.fail("private transaction plan digest was not deterministic")

        evidence = json.dumps(
            first.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        )
        self._assert_private_identity_absent(evidence)
        self._assert_source_unchanged()

    def test_private_execution_is_ephemeral_reparsed_and_repeatable(self) -> None:
        preview_before = preview_structural_transaction(
            self.document,
            self.request,
        )
        temporary_root: Path | None = None

        with tempfile.TemporaryDirectory(
            prefix=".mmd-registry-cp26-private-transaction-",
            dir=self.source_path.parent,
        ) as directory:
            temporary_root = Path(directory)
            first_output = temporary_root / "transaction-first.pmx"
            second_output = temporary_root / "transaction-second.pmx"

            first = apply_structural_transaction(
                self.source_path,
                first_output,
                self.request,
            )
            second = apply_structural_transaction(
                self.source_path,
                second_output,
                self.request,
            )

            if first.status not in {"written", "no_changes"}:
                self.fail("private transaction returned an unexpected status")
            if second.status != first.status:
                self.fail("repeated private transaction status changed")
            if not first_output.is_file() or not second_output.is_file():
                self.fail("private transaction did not publish temporary output")
            if first_output.read_bytes() != second_output.read_bytes():
                self.fail("repeated private transaction bytes were not deterministic")
            if first.document != preview_before.document:
                self.fail("private execution diverged from preview semantics")
            if second.document != preview_before.document:
                self.fail("repeated private execution diverged from preview")
            if load_pmx(first_output) != preview_before.document:
                self.fail("private transaction output failed independent reparse")
            if load_pmx(second_output) != preview_before.document:
                self.fail("repeated private output failed independent reparse")
            if first.source_sha256 != self.source_sha256:
                self.fail("private execution source binding was not exact")
            if second.source_sha256 != self.source_sha256:
                self.fail("repeated private source binding was not exact")
            if first.output_sha256 != second.output_sha256:
                self.fail("private output digest was not deterministic")
            if self._temporary_outputs(first_output):
                self.fail("private transaction left a temporary first-output file")
            if self._temporary_outputs(second_output):
                self.fail("private transaction left a temporary second-output file")

            preview_after = preview_structural_transaction(
                self.document,
                self.request,
            )
            if preview_before.to_dict() != preview_after.to_dict():
                self.fail("private execution changed later preview evidence")
            self._assert_source_unchanged()

        if temporary_root is None or temporary_root.exists():
            self.fail("private transaction validation directory was not removed")
        self._assert_source_unchanged()

    def test_private_failure_is_bounded_and_leaves_no_output(self) -> None:
        request = _invalid_request(self.document)
        temporary_root: Path | None = None

        with self.assertRaises(PmxServiceError) as preview_failure:
            preview_structural_transaction(self.document, request)
        preview_diagnostic = preview_failure.exception.to_dict()
        self._assert_private_identity_absent(
            json.dumps(
                preview_diagnostic,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
            )
        )

        with tempfile.TemporaryDirectory(
            prefix=".mmd-registry-cp26-private-failure-",
            dir=self.source_path.parent,
        ) as directory:
            temporary_root = Path(directory)
            destination = temporary_root / "blocked-output.pmx"
            with self.assertRaises(PmxServiceError) as execution_failure:
                apply_structural_transaction(
                    self.source_path,
                    destination,
                    request,
                )

            diagnostic = execution_failure.exception.to_dict()
            details = diagnostic.get("details")
            if not isinstance(details, dict):
                self.fail("private failure diagnostic omitted bounded details")
            if details.get("source_modified") is not False:
                self.fail("private failure did not certify source immutability")
            if details.get("destination_published") is not False:
                self.fail("private failure reported destination publication")
            if destination.exists():
                self.fail("private failure published an output")
            if self._temporary_outputs(destination):
                self.fail("private failure left temporary output residue")
            self._assert_private_identity_absent(
                json.dumps(
                    diagnostic,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                )
            )
            self._assert_source_unchanged()

        if temporary_root is None or temporary_root.exists():
            self.fail("private failure validation directory was not removed")
        self._assert_source_unchanged()


if __name__ == "__main__":
    unittest.main()
