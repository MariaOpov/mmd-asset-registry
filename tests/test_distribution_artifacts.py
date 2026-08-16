"""Tests for fail-closed wheel and sdist artifact inspection."""

from __future__ import annotations

import csv
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.inspect_distribution_artifacts import (
    DistributionInspectionError,
    ProjectIdentity,
    inspect_distribution_directory,
)


IDENTITY = ProjectIdentity(
    name="mmd-asset-registry",
    version="0.9.0",
    requires_python=">=3.12",
    dependencies=("PyYAML>=6.0",),
    console_scripts=(("mmd-asset-registry", "mmd_registry.cli:main"),),
)
NORMALIZED_NAME = "mmd_asset_registry"
DIST_INFO = f"{NORMALIZED_NAME}-{IDENTITY.version}.dist-info"
SDIST_ROOT = f"{NORMALIZED_NAME}-{IDENTITY.version}"


def package_metadata(*, version: str = IDENTITY.version) -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        f"Name: {IDENTITY.name}\n"
        f"Version: {version}\n"
        f"Requires-Python: {IDENTITY.requires_python}\n"
        "Requires-Dist: PyYAML>=6.0\n"
        "\n"
    ).encode("utf-8")


def default_wheel_files() -> dict[str, bytes]:
    return {
        "mmd_registry/__init__.py": b'__version__ = "0.9.0"\n',
        "mmd_registry/diagnostics.py": b"__all__ = ()\n",
        "mmd_registry/pmx/__init__.py": b"__all__ = ()\n",
        "mmd_registry/services/__init__.py": b"__all__ = ()\n",
        f"{DIST_INFO}/METADATA": package_metadata(),
        f"{DIST_INFO}/entry_points.txt": (
            b"[console_scripts]\n"
            b"mmd-asset-registry = mmd_registry.cli:main\n"
        ),
        f"{DIST_INFO}/WHEEL": (
            b"Wheel-Version: 1.0\n"
            b"Root-Is-Purelib: true\n"
            b"Tag: py3-none-any\n\n"
        ),
        f"{DIST_INFO}/top_level.txt": b"mmd_registry\n",
    }


def write_wheel(
    directory: Path,
    *,
    additions: dict[str, bytes] | None = None,
    replacements: dict[str, bytes] | None = None,
) -> Path:
    files = default_wheel_files()
    files.update(additions or {})
    files.update(replacements or {})
    record_name = f"{DIST_INFO}/RECORD"
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    for name in (*files, record_name):
        writer.writerow((name, "", ""))
    files[record_name] = output.getvalue().encode("utf-8")

    path = directory / f"{NORMALIZED_NAME}-{IDENTITY.version}-py3-none-any.whl"
    with zipfile.ZipFile(path, mode="w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


def default_sdist_files() -> dict[str, bytes]:
    return {
        "MANIFEST.in": b"recursive-include tests *.py\n",
        "PKG-INFO": package_metadata(),
        "README.md": b"# Test package\n",
        "mmd_registry/__init__.py": b'__version__ = "0.9.0"\n',
        "mmd_registry/diagnostics.py": b"__all__ = ()\n",
        "mmd_registry/pmx/__init__.py": b"__all__ = ()\n",
        "mmd_registry/services/__init__.py": b"__all__ = ()\n",
        "pyproject.toml": b"[build-system]\n",
        "requirements-dev.txt": (
            b"ruff==0.16.3\ncoverage==7.15.4\nbuild==1.5.0\n"
        ),
        "setup.cfg": b"[egg_info]\n",
        "tests/__init__.py": b"",
        "tests/mmd_fixtures.py": b"# fixtures\n",
        "tests/test_clean_install.py": b"# clean install tests\n",
        "tests/test_console_entry_point.py": b"# console tests\n",
        "tests/test_distribution_artifacts.py": b"# tests\n",
        "tests/test_coverage_foundation.py": b"# coverage tests\n",
        "tests/test_cross_platform_build_install_gate.py": (
            b"# cross-platform tests\n"
        ),
        "tests/test_lint_foundation.py": b"# lint tests\n",
        "tests/test_public_capability_api.py": b"# public capability tests\n",
        "tests/test_public_diagnostics_api.py": b"# public diagnostic tests\n",
        "tests/test_stable_document_service.py": b"# document service tests\n",
        "tests/test_stable_validation_service.py": b"# validation service tests\n",
        "tests/test_stable_edit_service.py": b"# edit service tests\n",
        "tools/inspect_distribution_artifacts.py": b"# inspector\n",
        "tools/verify_clean_install.py": b"# clean install verifier\n",
        f"{NORMALIZED_NAME}.egg-info/PKG-INFO": package_metadata(),
    }


def write_sdist(
    directory: Path,
    *,
    additions: dict[str, bytes] | None = None,
    replacements: dict[str, bytes] | None = None,
    link_name: str | None = None,
) -> Path:
    files = default_sdist_files()
    files.update(additions or {})
    files.update(replacements or {})
    path = directory / f"{NORMALIZED_NAME}-{IDENTITY.version}.tar.gz"
    with tarfile.open(path, mode="w:gz") as archive:
        for relative_name, data in files.items():
            info = tarfile.TarInfo(f"{SDIST_ROOT}/{relative_name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if link_name is not None:
            info = tarfile.TarInfo(f"{SDIST_ROOT}/{link_name}")
            info.type = tarfile.SYMTYPE
            info.linkname = "README.md"
            archive.addfile(info)
    return path


class DistributionArtifactTests(unittest.TestCase):
    """Exercise the archive gate without invoking a build frontend."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_valid_pair(self) -> None:
        write_wheel(self.directory)
        write_sdist(self.directory)

    def assert_rejected(self, message: str) -> None:
        with self.assertRaisesRegex(DistributionInspectionError, message):
            inspect_distribution_directory(self.directory, IDENTITY)

    def test_valid_wheel_and_sdist_pass_as_one_pair(self) -> None:
        self.write_valid_pair()

        wheel, sdist = inspect_distribution_directory(self.directory, IDENTITY)

        self.assertEqual(wheel.kind, "wheel")
        self.assertEqual(sdist.kind, "sdist")
        self.assertRegex(wheel.sha256, r"^[0-9a-f]{64}$")
        self.assertRegex(sdist.sha256, r"^[0-9a-f]{64}$")

    def test_directory_must_contain_exactly_two_artifacts(self) -> None:
        self.write_valid_pair()
        (self.directory / "notes.txt").write_text("unexpected", encoding="utf-8")

        self.assert_rejected("exactly one .whl and one .tar.gz")

    def test_wheel_rejects_non_runtime_paths(self) -> None:
        write_wheel(
            self.directory,
            additions={"tests/test_leak.py": b"# leaked test\n"},
        )
        write_sdist(self.directory)

        self.assert_rejected("non-runtime path")

    def test_archive_rejects_private_pmx_and_secret_files(self) -> None:
        write_wheel(self.directory)
        write_sdist(
            self.directory,
            additions={"tests/private-model.pmx": b"PMX ", ".env": b"TOKEN=x\n"},
        )

        self.assert_rejected("forbidden file")

    def test_sdist_rejects_links(self) -> None:
        write_wheel(self.directory)
        write_sdist(self.directory, link_name="README-link.md")

        self.assert_rejected("link or special member")

    def test_sdist_rejects_unintended_repository_paths(self) -> None:
        write_wheel(self.directory)
        write_sdist(
            self.directory,
            additions={"CHANGELOG.md": b"private release notes\n"},
        )

        self.assert_rejected("unintended repository path")

    def test_metadata_must_match_the_project_identity(self) -> None:
        write_wheel(
            self.directory,
            replacements={f"{DIST_INFO}/METADATA": package_metadata(version="9.9.9")},
        )
        write_sdist(self.directory)

        self.assert_rejected("metadata Version='9.9.9'")

    def test_console_script_must_match_the_project_identity(self) -> None:
        write_wheel(
            self.directory,
            replacements={
                f"{DIST_INFO}/entry_points.txt": (
                    b"[console_scripts]\n"
                    b"mmd-asset-registry = mmd_registry.cli:run\n"
                )
            },
        )
        write_sdist(self.directory)

        self.assert_rejected("Wheel console scripts")

    def test_private_local_path_content_is_rejected(self) -> None:
        self.write_valid_pair()
        secret_path = r"C:\Users\Alice\private\model.pmx"
        wheel_path = next(self.directory.glob("*.whl"))
        wheel_path.unlink()
        write_wheel(
            self.directory,
            replacements={
                "mmd_registry/__init__.py": secret_path.encode("utf-8")
            },
        )

        with self.assertRaisesRegex(
            DistributionInspectionError, "private local path"
        ):
            inspect_distribution_directory(
                self.directory,
                IDENTITY,
                private_values=(secret_path,),
            )


if __name__ == "__main__":
    unittest.main()
