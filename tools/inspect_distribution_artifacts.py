"""Inspect wheel and sdist artifacts without extracting or installing them."""

from __future__ import annotations

import argparse
import ast
import configparser
import csv
import hashlib
import io
import os
import re
import stat
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from email.message import Message
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import Iterable


FORBIDDEN_COMPONENTS = frozenset(
    {
        ".git",
        ".github",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "reports",
        "sample_assets",
        "venv",
    }
)
FORBIDDEN_SUFFIXES = frozenset(
    {
        ".bak",
        ".key",
        ".orig",
        ".p12",
        ".pem",
        ".pfx",
        ".pmd",
        ".pmx",
        ".rej",
        ".swp",
        ".tmp",
        ".vmd",
        ".vpd",
    }
)
TEXT_SUFFIXES = frozenset(
    {".cfg", ".csv", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"}
)
SECRET_MARKERS = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN RSA " + b"PRIVATE KEY-----",
    b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
)


class DistributionInspectionError(RuntimeError):
    """Raised when a built distribution violates the artifact contract."""


@dataclass(frozen=True, slots=True)
class ArtifactInspection:
    """Summary of one successfully inspected distribution artifact."""

    kind: str
    path: Path
    member_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class ProjectIdentity:
    """Expected distribution identity loaded from repository metadata."""

    name: str
    version: str
    requires_python: str
    dependencies: tuple[str, ...]
    console_scripts: tuple[tuple[str, str], ...] = ()


def load_project_identity(project_root: Path) -> ProjectIdentity:
    """Load expected artifact metadata without importing project code."""

    root = project_root.resolve()
    pyproject = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = pyproject["project"]
    version_attribute = pyproject["tool"]["setuptools"]["dynamic"]["version"][
        "attr"
    ]
    module_name, attribute_name = version_attribute.rsplit(".", 1)
    module_path = root.joinpath(*module_name.split(".")).with_suffix(".py")
    if not module_path.is_file():
        module_path = root.joinpath(*module_name.split("."), "__init__.py")
    version = _read_literal_assignment(module_path, attribute_name)
    return ProjectIdentity(
        name=project["name"],
        version=version,
        requires_python=project["requires-python"],
        dependencies=tuple(project.get("dependencies", ())),
        console_scripts=tuple(sorted(project.get("scripts", {}).items())),
    )


def inspect_distribution_directory(
    directory: Path,
    identity: ProjectIdentity,
    *,
    project_root: Path | None = None,
    private_values: Iterable[str] = (),
) -> tuple[ArtifactInspection, ArtifactInspection]:
    """Inspect exactly one wheel and one sdist in a clean directory."""

    artifact_directory = directory.resolve()
    if not artifact_directory.is_dir():
        raise DistributionInspectionError(
            f"Distribution directory does not exist: {artifact_directory}"
        )

    entries = sorted(artifact_directory.iterdir(), key=lambda path: path.name)
    if any(not entry.is_file() or entry.is_symlink() for entry in entries):
        raise DistributionInspectionError(
            "Distribution directory may contain only two regular artifact files."
        )
    wheels = [entry for entry in entries if entry.name.endswith(".whl")]
    sdists = [entry for entry in entries if entry.name.endswith(".tar.gz")]
    unexpected = [
        entry.name
        for entry in entries
        if entry not in wheels and entry not in sdists
    ]
    if len(wheels) != 1 or len(sdists) != 1 or unexpected:
        raise DistributionInspectionError(
            "Expected exactly one .whl and one .tar.gz artifact; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}, "
            f"unexpected={unexpected!r}."
        )

    sensitive_values = set(value for value in private_values if value)
    if project_root is not None:
        sensitive_values.add(str(project_root.resolve()))
    for variable_name in ("HOME", "USERPROFILE", "MMD_REGISTRY_PRIVATE_PMX"):
        value = os.environ.get(variable_name)
        if value and len(value) >= 6:
            sensitive_values.add(value)

    wheel_report = inspect_wheel(
        wheels[0], identity, private_values=sensitive_values
    )
    sdist_report = inspect_sdist(
        sdists[0], identity, private_values=sensitive_values
    )
    return wheel_report, sdist_report


def inspect_wheel(
    path: Path,
    identity: ProjectIdentity,
    *,
    private_values: Iterable[str] = (),
) -> ArtifactInspection:
    """Validate the wheel boundary, metadata, records, and archive safety."""

    normalized_name = _normalized_name(identity.name)
    expected_filename = f"{normalized_name}-{identity.version}-py3-none-any.whl"
    if path.name != expected_filename:
        raise DistributionInspectionError(
            f"Unexpected wheel filename: {path.name}; expected {expected_filename}."
        )

    expected_dist_info = f"{normalized_name}-{identity.version}.dist-info"
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            _validate_member_names(names)
            for info in infos:
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise DistributionInspectionError(
                        f"Wheel contains a symbolic link: {info.filename}"
                    )
                _validate_forbidden_path(info.filename)

            file_names = {
                info.filename for info in infos if not info.is_dir()
            }
            for name in file_names:
                first = PurePosixPath(name).parts[0]
                if first not in {"mmd_registry", expected_dist_info}:
                    raise DistributionInspectionError(
                        f"Wheel contains a non-runtime path: {name}"
                    )
                if first == "mmd_registry" and not name.endswith(".py"):
                    raise DistributionInspectionError(
                        f"Wheel contains unexpected package data: {name}"
                    )

            required = {
                "mmd_registry/__init__.py",
                "mmd_registry/pmx/__init__.py",
                "mmd_registry/services/__init__.py",
                f"{expected_dist_info}/METADATA",
                f"{expected_dist_info}/RECORD",
                f"{expected_dist_info}/WHEEL",
                f"{expected_dist_info}/top_level.txt",
            }
            entry_points_name = f"{expected_dist_info}/entry_points.txt"
            if identity.console_scripts:
                required.add(entry_points_name)
            _require_members(file_names, required, "wheel")
            if not identity.console_scripts and entry_points_name in file_names:
                raise DistributionInspectionError(
                    "Wheel contains console entry points not declared by the project."
                )

            metadata = _parse_metadata(
                archive.read(f"{expected_dist_info}/METADATA")
            )
            _validate_metadata(metadata, identity)
            if identity.console_scripts:
                _validate_entry_points(
                    archive.read(entry_points_name), identity.console_scripts
                )
            wheel_metadata = _parse_metadata(
                archive.read(f"{expected_dist_info}/WHEEL")
            )
            if wheel_metadata.get("Root-Is-Purelib") != "true":
                raise DistributionInspectionError("Wheel is not pure-Python.")
            if wheel_metadata.get_all("Tag", failobj=[]) != ["py3-none-any"]:
                raise DistributionInspectionError(
                    "Wheel compatibility tag must be py3-none-any."
                )
            if archive.read(f"{expected_dist_info}/top_level.txt") != b"mmd_registry\n":
                raise DistributionInspectionError(
                    "Wheel top_level.txt does not identify mmd_registry."
                )
            _validate_record(
                archive.read(f"{expected_dist_info}/RECORD"), file_names
            )
            _scan_archive_text(
                ((name, archive.read(name)) for name in file_names),
                private_values,
            )
    except (OSError, zipfile.BadZipFile) as error:
        raise DistributionInspectionError(
            f"Cannot read wheel {path.name}: {error}"
        ) from error

    return ArtifactInspection(
        kind="wheel",
        path=path,
        member_count=len(file_names),
        sha256=_sha256_file(path),
    )


def inspect_sdist(
    path: Path,
    identity: ProjectIdentity,
    *,
    private_values: Iterable[str] = (),
) -> ArtifactInspection:
    """Validate the source archive boundary, metadata, and member safety."""

    normalized_name = _normalized_name(identity.name)
    expected_filename = f"{normalized_name}-{identity.version}.tar.gz"
    expected_root = f"{normalized_name}-{identity.version}"
    if path.name != expected_filename:
        raise DistributionInspectionError(
            f"Unexpected sdist filename: {path.name}; expected {expected_filename}."
        )

    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            _validate_member_names(names)
            for member in members:
                if not (member.isdir() or member.isfile()):
                    raise DistributionInspectionError(
                        f"sdist contains a link or special member: {member.name}"
                    )
                _validate_forbidden_path(member.name)
                if PurePosixPath(member.name).parts[0] != expected_root:
                    raise DistributionInspectionError(
                        f"sdist member escapes its expected root: {member.name}"
                    )

            file_members = {member.name: member for member in members if member.isfile()}
            relative_names = {
                "/".join(PurePosixPath(name).parts[1:])
                for name in file_members
            }
            required = {
                "MANIFEST.in",
                "PKG-INFO",
                "README.md",
                "mmd_registry/__init__.py",
                "mmd_registry/pmx/__init__.py",
                "mmd_registry/services/__init__.py",
                "pyproject.toml",
                "tests/__init__.py",
                "tests/mmd_fixtures.py",
                "tests/test_console_entry_point.py",
                "tests/test_distribution_artifacts.py",
                "tools/inspect_distribution_artifacts.py",
            }
            _require_members(relative_names, required, "sdist")
            allowed_roots = {
                "MANIFEST.in",
                "PKG-INFO",
                "README.md",
                f"{normalized_name}.egg-info",
                "mmd_registry",
                "pyproject.toml",
                "setup.cfg",
                "tests",
                "tools",
            }
            for relative_name in relative_names:
                top_level = PurePosixPath(relative_name).parts[0]
                if top_level not in allowed_roots:
                    raise DistributionInspectionError(
                        f"sdist contains an unintended repository path: {relative_name}"
                    )

            package_info_name = f"{expected_root}/PKG-INFO"
            package_info_file = archive.extractfile(file_members[package_info_name])
            if package_info_file is None:
                raise DistributionInspectionError("Cannot read sdist PKG-INFO.")
            _validate_metadata(
                _parse_metadata(package_info_file.read()), identity
            )

            textual_members: list[tuple[str, bytes]] = []
            for name, member in file_members.items():
                relative_name = "/".join(PurePosixPath(name).parts[1:])
                if _is_text_member(relative_name):
                    file = archive.extractfile(member)
                    if file is None:
                        raise DistributionInspectionError(
                            f"Cannot read sdist member: {name}"
                        )
                    textual_members.append((name, file.read()))
            _scan_archive_text(textual_members, private_values)
    except (OSError, tarfile.TarError) as error:
        raise DistributionInspectionError(
            f"Cannot read sdist {path.name}: {error}"
        ) from error

    return ArtifactInspection(
        kind="sdist",
        path=path,
        member_count=len(file_members),
        sha256=_sha256_file(path),
    )


def _read_literal_assignment(path: Path, attribute_name: str) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(
            isinstance(target, ast.Name) and target.id == attribute_name
            for target in targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise DistributionInspectionError(
        f"Cannot resolve literal {attribute_name} from {path}."
    )


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def _validate_member_names(names: Iterable[str]) -> None:
    names = list(names)
    if len(names) != len(set(names)):
        raise DistributionInspectionError("Archive contains duplicate member names.")
    for name in names:
        stripped = name.rstrip("/")
        if (
            not stripped
            or "\\" in name
            or "\x00" in name
            or "//" in name
        ):
            raise DistributionInspectionError(f"Unsafe archive member name: {name!r}")
        path = PurePosixPath(stripped)
        if (
            path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or ":" in path.parts[0]
        ):
            raise DistributionInspectionError(f"Unsafe archive member path: {name}")


def _validate_forbidden_path(name: str) -> None:
    path = PurePosixPath(name.rstrip("/"))
    lowered_parts = tuple(part.casefold() for part in path.parts)
    if FORBIDDEN_COMPONENTS.intersection(lowered_parts):
        raise DistributionInspectionError(
            f"Archive contains a forbidden path: {name}"
        )
    basename = lowered_parts[-1]
    suffix = PurePosixPath(basename).suffix
    if (
        basename == "assets.yaml"
        or basename == "check_assets.py"
        or basename.startswith(".env")
        or basename.endswith("~")
        or suffix in FORBIDDEN_SUFFIXES
    ):
        raise DistributionInspectionError(
            f"Archive contains a forbidden file: {name}"
        )


def _require_members(
    actual: set[str], required: set[str], artifact_kind: str
) -> None:
    missing = sorted(required - actual)
    if missing:
        raise DistributionInspectionError(
            f"{artifact_kind} is missing required members: {missing!r}"
        )


def _parse_metadata(data: bytes) -> Message:
    return BytesParser(policy=default).parsebytes(data)


def _validate_metadata(metadata: Message, identity: ProjectIdentity) -> None:
    expected = {
        "Name": identity.name,
        "Version": identity.version,
        "Requires-Python": identity.requires_python,
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise DistributionInspectionError(
                f"Artifact metadata {key}={metadata.get(key)!r}; expected {value!r}."
            )
    requirements = tuple(metadata.get_all("Requires-Dist", failobj=[]))
    if requirements != identity.dependencies:
        raise DistributionInspectionError(
            f"Artifact dependencies {requirements!r}; expected {identity.dependencies!r}."
        )


def _validate_record(data: bytes, file_names: set[str]) -> None:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
    recorded_names = [row[0] for row in rows if len(row) == 3]
    if len(rows) != len(recorded_names) or len(recorded_names) != len(set(recorded_names)):
        raise DistributionInspectionError("Wheel RECORD is malformed or duplicated.")
    if set(recorded_names) != file_names:
        raise DistributionInspectionError(
            "Wheel RECORD does not cover exactly the archived files."
        )


def _validate_entry_points(
    data: bytes, expected_scripts: tuple[tuple[str, str], ...]
) -> None:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(data.decode("utf-8"))
    except (UnicodeDecodeError, configparser.Error) as error:
        raise DistributionInspectionError(
            f"Wheel entry_points.txt is malformed: {error}"
        ) from error

    if parser.sections() != ["console_scripts"]:
        raise DistributionInspectionError(
            "Wheel must contain only the console_scripts entry-point group."
        )
    actual_scripts = tuple(sorted(parser.items("console_scripts")))
    if actual_scripts != expected_scripts:
        raise DistributionInspectionError(
            f"Wheel console scripts {actual_scripts!r}; "
            f"expected {expected_scripts!r}."
        )


def _is_text_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        path.suffix.casefold() in TEXT_SUFFIXES
        or path.name in {"MANIFEST.in", "METADATA", "PKG-INFO", "RECORD", "WHEEL"}
    )


def _scan_archive_text(
    members: Iterable[tuple[str, bytes]], private_values: Iterable[str]
) -> None:
    tokens: set[bytes] = set()
    for value in private_values:
        if not value or len(value) < 6:
            continue
        variants = {value, value.replace("\\", "/"), value.replace("/", "\\")}
        tokens.update(variant.encode("utf-8", errors="ignore") for variant in variants)

    for name, data in members:
        if not _is_text_member(name):
            continue
        for marker in SECRET_MARKERS:
            if marker in data:
                raise DistributionInspectionError(
                    f"Archive member contains private-key material: {name}"
                )
        for token in tokens:
            if token and token in data:
                raise DistributionInspectionError(
                    f"Archive member contains a private local path: {name}"
                )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect one wheel and one sdist without extracting them."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("dist"),
        help="clean directory containing exactly one wheel and one sdist",
    )
    arguments = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]

    try:
        identity = load_project_identity(project_root)
        reports = inspect_distribution_directory(
            arguments.directory,
            identity,
            project_root=project_root,
        )
    except (DistributionInspectionError, KeyError, OSError, SyntaxError, ValueError) as error:
        print(f"DISTRIBUTION INSPECTION — FAIL: {error}")
        return 2

    print("DISTRIBUTION INSPECTION — PASS")
    print(f"Name: {identity.name}")
    print(f"Version: {identity.version}")
    for report in reports:
        print(f"{report.kind}: {report.path.name}")
        print(f"  members: {report.member_count}")
        print(f"  SHA-256: {report.sha256}")
    print("No artifact was extracted, installed, or published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
