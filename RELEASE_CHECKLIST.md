# MMD Asset Registry v0.7.0 Release Checklist

Use this checklist after the feature branch is complete. Do not commit or
redistribute any private or third-party production model.

## 1. Verify the feature branch

- [ ] Confirm the expected branch and a clean working tree:

  ```bat
  git branch --show-current
  git status
  git --no-pager log -5 --oneline --decorate
  ```

- [ ] Confirm release metadata:

  ```bat
  python check_assets.py --version
  python -c "from mmd_registry import __version__; assert __version__ == '0.7.0'"
  ```

- [ ] Compile and run all automated checks:

  ```bat
  python -m compileall -f mmd_registry tests check_assets.py
  python -m unittest discover -s tests -q
  git diff --check
  ```

- [ ] Confirm all release-facing command help pages:

  ```bat
  python check_assets.py validate --help
  python check_assets.py hash --help
  python check_assets.py inspect --help
  python check_assets.py scan --help
  python check_assets.py roundtrip --help
  python check_assets.py doctor --help
  python check_assets.py bones --help
  python check_assets.py rig --help
  ```

## 2. Reconfirm safety and compatibility

- [ ] Registry schemas `0.2` and `0.3` remain supported; latest remains `0.3`.
- [ ] Existing `validate`, `hash`, `inspect`, `scan`, `doctor`, `bones`, and
  `rig` commands retain their prior behavior.
- [ ] `roundtrip` refuses an input/output alias and refuses an existing output
  unless `--overwrite` is explicitly supplied.
- [ ] PMX output is written only to a distinct user-selected path; no in-place
  edit or automatic repair is performed.
- [ ] Generated fixtures cover PMX 2.0/2.1, UTF-8/UTF-16LE, uniform and mixed
  1/2/4-byte indices, all deform types, all morph types, and physics sections.

## 3. Private real-model validation

- [ ] Private real-model validation passes parse → serialize → parse semantic
  equality, cross-reference validation, input-integrity verification, and
  temporary-output cleanup.
- [ ] The private model and textures remain outside the repository.
- [ ] No third-party PMX, texture, archive, derived binary, or identifying
  local path is staged or committed.
- [ ] Inspect tracked model placeholders before publication:

  ```bat
  git ls-files -s "*.pmx"
  git status --short
  ```

## 4. Publish the pull request

- [ ] Review the complete branch diff:

  ```bat
  git --no-pager diff main...HEAD --check
  git --no-pager diff main...HEAD --stat
  git --no-pager log main..HEAD --oneline
  ```

- [ ] Push the feature branch and open a pull request only after local checks
  pass.
- [ ] Wait for both Ubuntu and Windows jobs:

  ```bat
  gh pr checks --watch
  ```

- [ ] Review the PR file list and confirm no private asset is present.
- [ ] Merge only when required checks pass and review is complete.

## 5. Tag and release

- [ ] Synchronize local `main` after merging:

  ```bat
  git switch main
  git pull --ff-only origin main
  git status
  ```

- [ ] Re-run the version and test checks on merged `main`.
- [ ] Create and push the annotated tag:

  ```bat
  git tag -a v0.7.0 -m "MMD Asset Registry v0.7.0"
  git push origin v0.7.0
  ```

- [ ] Publish the release with reviewed notes:

  ```bat
  gh release create v0.7.0 --verify-tag --title "MMD Asset Registry v0.7.0" --notes-file "%USERPROFILE%\Downloads\v0.7.0-release-notes.md"
  ```

- [ ] Verify the published release is neither draft nor prerelease:

  ```bat
  gh release view v0.7.0 --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish
  ```

## 6. Post-release confirmation

- [ ] Confirm `main`, `origin/main`, and tag `v0.7.0` identify the intended
  release commit.
- [ ] Confirm the release page documents PMX writer safety, generated fixture
  coverage, private real-model verification, compatibility, and limitations.
- [ ] Keep the private validation output local; do not attach the production
  PMX or textures to the GitHub release.
