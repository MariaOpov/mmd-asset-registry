"""Verify a built wheel in a disposable virtual environment outside the repo."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

if __package__:
    from tools.inspect_distribution_artifacts import (
        DistributionInspectionError,
        ProjectIdentity,
        inspect_distribution_directory,
        load_project_identity,
    )
else:
    from inspect_distribution_artifacts import (  # type: ignore[no-redef]
        DistributionInspectionError,
        ProjectIdentity,
        inspect_distribution_directory,
        load_project_identity,
    )


COMMAND_NAME = "mmd-asset-registry"
ENTRY_POINT_VALUE = "mmd_registry.cli:main"
PROBE_RESULT_PREFIX = "CLEAN_INSTALL_PROBE="
PROBE_SOURCE = r'''from __future__ import annotations

import importlib.metadata as metadata
import json
import sys
from dataclasses import replace
from io import BytesIO
from pathlib import Path


def is_within(path: Path, parent: Path) -> bool:
    path = path.resolve()
    parent = parent.resolve()
    return path == parent or parent in path.parents


expectations = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
project_root = Path(sys.argv[2]).resolve()
working_directory = Path.cwd().resolve()
environment_root = Path(sys.prefix).resolve()

assert sys.prefix != sys.base_prefix, "probe is not running in a virtual environment"
assert not is_within(working_directory, project_root), "probe cwd is inside repository"

for entry in sys.path:
    if entry and is_within(Path(entry), project_root):
        raise AssertionError(f"repository path leaked into sys.path: {entry}")

import mmd_registry
import mmd_registry._internal
import mmd_registry.capabilities as public_capabilities
import mmd_registry.diagnostics as public_diagnostics
import mmd_registry.pmx
import mmd_registry.pmx.editing
import mmd_registry.services as public_services
import yaml

assert "mmd_registry.cli" not in sys.modules, "public imports loaded CLI"
assert mmd_registry.__version__ == expectations["version"], "runtime version mismatch"
assert public_capabilities.__all__ == (
    "PmxCapabilityManifest",
    "PmxRoundTripContract",
    "get_capabilities",
), "public capability exports mismatch"
capability_manifest = public_capabilities.get_capabilities()
assert capability_manifest.edit_operation_types == (
    "set_model_info",
    "set_texture_path",
    "update_material",
), "installed capability manifest mismatch"
assert public_diagnostics.__all__ == (
    "PmxServiceDiagnostic",
    "PmxServiceDiagnosticCode",
    "PmxServiceError",
    "PmxServiceOperation",
    "diagnostic_from_service_error",
), "public diagnostic exports mismatch"
internal_diagnostic = public_diagnostics.diagnostic_from_service_error(
    public_diagnostics.PmxServiceOperation.LOAD_DOCUMENT,
    RuntimeError("private implementation detail"),
)
assert internal_diagnostic.to_dict() == {
    "code": "service_internal_error",
    "operation": "load_document",
    "message": "Unexpected internal service failure.",
}, "installed diagnostic redaction mismatch"

document_source = bytes.fromhex(
    "504d5820000000400801000101010101010e0000005465737420504d58204d6f64656c0e"
    "0000005465737420504d58204d6f64656c00000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000000"
)
installed_document = public_services.load_document(BytesIO(document_source))
installed_metadata = public_services.inspect_document(installed_document)
assert (
    installed_metadata.version,
    installed_metadata.encoding,
    installed_metadata.local_name,
    installed_metadata.universal_name,
    installed_metadata.local_comments,
    installed_metadata.universal_comments,
) == (
    2.0,
    "utf-8",
    "Test PMX Model",
    "Test PMX Model",
    "",
    "",
), "installed document service mismatch"
try:
    public_services.load_document(BytesIO(b"bad"))
except public_diagnostics.PmxServiceError as error:
    assert error.to_dict() == {
        "code": "source_invalid",
        "operation": "load_document",
        "message": "Source PMX data is invalid.",
        "details": {
            "format_name": "PMX",
            "offset": 0,
            "parse_operation": "reading PMX signature",
            "record_index": None,
            "section": "signature",
        },
    }, "installed document diagnostic mismatch"
else:
    raise AssertionError("installed document service accepted malformed PMX")

valid_validation = public_services.validate_document(installed_document)
assert valid_validation.to_dict() == {
    "is_valid": True,
    "issues": [],
}, "installed valid-document validation mismatch"
invalid_document = replace(
    installed_document,
    geometry=replace(installed_document.geometry, surface_indices=(0, 0, 0)),
)
invalid_validation = public_services.validate_document(invalid_document)
assert invalid_validation.to_dict() == {
    "is_valid": False,
    "issues": [
        {
            "section": "surface_indices",
            "record_index": 0,
            "field": "vertex_index",
            "reason": "index 0 is invalid; expected no value.",
        }
    ],
}, "installed invalid-document validation mismatch"
try:
    public_services.validate_document(object())
except public_diagnostics.PmxServiceError as error:
    assert error.to_dict() == {
        "code": "invalid_argument",
        "operation": "validate_document",
        "message": "Invalid service input.",
    }, "installed validation diagnostic mismatch"
else:
    raise AssertionError("installed validation service accepted invalid input")

package_path = Path(mmd_registry.__file__).resolve()
dependency_path = Path(yaml.__file__).resolve()
assert is_within(package_path, environment_root), "package did not load from clean venv"
assert is_within(dependency_path, environment_root), (
    "dependency did not load from clean venv"
)
assert not is_within(package_path, project_root), "package loaded from repository"
assert not is_within(dependency_path, project_root), "dependency loaded from repository"

distribution = metadata.distribution(expectations["name"])
assert distribution.version == expectations["version"], "installed version mismatch"
assert sorted(distribution.requires or []) == sorted(expectations["dependencies"]), (
    "installed dependency metadata mismatch"
)

entry_points = sorted(
    (entry_point.group, entry_point.name, entry_point.value)
    for entry_point in distribution.entry_points
)
expected_entry_points = [
    ["console_scripts", name, value]
    for name, value in expectations["console_scripts"]
]
assert [list(item) for item in entry_points] == expected_entry_points, (
    "installed entry-point metadata mismatch"
)

loaded_entry_point = next(iter(distribution.entry_points)).load()
assert loaded_entry_point.__module__ == "mmd_registry.cli"
assert loaded_entry_point.__name__ == "main"

result = {
    "dependency_path": str(dependency_path),
    "environment_root": str(environment_root),
    "package_path": str(package_path),
    "version": distribution.version,
    "working_directory": str(working_directory),
}
print("CLEAN_INSTALL_PROBE=" + json.dumps(result, sort_keys=True))
'''


class CleanInstallVerificationError(RuntimeError):
    """Raised when isolated installation or an installed-package probe fails."""


@dataclass(frozen=True, slots=True)
class EnvironmentPaths:
    """Platform-specific executables inside one disposable virtual environment."""

    root: Path
    python: Path
    console: Path


@dataclass(frozen=True, slots=True)
class CleanInstallReport:
    """Evidence returned by one successful clean installation verification."""

    identity: ProjectIdentity
    wheel_name: str
    package_path: str
    dependency_path: str
    working_directory: str
    console_version: str


def environment_paths(root: Path, *, windows: bool | None = None) -> EnvironmentPaths:
    """Return expected Python and console launcher paths for a venv."""

    is_windows = os.name == "nt" if windows is None else windows
    scripts = root / ("Scripts" if is_windows else "bin")
    python_name = "python.exe" if is_windows else "python"
    console_name = f"{COMMAND_NAME}.exe" if is_windows else COMMAND_NAME
    return EnvironmentPaths(
        root=root,
        python=scripts / python_name,
        console=scripts / console_name,
    )


def clean_subprocess_environment(
    source: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Remove import and active-venv state that could hide packaging defects."""

    environment = dict(os.environ if source is None else source)
    for variable in (
        "MMD_REGISTRY_PRIVATE_PMX",
        "PYTHONHOME",
        "PYTHONPATH",
        "VIRTUAL_ENV",
        "__PYVENV_LAUNCHER__",
    ):
        environment.pop(variable, None)
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


def install_arguments(
    python: Path,
    wheel: Path,
    *,
    no_index: bool = False,
    find_links: Sequence[Path] = (),
) -> list[str]:
    """Build dependency-resolving pip arguments for one local wheel."""

    arguments = [
        str(python),
        "-I",
        "-m",
        "pip",
        "--isolated",
        "install",
        "--disable-pip-version-check",
        "--no-input",
    ]
    if no_index:
        arguments.append("--no-index")
    for directory in find_links:
        arguments.extend(("--find-links", str(directory.resolve())))
    arguments.append(str(wheel.resolve()))
    return arguments


def verify_clean_install(
    artifact_directory: Path,
    *,
    project_root: Path,
    base_python: Path | None = None,
    work_parent: Path | None = None,
    no_index: bool = False,
    find_links: Sequence[Path] = (),
) -> CleanInstallReport:
    """Install and probe exactly one inspected wheel in a fresh external venv."""

    root = project_root.resolve()
    parent = (
        Path(tempfile.gettempdir()).resolve()
        if work_parent is None
        else work_parent.resolve()
    )
    _validate_work_parent(parent, root)
    resolved_links = tuple(_validate_find_links(path) for path in find_links)

    identity = load_project_identity(root)
    wheel_report, _ = inspect_distribution_directory(
        artifact_directory,
        identity,
        project_root=root,
    )
    expected_scripts = ((COMMAND_NAME, ENTRY_POINT_VALUE),)
    if identity.console_scripts != expected_scripts:
        raise CleanInstallVerificationError(
            f"Expected console scripts {expected_scripts!r}; "
            f"found {identity.console_scripts!r}."
        )

    interpreter = Path(sys.executable if base_python is None else base_python).resolve()
    if not interpreter.is_file():
        raise CleanInstallVerificationError(
            f"Base Python executable does not exist: {interpreter}"
        )

    environment = clean_subprocess_environment()
    try:
        with tempfile.TemporaryDirectory(
            prefix="mmd-registry-clean-install-",
            dir=parent,
        ) as temporary_directory:
            workspace = Path(temporary_directory).resolve()
            if _is_within(workspace, root):
                raise CleanInstallVerificationError(
                    "Temporary clean-install workspace is inside the repository."
                )
            paths = environment_paths(workspace / "venv")
            probe_path = workspace / "probe_installed_package.py"
            expectations_path = workspace / "expectations.json"
            probe_path.write_text(PROBE_SOURCE, encoding="utf-8", newline="\n")
            expectations_path.write_text(
                json.dumps(
                    {
                        "console_scripts": identity.console_scripts,
                        "dependencies": identity.dependencies,
                        "name": identity.name,
                        "version": identity.version,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
                newline="\n",
            )

            _run_command(
                [str(interpreter), "-I", "-m", "venv", str(paths.root)],
                stage="create isolated virtual environment",
                cwd=workspace,
                environment=environment,
            )
            if not paths.python.is_file():
                raise CleanInstallVerificationError(
                    f"Virtual environment Python was not created: {paths.python}"
                )

            _run_command(
                install_arguments(
                    paths.python,
                    wheel_report.path,
                    no_index=no_index,
                    find_links=resolved_links,
                ),
                stage="install wheel and runtime dependencies",
                cwd=workspace,
                environment=environment,
            )
            _run_command(
                [
                    str(paths.python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "check",
                ],
                stage="check installed dependency consistency",
                cwd=workspace,
                environment=environment,
            )
            probe = _run_command(
                [
                    str(paths.python),
                    "-I",
                    str(probe_path),
                    str(expectations_path),
                    str(root),
                ],
                stage="probe installed package outside repository",
                cwd=workspace,
                environment=environment,
            )
            probe_result = _parse_probe_result(probe.stdout)

            if not paths.console.is_file():
                raise CleanInstallVerificationError(
                    f"Installed console launcher does not exist: {paths.console}"
                )
            expected_version = f"{COMMAND_NAME} {identity.version}"
            console_version = _run_command(
                [str(paths.console), "--version"],
                stage="run installed console version",
                cwd=workspace,
                environment=environment,
            ).stdout.strip()
            if console_version != expected_version:
                raise CleanInstallVerificationError(
                    f"Installed console version was {console_version!r}; "
                    f"expected {expected_version!r}."
                )
            console_help = _run_command(
                [str(paths.console), "--help"],
                stage="run installed console help",
                cwd=workspace,
                environment=environment,
            ).stdout
            _validate_help(console_help)

            module_version = _run_command(
                [str(paths.python), "-I", "-m", "mmd_registry.cli", "--version"],
                stage="run installed module version",
                cwd=workspace,
                environment=environment,
            ).stdout.strip()
            if module_version != expected_version:
                raise CleanInstallVerificationError(
                    f"Installed module version was {module_version!r}; "
                    f"expected {expected_version!r}."
                )

            report = CleanInstallReport(
                identity=identity,
                wheel_name=wheel_report.path.name,
                package_path=probe_result["package_path"],
                dependency_path=probe_result["dependency_path"],
                working_directory=probe_result["working_directory"],
                console_version=console_version,
            )
    except OSError as error:
        raise CleanInstallVerificationError(
            f"Cannot create or clean the temporary installation workspace: {error}"
        ) from error

    return report


def _validate_work_parent(parent: Path, project_root: Path) -> None:
    if not parent.is_dir():
        raise CleanInstallVerificationError(
            f"Temporary workspace parent does not exist: {parent}"
        )
    if _is_within(parent, project_root):
        raise CleanInstallVerificationError(
            "Temporary workspace parent must be outside the repository."
        )


def _validate_find_links(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise CleanInstallVerificationError(
            f"Dependency wheel directory does not exist: {resolved}"
        )
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    resolved_path = path.resolve()
    resolved_parent = parent.resolve()
    return resolved_path == resolved_parent or resolved_parent in resolved_path.parents


def _run_command(
    arguments: Sequence[str],
    *,
    stage: str,
    cwd: Path,
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(arguments),
            cwd=cwd,
            env=dict(environment),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    except subprocess.CalledProcessError as error:
        details = "\n".join(
            part.strip()
            for part in (error.stdout or "", error.stderr or "")
            if part.strip()
        )
        suffix = f"\n{details}" if details else ""
        raise CleanInstallVerificationError(
            f"Failed to {stage} (exit code {error.returncode}).{suffix}"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise CleanInstallVerificationError(
            f"Failed to {stage}: command exceeded 300 seconds."
        ) from error
    except OSError as error:
        raise CleanInstallVerificationError(f"Failed to {stage}: {error}") from error


def _parse_probe_result(output: str) -> dict[str, str]:
    lines = [
        line[len(PROBE_RESULT_PREFIX) :]
        for line in output.splitlines()
        if line.startswith(PROBE_RESULT_PREFIX)
    ]
    if len(lines) != 1:
        raise CleanInstallVerificationError(
            "Installed-package probe did not emit exactly one result."
        )
    try:
        result = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise CleanInstallVerificationError(
            f"Installed-package probe emitted invalid JSON: {error}"
        ) from error
    required = {
        "dependency_path",
        "environment_root",
        "package_path",
        "version",
        "working_directory",
    }
    if not isinstance(result, dict) or set(result) != required:
        raise CleanInstallVerificationError(
            "Installed-package probe result has an unexpected schema."
        )
    if not all(isinstance(value, str) and value for value in result.values()):
        raise CleanInstallVerificationError(
            "Installed-package probe result contains an invalid value."
        )
    return result


def _validate_help(output: str) -> None:
    if f"usage: {COMMAND_NAME}" not in output or "--version" not in output:
        raise CleanInstallVerificationError(
            "Installed console help does not match the public CLI contract."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Install one inspected wheel and its dependencies in a disposable "
            "virtual environment outside the repository."
        )
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("dist"),
        help="clean directory containing exactly one wheel and one sdist",
    )
    parser.add_argument(
        "--work-parent",
        type=Path,
        help="existing external directory for the disposable workspace",
    )
    parser.add_argument(
        "--no-index",
        action="store_true",
        help="disable package indexes; use with a complete dependency wheelhouse",
    )
    parser.add_argument(
        "--find-links",
        action="append",
        type=Path,
        default=[],
        metavar="DIRECTORY",
        help="additional local dependency wheel directory; may be repeated",
    )
    arguments = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]

    try:
        report = verify_clean_install(
            arguments.directory,
            project_root=project_root,
            work_parent=arguments.work_parent,
            no_index=arguments.no_index,
            find_links=arguments.find_links,
        )
    except (
        CleanInstallVerificationError,
        DistributionInspectionError,
        KeyError,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        print(f"CLEAN INSTALL VERIFICATION — FAIL: {error}")
        return 2

    print("CLEAN INSTALL VERIFICATION — PASS")
    print(f"Name: {report.identity.name}")
    print(f"Version: {report.identity.version}")
    print(f"Wheel: {report.wheel_name}")
    print(f"Installed package: {report.package_path}")
    print(f"Installed dependency: {report.dependency_path}")
    print(f"External working directory: {report.working_directory}")
    print(f"Console: {report.console_version}")
    print("The disposable virtual environment was removed.")
    print("No artifact was published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
