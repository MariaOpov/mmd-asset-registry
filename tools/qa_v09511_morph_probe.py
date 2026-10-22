"""B-owned read-only Smart Morph QA probe. No installation or Git mutation.

Default: scoped readiness only. Optional --run-tests requires an already
separately approved B .venv; this tool never creates/installs dependencies.
Use Python -B to suppress __pycache__ generation during execution.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

BASE = "efc3a3925b72518c1a4c2fc4cb74916e3ff7f0a3"
BRANCH = "test/v0.9.5.11-smart-morph-qa"
B_ROOT = Path(r"D:\MMD\mmd-asset-registry-smart")
A_ROOT = Path(r"D:\MMD\mmd-asset-registry")
OWNED = (
    "tests/test_v09511_qa_morph_adversarial.py",
    "tools/qa_v09511_morph_probe.py",
)


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 125, ""
    return result.returncode, result.stdout.strip()


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _check() -> tuple[bool, str]:
    if not A_ROOT.is_dir() or not B_ROOT.is_dir():
        return False, "WORKTREE_DIR_MISSING"
    for root, expected_branch in ((A_ROOT, "feature/v0.9.5.11-smart-morph-core"),
                                  (B_ROOT, BRANCH)):
        rc, actual = _git(root, "rev-parse", "--show-toplevel")
        if rc != 0 or _norm(actual) != _norm(root):
            return False, "WORKTREE_ROOT_MISMATCH"
        rc, branch = _git(root, "branch", "--show-current")
        if rc != 0 or branch != expected_branch:
            return False, "BRANCH_MISMATCH"
        rc, head = _git(root, "rev-parse", "HEAD")
        if rc != 0 or head != BASE:
            return False, "BASELINE_HEAD_MISMATCH"
    rc, listing = _git(B_ROOT, "worktree", "list", "--porcelain")
    if rc != 0 or sum(line.startswith("worktree ") for line in listing.splitlines()) != 2:
        return False, "WORKTREE_COUNT_MISMATCH"
    rc, staged = _git(B_ROOT, "diff", "--cached", "--name-only")
    if rc != 0 or staged:
        return False, "B_INDEX_NOT_EMPTY"
    rc, status = _git(B_ROOT, "status", "--porcelain=v1", "--untracked-files=all")
    if rc != 0:
        return False, "B_STATUS_UNAVAILABLE"
    observed = {line[3:].replace("\\", "/") for line in status.splitlines() if len(line) > 3}
    if not observed.issubset(set(OWNED)):
        return False, "B_SCOPE_VIOLATION"
    if not all((B_ROOT / path).is_file() for path in OWNED):
        return False, "B_QA_FILES_NOT_INSTALLED"
    return True, "READY_READONLY"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only B QA scope probe")
    parser.add_argument("--run-tests", action="store_true", help="Only after separate B venv approval")
    args = parser.parse_args()
    ok, reason = _check()
    print("SESSION=B")
    print("CHECKPOINT=CP04B_QA_SCOPE_PROBE")
    print("PROBE_RESULT=" + ("PASS" if ok else "HOLD"))
    print("PROBE_REASON=" + reason)
    if not ok:
        return 2
    if not args.run_tests:
        print("TESTS_RUN=0")
        print("B_VENV=DEFERRED")
        return 0
    b_python = B_ROOT / ".venv" / "Scripts" / "python.exe"
    if not b_python.is_file() or _norm(sys.executable) != _norm(b_python):
        print("TEST_EXECUTION=HOLD_B_VENV_NOT_APPROVED_OR_NOT_ACTIVE")
        return 2
    result = subprocess.run(
        [str(b_python), "-B", "-m", "unittest", "tests.test_v09511_qa_morph_adversarial"],
        cwd=B_ROOT, check=False,
    )
    print("TEST_EXIT_CODE=" + str(result.returncode))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
