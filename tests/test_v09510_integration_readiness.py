"""CP15 Integration Readiness: 14 frozen synthetic-only regression tests.

Two independent in-memory integration snapshots, eight Smart Material pipelines,
source/target identity, dry-run guarantees and released compatibility.
No production writes, private PMX, Git actions, or release operations.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest

CAPABILITIES = ('material_color','transparency','material_specular','material_edge')
REFERENCE = {
  'single':'2445e393222357452dbdbc9f1d6ab16d501fc45c2c3cefa5583a3e9e9722bc8b',
  'multi':'682698fe99dff0588aa3cd58b7997fe477a71ad4af3fb34e789a4582a1894d9f',
}
REFERENCE_DIGEST = 'd289832498d0fb12e77f1d6096e6fd44e07e9eb08ec56a110b8f4cf0635e8d8b'
PROBE = "import hashlib\nimport io\nimport json\nfrom mmd_registry.pmx import load_pmx, serialize_pmx\nfrom tests.test_v09510_preview_apply_parity_hardening import _source, _build\n\nREFERENCE = {\n    'single': '2445e393222357452dbdbc9f1d6ab16d501fc45c2c3cefa5583a3e9e9722bc8b',\n    'multi': '682698fe99dff0588aa3cd58b7997fe477a71ad4af3fb34e789a4582a1894d9f',\n}\nCAPABILITIES = ('material_color', 'transparency', 'material_specular', 'material_edge')\nresults = []\nfor shape in ('single', 'multi'):\n    original = _source(shape)\n    input_hash = hashlib.sha256(original).hexdigest()\n    assert input_hash == REFERENCE[shape]\n    expected_targets = [0] if shape == 'single' else [1, 2]\n    for capability in CAPABILITIES:\n        draft, preview, confirmation = _build(original, capability)\n        info = preview.to_dict()\n        updated = serialize_pmx(preview.document)\n        assert load_pmx(io.BytesIO(updated)) == preview.document\n        assert [op.material_index for op in draft.operations] == expected_targets\n        assert draft.expected_source_sha256 == preview.source_sha256 == input_hash\n        assert confirmation.plan_sha256 == preview.plan_sha256\n        assert preview.plan_sha256 == info['plan']['sha256']\n        assert info['dry_run'] is True and info['output']['written'] is False\n        assert info['output']['sha256'] is None\n        assert info['verification']['input_unchanged'] is True\n        assert info['verification']['semantic'] == 'passed'\n        assert info['status'] == 'changes_pending'\n        assert info['audit']['summary']['changed_fields'] > 0\n        assert hashlib.sha256(original).hexdigest() == input_hash\n        results.append({\n            'shape':shape, 'capability':capability,\n            'targets':expected_targets,\n            'source_sha256':input_hash,\n            'plan_sha256':preview.plan_sha256,\n            'semantic_sha256':hashlib.sha256(updated).hexdigest(),\n            'audit_changed_fields':info['audit']['summary']['changed_fields'],\n            'preview_written':info['output']['written'],\n        })\nassert len(results) == 8\npayload = json.dumps({'schema_version':1, 'cases':results},ensure_ascii=False,sort_keys=True,separators=(',', ':'))\nprint('CP15_INTEGRATION_JSON='+payload)\nprint('CP15_INTEGRATION_SHA256='+hashlib.sha256(payload.encode('utf-8')).hexdigest())\n"


def _parse(stdout):
    lines = stdout.splitlines()
    payloads = [line.partition('=')[2] for line in lines if line.startswith('CP15_INTEGRATION_JSON=')]
    digests = [line.partition('=')[2] for line in lines if line.startswith('CP15_INTEGRATION_SHA256=')]
    if len(payloads) != 1 or len(digests) != 1:
        raise AssertionError('exactly one snapshot and digest required')
    p = payloads[0]
    actual = hashlib.sha256(p.encode('utf-8')).hexdigest()
    if actual != digests[0] or actual != REFERENCE_DIGEST:
        raise AssertionError('CP15 snapshot SHA does not match pinned audit')
    content = json.loads(p)
    if content.get('schema_version') != 1 or len(content.get('cases',[])) != 8:
        raise AssertionError('bad CP15 integration schema')
    if not isinstance(content['cases'],list):
        raise AssertionError('CP15 cases not list')
    return content,actual


class V09510IntegrationReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('MMD_REGISTRY_PRIVATE_PMX'):
            raise AssertionError('Private PMX is forbidden for CP15')
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE']='1'
        env['PYTHONNOUSERSITE']='1'
        env['PYTHONIOENCODING']='utf-8:strict'
        cls.snapshots=[]
        cls.digests=[]
        for _ in range(2):
            run = subprocess.run([sys.executable,'-B','-c',PROBE],
                capture_output=True,text=True,encoding='utf-8',errors='strict',
                env=env,timeout=90,check=False)
            if run.returncode:
                raise AssertionError('CP15 subprocess failed: '+run.stderr[-1500:])
            snapshot,digest=_parse(run.stdout)
            cls.snapshots.append(snapshot)
            cls.digests.append(digest)
        cls.cases=cls.snapshots[0]['cases']
        cls.keyed={(c['shape'],c['capability']):c for c in cls.cases}
        expected={(shape,cap) for shape in ('single','multi') for cap in CAPABILITIES}
        if set(cls.keyed)!=expected or len(cls.keyed)!=8:
            raise AssertionError('Integration capability matrix mismatch')

    def _case(self,shape,capability):
        row=self.keyed[(shape,capability)]
        self.assertEqual(row['shape'],shape)
        self.assertEqual(row['capability'],capability)
        self.assertEqual(row['source_sha256'],REFERENCE[shape])
        self.assertEqual(row['targets'],[0] if shape=='single' else [1,2])
        self.assertRegex(row['plan_sha256'],r'^[0-9a-f]{64}$')
        self.assertRegex(row['semantic_sha256'],r'^[0-9a-f]{64}$')
        self.assertIs(type(row['audit_changed_fields']),int)
        self.assertGreater(row['audit_changed_fields'],0)
        self.assertIs(row['preview_written'],False)

    def test_cp15_01_single_material_color(self): self._case('single','material_color')
    def test_cp15_02_single_transparency(self): self._case('single','transparency')
    def test_cp15_03_single_material_specular(self): self._case('single','material_specular')
    def test_cp15_04_single_material_edge(self): self._case('single','material_edge')
    def test_cp15_05_multi_material_color(self): self._case('multi','material_color')
    def test_cp15_06_multi_transparency(self): self._case('multi','transparency')
    def test_cp15_07_multi_material_specular(self): self._case('multi','material_specular')
    def test_cp15_08_multi_material_edge(self): self._case('multi','material_edge')

    def test_cp15_09_source_identity_and_target_bounds(self):
        from tests.test_v09510_preview_apply_parity_hardening import _source
        for shape in ('single','multi'):
            before=_source(shape)
            self.assertEqual(hashlib.sha256(before).hexdigest(),REFERENCE[shape])
            target=[0] if shape=='single' else [1,2]
            for cap in CAPABILITIES:
                self.assertEqual(self.keyed[(shape,cap)]['targets'],target)
            self.assertEqual(hashlib.sha256(before).hexdigest(),REFERENCE[shape])

    def test_cp15_10_plan_and_semantic_shas_stable(self):
        for before,after in zip(self.snapshots[0]['cases'],self.snapshots[1]['cases']):
            self.assertEqual(before['plan_sha256'],after['plan_sha256'])
            self.assertEqual(before['semantic_sha256'],after['semantic_sha256'])
            self.assertNotEqual(before['semantic_sha256'],before['source_sha256'])

    def test_cp15_11_dry_run_audit_no_writes(self):
        for row in self.cases:
            self.assertIs(row['preview_written'],False)
            self.assertGreater(row['audit_changed_fields'],0)

    def test_cp15_12_repeated_snapshot_digest_frozen(self):
        self.assertEqual(self.digests,[REFERENCE_DIGEST,REFERENCE_DIGEST])
        self.assertEqual(self.snapshots[0],self.snapshots[1])
        self.assertEqual(self.snapshots[0]['cases'],self.cases)

    def test_cp15_13_cp12_cp13_cp14_and_released_test_inventory(self):
        loader=unittest.defaultTestLoader
        for name in ('tests.test_v09510_preview_apply_parity_hardening',
                     'tests.test_v09510_determinism_certification',
                     'tests.test_v09510_performance_hardening'):
            self.assertEqual(loader.loadTestsFromName(name).countTestCases(),14)
        modules=('tests.test_v0956_smart_material_draft',
                 'tests.test_v0957_smart_material_preview_bridge',
                 'tests.test_v0958_smart_material_apply_integration',
                 'tests.test_v0959_smart_material_appearance')
        total=sum(loader.loadTestsFromName(m).countTestCases() for m in modules)
        self.assertEqual(total,113)

    def test_cp15_14_public_root_api_and_synthetic_boundary(self):
        import mmd_registry
        from tests.test_v09510_preview_apply_parity_hardening import _source
        self.assertEqual(mmd_registry.__version__,'0.9.5.9')
        self.assertEqual(mmd_registry.__all__,('__version__',))
        self.assertFalse(os.environ.get('MMD_REGISTRY_PRIVATE_PMX'))
        self.assertEqual(set(self.keyed),{(s,c) for s in ('single','multi') for c in CAPABILITIES})
        for shape in ('single','multi'):
            self.assertEqual(hashlib.sha256(_source(shape)).hexdigest(),REFERENCE[shape])


if __name__=='__main__':
    unittest.main()
