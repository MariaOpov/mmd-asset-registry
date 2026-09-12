"""CP10 determinism, hashseed, and adversarial Smart Inspect output tests."""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import mmd_registry.cli as cli
import mmd_registry.smart_cli as smart_cli
from mmd_registry.services import _smart_inspection as smart_inspection
from mmd_registry.services.structural_authoring_catalog import (
    PmxStructuralAuthoringBoneCatalogEntry,
    PmxStructuralAuthoringMaterialCatalogEntry,
)
from tests.mmd_fixtures import (
    build_pmx_bone,
    build_pmx_material,
    build_pmx_structure,
)


_HASHSEEDS = ("0", "1", "2", "42", "31337")


class SmartCliDeterminismTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.model_path = self.root / "determinism 日本語 model.pmx"
        self.model_path.write_bytes(
            build_pmx_structure(
                deform_types=(),
                surface_indices=(),
                materials=(
                    build_pmx_material(
                        local_name="Face",
                        universal_name="Hair",
                        surface_index_count=0,
                    ),
                    build_pmx_material(
                        local_name="瞳",
                        universal_name="Eyes",
                        surface_index_count=0,
                    ),
                ),
                bones=(
                    build_pmx_bone(
                        local_name="左目",
                        universal_name="right eye",
                    ),
                ),
            )
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    @staticmethod
    def material(
        source_index: int,
        local_name: str,
        universal_name: str = "",
    ) -> PmxStructuralAuthoringMaterialCatalogEntry:
        return PmxStructuralAuthoringMaterialCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            texture_index=-1,
            sphere_texture_index=-1,
            surface_index_count=0,
        )

    @staticmethod
    def bone(
        source_index: int,
        local_name: str,
        universal_name: str = "",
    ) -> PmxStructuralAuthoringBoneCatalogEntry:
        return PmxStructuralAuthoringBoneCatalogEntry(
            source_index=source_index,
            local_name=local_name,
            universal_name=universal_name,
            parent_bone_index=-1,
            position=(0.0, 0.0, 0.0),
            flag_names=(),
        )

    def capture_run(self) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = cli.run(["smart", "inspect", str(self.model_path)])
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_repeat_runs_have_one_canonical_signature(self) -> None:
        outputs = []
        for _ in range(5):
            exit_code, stdout, stderr = self.capture_run()
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            outputs.append(stdout)

        signatures = {
            hashlib.sha256(output.encode("utf-8")).hexdigest()
            for output in outputs
        }
        self.assertEqual(len(signatures), 1)

    def test_reversed_equivalent_injected_entry_order_is_identical(self) -> None:
        entries = (
            self.material(0, "Face", "Hair"),
            self.material(1, "瞳", "Eyes"),
            self.bone(0, "左目", "right eye"),
        )

        forward = smart_inspection._analyze_entries(entries)
        reverse = smart_inspection._analyze_entries(tuple(reversed(entries)))

        self.assertEqual(
            smart_cli._render_basic_text(forward),
            smart_cli._render_basic_text(reverse),
        )

    def test_adversarial_output_preserves_resolved_and_ambiguous_sections(self) -> None:
        exit_code, stdout, stderr = self.capture_run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Eyes", stdout)
        self.assertIn("HIGH", stdout)
        self.assertIn("Hair / Face", stdout)
        self.assertIn("AMBIGUOUS", stdout)
        self.assertIn("Candidates:", stdout)
        self.assertIn("Evidence:", stdout)
        self.assertIn("瞳", stdout)

    def test_hashseed_matrix_has_one_canonical_signature(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        signatures: set[str] = set()

        for seed in _HASHSEEDS:
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mmd_registry.cli",
                    "smart",
                    "inspect",
                    str(self.model_path),
                ],
                cwd=project_root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"seed={seed} stderr={completed.stderr!r}",
            )
            self.assertEqual(completed.stderr, b"")
            decoded = completed.stdout.decode("utf-8")
            self.assertIn("Hair / Face", decoded)
            self.assertIn("Eyes", decoded)
            signatures.add(hashlib.sha256(completed.stdout).hexdigest())

        self.assertEqual(len(signatures), 1)


if __name__ == "__main__":
    unittest.main()
