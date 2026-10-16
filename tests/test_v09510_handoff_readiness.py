"""CP16 Handoff Readiness: frozen 14-case cumulative contract (synthetic-only).

Checks known 10 hardening modules, 28 source/test digests, canonical CP15
integration and repository boundary. Never touches private PMX, MODELS, POSES,
production writes, Git mutations, version or distribution.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

PINS = {'tests/test_v09510_unicode_name_hardening.py': '59920ee3edfa20ba0475bdf3d86b0f57068d995ed1de17e95d2e225167016534', 'tests/test_v09510_duplicate_unnamed_material_hardening.py': '64596bb0fd85af39eec1bab8a39152572f1e1b9cfe006f51710face0aefb8793', 'tests/test_v09510_multiple_semantic_material_hardening.py': '3a7527aa9d5bc9272582b442e82c32b58f96e634143f81c0b12bc3c679e7ed06', 'tests/test_v09510_texture_material_only_hardening.py': 'b8192dff70d90d0c10a728a25ff65b6cde10116d99fce3317e2421aac593a165', 'tests/test_v09510_malformed_evidence_hardening.py': '24c4278a894183480189e1dabf1d61257b7b3a72b7baae55956347884501de12', 'tests/test_v09510_source_drift_race_hardening.py': 'c1ce58272e824dc84500ff9eebb550d2c43efe31fed0a7c4cb3ddd98807505b6', 'mmd_registry/smart_part_detection.py': '231a6e6a7c31c6d089cbe829b91495629c9d41eb9a8d8d2fa98eca35215c51e5', 'mmd_registry/smart_parts.py': 'a1c3441fc37b3798293441e55d268a408f095c5e78d6591ed2a14865db5a1558', 'mmd_registry/services/_smart_inspection.py': 'b5ba5e4f996c43b416a4794c0f0f6d7fc25e3a9ec52a88b89f986ec3aa36ed90', 'mmd_registry/services/_smart_material_draft.py': '862804e500a6abfd3b0bd717ab4ba8c629ac1c0f4d15fe397a4fe93d62074e71', 'mmd_registry/services/_smart_material_appearance.py': '5a239c1c0d4a66368ba38b0face46baf67f208eef55582e4f33c2457c4b6eccb', 'mmd_registry/services/_smart_material_preview.py': '75e504df99945d52f9f9743ae9db6ab589745c73edc10d8c560f6eed1f9429af', 'mmd_registry/services/_smart_material_apply.py': '70b3e4397a4896f789831068e5f3b5a67a728ce6c4fe4e266cea917314fb3579', 'mmd_registry/services/structural_authoring_catalog.py': 'c0cdb7bdadbe98f9a055a6eb8b44ba391d3f16fff264478929d6fb74fd42a205', 'mmd_registry/pmx/document.py': 'ab0bbf978db449c1ffd9166973c9f38a259dc0eb49e2da22187ddae9305ae791', 'mmd_registry/pmx/editing/engine.py': 'd64e7ac23e2fba19c24f733794f52813ae4a2cdc291281c77536fc198da5b020', 'mmd_registry/pmx/editing/plan.py': '8d395e16645cda35173d46f291779cc8db2d391db94a99104f33f67b9d2972eb', 'mmd_registry/pmx/editing/preview.py': '19e4b80f98c4a6126a1181d1a67b04eaa7afa3cc3954f256e3316aee84d50069', 'mmd_registry/pmx/editing/output.py': 'e24683641043bf09719222b95e36e659e3c23c07a1322b9768479719a0ffccd8', 'mmd_registry/pmx/editing/errors.py': '18a6351a9b790d17a2ff62a787c911926f7b27c80aaa3cfea07994f2633606b6', 'mmd_registry/services/__init__.py': 'b20d42e3df579e119f0a918958dd450831dcdcf45b383adfcee0243857c4ab45', 'tests/test_v0957_smart_material_preview_bridge.py': 'd5d7561174066440ec4932a938812176eb844212cf16ebbc70a24c5f080262eb', 'tests/test_v0958_smart_material_apply_integration.py': '91893ddeee697b5bfc90d5df833084dc2cea21e177b32e7b97f6424627b18efb', 'tests/test_v0959_smart_material_appearance.py': 'ab7eb8346b443c88076fae1b29d29196c1baf5844426665bc664645460929143', 'tests/test_v09510_preview_apply_parity_hardening.py': '3a5fa32a007d124bee8b0968fd8ea1d49843f07f91ce148d9eefeff7cf1b1ca2', 'tests/test_v09510_determinism_certification.py': '25e6d6d79113f5d4c32ebf8976619f6d1a6fe7051b392837e08e6251af04370f', 'tests/test_v09510_performance_hardening.py': '6680b6f345bb45b7ab4b414d61ddd822ef6211c4e4a2abd6914d823efa315ff4', 'tests/test_v09510_integration_readiness.py': '187a63f1f850314bcbdb99807951c053259ac82531673ef4c83026f8905c5163'}
METHODS = {'tests/test_v09510_unicode_name_hardening.py': 4, 'tests/test_v09510_duplicate_unnamed_material_hardening.py': 4, 'tests/test_v09510_multiple_semantic_material_hardening.py': 4, 'tests/test_v09510_texture_material_only_hardening.py': 6, 'tests/test_v09510_malformed_evidence_hardening.py': 14, 'tests/test_v09510_source_drift_race_hardening.py': 12, 'tests/test_v09510_preview_apply_parity_hardening.py': 14, 'tests/test_v09510_determinism_certification.py': 14, 'tests/test_v09510_performance_hardening.py': 14, 'tests/test_v09510_integration_readiness.py': 14}
HANDOFF_MATRIX = ((1, 'Unicode material name handling', 'tests/test_v09510_unicode_name_hardening.py', 4), (2, 'Duplicate and unnamed material fail-closed', 'tests/test_v09510_duplicate_unnamed_material_hardening.py', 4), (3, 'Multiple semantic material targets', 'tests/test_v09510_multiple_semantic_material_hardening.py', 4), (4, 'Texture versus material evidence boundaries', 'tests/test_v09510_texture_material_only_hardening.py', 6), (5, 'Malformed evidence validation', 'tests/test_v09510_malformed_evidence_hardening.py', 14), (6, 'Source drift and race prevention', 'tests/test_v09510_source_drift_race_hardening.py', 12), (7, 'Preview versus apply parity', 'tests/test_v09510_preview_apply_parity_hardening.py', 14), (8, 'Deterministic certification', 'tests/test_v09510_determinism_certification.py', 14), (9, 'Observational performance measurements', 'tests/test_v09510_performance_hardening.py', 14), (10, 'Integration dry-run readiness', 'tests/test_v09510_integration_readiness.py', 14), (11, '28-file provenance manifest', 'sha256_manifest', 28), (12, 'Repeated 8-path canonical integration', 'integration_digest', 8), (13, 'Focused released determinism and Smart Series', 'regression_suites', 814), (14, 'Asset Git API and no mutation safety', 'safety_boundary', 10))
MATRIX_SHA256 = '285adf01a5a3bc1434b257e4782507b77d59ca1c85f5464c08898d0d9b78b953'
MANIFEST_SHA256 = '4b5bef73ee4a441ac13ff01b4dac079afa3c13800321acf6e577bb83485af137'
INTEGRATION_SHA256 = 'd289832498d0fb12e77f1d6096e6fd44e07e9eb08ec56a110b8f4cf0635e8d8b'
BRANCH = 'feature/v0.9.5.10-smart-material-editing-hardening'
HEAD = 'd0b9b4b049d43c5fdc449e87627956631a9e12a4'
CP16_REL = 'tests/test_v09510_handoff_readiness.py'

def _root():
    return Path(__file__).resolve().parents[1]

def _sha(data):
    return hashlib.sha256(data).hexdigest()

def _module_contract(relative, expected_count):
    root = _root()
    path = root / relative
    if not path.is_file() or path.is_symlink():
        raise AssertionError('Missing or symlink test: ' + relative)
    content = path.read_bytes()
    if _sha(content) != PINS[relative]:
        raise AssertionError('Frozen test digest mismatch: ' + relative)
    tree = ast.parse(content.decode('utf-8'), filename=relative)
    compile(tree, relative, 'exec')
    methods = [n.name for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name.startswith('test_')]
    if len(methods) != expected_count or len(set(methods)) != expected_count:
        raise AssertionError('Test count/identity drift: ' + relative)
    return len(methods)

class V09510HandoffReadinessTests(unittest.TestCase):
    def _module(self, relative, count):
        self.assertEqual(_module_contract(relative, count), count)

    def test_cp16_01_unicode_material_name_handling(self):
        self._module('tests/test_v09510_unicode_name_hardening.py', 4)

    def test_cp16_02_duplicate_unnamed_material_fail_closed(self):
        self._module('tests/test_v09510_duplicate_unnamed_material_hardening.py', 4)

    def test_cp16_03_multiple_semantic_targets(self):
        self._module('tests/test_v09510_multiple_semantic_material_hardening.py', 4)

    def test_cp16_04_texture_material_evidence_boundary(self):
        self._module('tests/test_v09510_texture_material_only_hardening.py', 6)

    def test_cp16_05_malformed_evidence_validation(self):
        self._module('tests/test_v09510_malformed_evidence_hardening.py', 14)

    def test_cp16_06_source_drift_race_prevention(self):
        self._module('tests/test_v09510_source_drift_race_hardening.py', 12)

    def test_cp16_07_preview_apply_parity(self):
        self._module('tests/test_v09510_preview_apply_parity_hardening.py', 14)

    def test_cp16_08_determinism_certification(self):
        self._module('tests/test_v09510_determinism_certification.py', 14)

    def test_cp16_09_observational_performance(self):
        self._module('tests/test_v09510_performance_hardening.py', 14)

    def test_cp16_10_integration_readiness(self):
        self._module('tests/test_v09510_integration_readiness.py', 14)

    def test_cp16_11_provenance_manifest_28(self):
        self.assertEqual(len(PINS), 28)
        self.assertEqual(len(METHODS), 10)
        self.assertEqual(sum(METHODS.values()), 100)
        manifest = [{'path': rel, 'sha256': PINS[rel]} for rel in sorted(PINS)]
        raw = json.dumps(manifest, ensure_ascii=True,
                         sort_keys=True, separators=(',', ':')).encode('utf-8')
        self.assertEqual(_sha(raw), MANIFEST_SHA256)
        for rel, expected in PINS.items():
            file = _root() / rel
            self.assertTrue(file.is_file() and not file.is_symlink(), rel)
            self.assertEqual(_sha(file.read_bytes()), expected, rel)
        matrix = json.dumps(HANDOFF_MATRIX, ensure_ascii=True,
                            separators=(',', ':')).encode('utf-8')
        self.assertEqual(_sha(matrix), MATRIX_SHA256)
        self.assertEqual([row[0] for row in HANDOFF_MATRIX], list(range(1, 15)))
        self.assertEqual(tuple((row[2], row[3]) for row in HANDOFF_MATRIX[:10]),
                         tuple(METHODS.items()))

    def test_cp16_12_repeat_eight_path_canonical_integration(self):
        from tests.test_v09510_integration_readiness import PROBE, _parse
        self.assertEqual(_sha(PROBE.encode('utf-8')),
                         '126a13272a683e2d78a35d0bb344944f8dfb6603d1a49a8186d315bff3affbdc')
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                   PYTHONIOENCODING='utf-8:strict')
        snapshots = []
        digests = []
        for _ in range(2):
            run = subprocess.run([sys.executable, '-B', '-c', PROBE], cwd=_root(),
                                 env=env, capture_output=True, text=True,
                                 encoding='utf-8', errors='strict', timeout=90, check=False)
            self.assertEqual(run.returncode, 0, run.stderr[-1500:])
            parsed, digest = _parse(run.stdout)
            snapshots.append(parsed)
            digests.append(digest)
        self.assertEqual(digests, [INTEGRATION_SHA256]*2)
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertEqual(len(snapshots[0]['cases']), 8)
        self.assertEqual({(c['shape'], c['capability']) for c in snapshots[0]['cases']},
                         {(s, c) for s in ('single','multi') for c in
                          ('material_color','transparency','material_specular','material_edge')})
        self.assertTrue(all(c['preview_written'] is False for c in snapshots[0]['cases']))

    def test_cp16_13_regression_inventory(self):
        self.assertEqual(sum(_module_contract(path, count)
                             for path, count in METHODS.items()), 100)
        released = ('tests.test_v0956_smart_material_draft',
                    'tests.test_v0957_smart_material_preview_bridge',
                    'tests.test_v0958_smart_material_apply_integration',
                    'tests.test_v0959_smart_material_appearance')
        loader = unittest.defaultTestLoader
        self.assertEqual(sum(loader.loadTestsFromName(m).countTestCases()
                             for m in released), 113)
        for name in ('tests.test_v09510_preview_apply_parity_hardening',
                     'tests.test_v09510_determinism_certification',
                     'tests.test_v09510_performance_hardening',
                     'tests.test_v09510_integration_readiness'):
            self.assertEqual(loader.loadTestsFromName(name).countTestCases(), 14)
        # End-to-end 828-suite executes in the external allowlisted runner,
        # not recursively inside this test.

    def test_cp16_14_git_api_and_no_private_asset_boundary(self):
        import mmd_registry
        self.assertEqual(mmd_registry.__version__, '0.9.5.9')
        self.assertEqual(mmd_registry.__all__, ('__version__',))
        self.assertFalse(os.environ.get('MMD_REGISTRY_PRIVATE_PMX'))
        self.assertEqual(len(METHODS), 10)
        root = _root()
        approved = set(METHODS) | {CP16_REL}
        self.assertEqual(len(approved), 11)

        def git(*args):
            run = subprocess.run(('git', *args), cwd=root, capture_output=True,
                                 text=True, encoding='utf-8', errors='strict',
                                 timeout=30, check=False)
            self.assertEqual(run.returncode, 0, run.stderr[-800:])
            self.assertFalse(run.stderr.strip())
            return run.stdout

        self.assertEqual(git('branch', '--show-current').strip(), BRANCH)
        self.assertEqual(git('rev-parse', 'main').strip(), HEAD)
        self.assertEqual(git('rev-parse', 'origin/main').strip(), HEAD)
        actual_head = git('rev-parse', 'HEAD').strip()
        self.assertEqual(git('diff', '--name-only').strip(), '')
        status = git('status', '--porcelain', '--untracked-files=all').splitlines()
        self.assertEqual(len(status), len(set(status)))
        changes = git('diff', '--cached', '--name-status').splitlines()
        index = git('ls-files', '--stage', '--', *sorted(approved)).splitlines()
        untracked = {'?? ' + rel for rel in approved}
        staged = {'A  ' + rel for rel in approved}
        if actual_head == HEAD and not changes:
            # Before staging: all eleven tests exist, but none are tracked.
            self.assertEqual(set(status), untracked)
            self.assertEqual(len(status), 11)
            self.assertEqual(index, [])
        elif actual_head == HEAD:
            # Before commit: exactly eleven new tests are staged.
            self.assertEqual(set(changes), {'A\t' + rel for rel in approved})
            self.assertEqual(len(changes), 11)
            self.assertEqual(set(status), staged)
            self.assertEqual(len(status), 11)
        else:
            # After commit: one non-merge child of frozen base, with only eleven additions.
            parents = git('rev-list', '--parents', '-n', '1', 'HEAD').split()
            self.assertEqual(parents, [actual_head, HEAD])
            committed = git('diff-tree', '--no-commit-id', '--no-renames',
                            '--name-status', '-r', 'HEAD').splitlines()
            self.assertEqual(len(committed), 11)
            self.assertEqual(set(committed), {'A\t' + rel for rel in approved})
            self.assertEqual(changes, [])
            self.assertEqual(status, [])

        if actual_head != HEAD or changes:
            # Both index states must contain only normal stage-zero test blobs.
            self.assertEqual(len(index), 11)
            observed = set()
            for row in index:
                mode, oid, stage_path = row.split(' ', 2)
                self.assertEqual(mode, '100644')
                self.assertEqual(len(oid), 40)
                stage_number, rel = stage_path.split('\t', 1)
                self.assertEqual(stage_number, '0')
                self.assertIn(rel, approved)
                observed.add(rel)
                # Git object in index/HEAD must represent current file bytes.
                expected_oid = git('hash-object', '--', rel).strip()
                self.assertEqual(oid, expected_oid)
            self.assertEqual(observed, approved)

if __name__ == '__main__':
    unittest.main()
