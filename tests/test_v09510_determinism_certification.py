"""CP13 frozen determinism certification; synthetic PMX, no repo edits.

One subprocess per hash-seed/repetition, two runs per seed. All 14 tests
compare exact content/plan/preview/audit/semantic projections and fail closed
on errors. Never accesses private PMX or any writer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

SEEDS = ('0', '1', '2', '42', '31337')
FROZEN_SNAPSHOT_SHA256 = 'c8459b36e6d45428ac8c08423cb117a30843498503f0cd12b50f8f339d216412'
CAPABILITIES = ('material_color','transparency','material_specular','material_edge')
SUPPORTED_FIXTURES = ('single','multi_japanese_english','duplicate_names','unicode_fullwidth')
EXPECTED_FIXTURES = SUPPORTED_FIXTURES + ('unnamed',)
FIELD_CONTRACT = {
    'material_color': ('diffuse',),
    'transparency': ('diffuse',),
    'material_specular': ('specular','specular_strength'),
    'material_edge': ('edge_color','edge_scale'),
}
PROBE = "import hashlib, io, json\nfrom dataclasses import replace\nfrom mmd_registry.pmx import load_pmx, serialize_pmx\nfrom mmd_registry.services import _smart_inspection\nfrom mmd_registry.services._smart_material_draft import discover_smart_material_capability, SmartMaterialDraftError\nfrom mmd_registry.diagnostics import PmxServiceError\nfrom mmd_registry.services.structural_authoring_catalog import PmxStructuralAuthoringMaterialCatalogEntry\nfrom mmd_registry.smart_parts import SmartPart, SmartPartKind, SmartPartEvidence, SmartPartEvidenceKind\nfrom tests.test_v09510_preview_apply_parity_hardening import _source, _build, INTENTS\n\n# Data only: no filesystem writes and no private PMX.\nsource_multi = _source('multi')\ndoc = load_pmx(io.BytesIO(source_multi))\n\ndef renamed(names):\n    assert len(names) == len(doc.materials)\n    new_doc = replace(doc, materials=tuple(\n        replace(mat, local_name=label) for mat, label in zip(doc.materials, names)))\n    data = serialize_pmx(new_doc)\n    assert load_pmx(io.BytesIO(data)) == new_doc\n    return data\n\nfixtures = {\n    'single': _source('single'),\n    'multi_japanese_english': source_multi,\n    'duplicate_names': renamed(('Hair', 'Eyes', 'Eyes')),\n    'unicode_fullwidth': renamed(('髪', '瞳', 'Ｅｙｅｓ')),\n    'unnamed': renamed(('Hair', '', '')),\n}\n\nsnapshot = {'fixture_cases': {}, 'canonical_evidence': {}}\nfor fixture_name, source in fixtures.items():\n    result = {'source_sha256': hashlib.sha256(source).hexdigest(), 'capabilities': {}}\n    for capability in ('material_color', 'transparency', 'material_specular', 'material_edge'):\n        try:\n            draft, preview, confirm = _build(source, capability)\n            before_doc = load_pmx(io.BytesIO(source))\n            assert draft.expected_source_sha256 == result['source_sha256'] == preview.source_sha256\n            assert preview.plan_sha256 == confirm.plan_sha256\n            assert all(op.material_index < len(before_doc.materials) for op in draft.operations)\n            result['capabilities'][capability] = {\n                'status': 'supported',\n                'indices': [op.material_index for op in draft.operations],\n                'plan_sha256': preview.plan_sha256,\n                'plan': draft.to_dict(),\n                'preview': preview.to_dict(),\n                'semantic_sha256': hashlib.sha256(serialize_pmx(preview.document)).hexdigest(),\n            }\n        except (SmartMaterialDraftError, PmxServiceError) as error:\n            result['capabilities'][capability] = {\n                'status': 'blocked', 'exception_type': type(error).__name__,\n                'reason': getattr(error, 'reason', None),\n            }\n    snapshot['fixture_cases'][fixture_name] = result\n\nassert all(v['status'] == 'supported' for v in snapshot['fixture_cases']['multi_japanese_english']['capabilities'].values())\nassert all(v['status'] == 'supported' for v in snapshot['fixture_cases']['single']['capabilities'].values())\nassert all(v['status'] == 'supported' for v in snapshot['fixture_cases']['duplicate_names']['capabilities'].values())\nassert all(v['status'] == 'blocked' for v in snapshot['fixture_cases']['unnamed']['capabilities'].values())\n\nentries = _smart_inspection._collect_semantic_entries(doc)\nmaterial_entries = tuple(x for x in entries if isinstance(x, PmxStructuralAuthoringMaterialCatalogEntry))\nassert material_entries\nchosen = next(x for x in material_entries if x.local_name == 'Eyes')\n\ndef evidence_view(sequence):\n    cap = discover_smart_material_capability(_smart_inspection._analyze_entries(tuple(sequence)), SmartPartKind.EYES)\n    return {\n        'status': cap.status.value,\n        'reason': cap.reason,\n        'indices': list(cap.material_indices),\n        'evidence': [ [e.source_kind.value,e.source_index,e.reason] for e in cap.evidence ],\n    }\n\nviews = {\n    'ordered': evidence_view(entries),\n    'reversed': evidence_view(tuple(reversed(entries))),\n    'duplicate_equivalent': evidence_view(entries + (chosen,)),\n}\nassert views['ordered'] == views['reversed'], 'reversed evidence changed Smart material semantics'\nassert views['ordered'] == views['duplicate_equivalent'], 'duplicate equivalent catalog evidence changed Smart material semantics'\nsnapshot['canonical_evidence']['catalog_permutations'] = views\n\nfirst = SmartPartEvidence(SmartPartEvidenceKind.MATERIAL,1,'exact_name_alias:eyes')\nsecond = SmartPartEvidence(SmartPartEvidenceKind.MATERIAL,2,'exact_name_alias:eyes')\nassert SmartPart(SmartPartKind.EYES,(first,second)).evidence == SmartPart(SmartPartKind.EYES,(second,first)).evidence\ntry:\n    SmartPart(SmartPartKind.EYES,(first,first))\nexcept ValueError:\n    snapshot['canonical_evidence']['direct_duplicate_evidence'] = 'rejected'\nelse:\n    raise AssertionError('duplicate direct SmartPart evidence was accepted')\nsnapshot['canonical_evidence']['direct_reversed_evidence'] = 'equal'\n\ncanonical = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)\nprint('CP13_SNAPSHOT_JSON=' + canonical)\nprint('CP13_SNAPSHOT_SHA256=' + hashlib.sha256(canonical.encode('utf-8')).hexdigest())\n"


def _snapshot_in_seed(seed: str):
    if seed not in SEEDS:
        raise ValueError('Unknown seed')
    env = os.environ.copy()
    env['PYTHONHASHSEED'] = seed
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8:strict'
    proc = subprocess.run(
        [sys.executable, '-B', '-c', PROBE], cwd=Path(__file__).resolve().parents[1],
        env=env, capture_output=True, text=True, encoding='utf-8', errors='strict',
        timeout=90, check=False,
    )
    if proc.returncode != 0:
        raise AssertionError('snapshot subprocess failed for seed '+seed+' rc='+str(proc.returncode)+': '+proc.stderr[-3000:])
    lines = proc.stdout.splitlines()
    json_lines = [line[len('CP13_SNAPSHOT_JSON='):] for line in lines if line.startswith('CP13_SNAPSHOT_JSON=')]
    sha_lines = [line[len('CP13_SNAPSHOT_SHA256='):] for line in lines if line.startswith('CP13_SNAPSHOT_SHA256=')]
    if len(lines) != 2 or len(json_lines) != 1 or len(sha_lines) != 1:
        raise AssertionError('Snapshot has missing/duplicate/unexpected lines')
    raw, digest = json_lines[0], sha_lines[0]
    obj = json.loads(raw)
    normalized = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if raw != normalized or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise AssertionError('Snapshot canonical JSON or SHA representation invalid')
    if hashlib.sha256(raw.encode('utf-8')).hexdigest() != digest:
        raise AssertionError('Snapshot SHA does not match JSON payload')
    if digest != FROZEN_SNAPSHOT_SHA256:
        raise AssertionError('Snapshot drift: '+digest)
    if set(obj) != {'fixture_cases', 'canonical_evidence'}:
        raise AssertionError('Snapshot structure drift')
    return digest, obj


class V09510DeterminismCertificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Test-only subprocesses: no production file mutation or output files.
        cls.snapshots = {seed: tuple(_snapshot_in_seed(seed) for _ in range(2)) for seed in SEEDS}
        cls.reference = cls.snapshots['0'][0][1]

    def _seed(self, seed):
        self.assertEqual(self.snapshots[seed][0][0], FROZEN_SNAPSHOT_SHA256)
        self.assertEqual(self.snapshots[seed][0][1], self.reference)

    def test_cp13_01_seed_0_frozen_baseline(self):
        self._seed('0')

    def test_cp13_02_seed_1_identical_semantics(self):
        self._seed('1')

    def test_cp13_03_seed_2_identical_semantics(self):
        self._seed('2')

    def test_cp13_04_seed_42_identical_semantics(self):
        self._seed('42')

    def test_cp13_05_seed_31337_identical_semantics(self):
        self._seed('31337')

    def test_cp13_06_two_runs_per_seed_bitwise_canonical(self):
        self.assertEqual(set(self.snapshots), set(SEEDS))
        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.assertEqual(len(self.snapshots[seed]), 2)
                self.assertEqual(self.snapshots[seed][0], self.snapshots[seed][1])
                self.assertEqual(self.snapshots[seed][1][1], self.reference)

    def test_cp13_07_unicode_japanese_fullwidth_exact_targets(self):
        fx = self.reference['fixture_cases']['unicode_fullwidth']
        self.assertEqual(fx['source_sha256'], '0c6519a6484204485f4094c0029e781dc4ee3e08a6619b1661b66586f824379f')
        for capability in CAPABILITIES:
            with self.subTest(capability=capability):
                obj = fx['capabilities'][capability]
                self.assertEqual(obj['status'], 'supported')
                self.assertEqual(obj['indices'], [1,2])
                self.assertEqual([x['target_name'] for x in obj['preview']['audit']['changes']][::len(FIELD_CONTRACT[capability])], ['瞳','Ｅｙｅｓ'])

    def test_cp13_08_duplicate_names_retained_as_distinct_source_indices(self):
        fx = self.reference['fixture_cases']['duplicate_names']
        for cap in CAPABILITIES:
            with self.subTest(cap=cap):
                obj = fx['capabilities'][cap]
                self.assertEqual(obj['status'], 'supported')
                self.assertEqual(obj['indices'], [1,2])
                self.assertEqual([op['material_index'] for op in obj['plan']['operations']], [1,2])
                self.assertEqual({c['target_name'] for c in obj['preview']['audit']['changes']},{'Eyes'})

    def test_cp13_09_unnamed_all_capabilities_fail_closed(self):
        fx = self.reference['fixture_cases']['unnamed']['capabilities']
        self.assertEqual(set(fx), set(CAPABILITIES))
        for cap in CAPABILITIES:
            with self.subTest(cap=cap):
                self.assertEqual(fx[cap]['status'], 'blocked')
                self.assertEqual(fx[cap]['exception_type'], 'SmartMaterialDraftError')
                self.assertEqual(fx[cap]['reason'], 'unsupported_material_color' if cap=='material_color' else 'unsupported_appearance_capability')

    def test_cp13_10_single_multi_target_stable_exact_identities(self):
        cases = self.reference['fixture_cases']
        self.assertEqual(set(cases),set(EXPECTED_FIXTURES))
        for fixture, targets in [('single',[0]),('multi_japanese_english',[1,2])]:
            for cap in CAPABILITIES:
                with self.subTest(fixture=fixture,cap=cap):
                    item=cases[fixture]['capabilities'][cap]
                    self.assertEqual(item['indices'],targets)
                    self.assertEqual([op['material_index'] for op in item['plan']['operations']],targets)
                    self.assertEqual(sorted(set(item['indices'])),targets)

    def test_cp13_11_reversed_catalog_evidence_same_canonical_projection(self):
        views=self.reference['canonical_evidence']['catalog_permutations']
        self.assertEqual(views['ordered'],views['reversed'])
        self.assertEqual(views['ordered']['indices'],[1,2])
        self.assertEqual(views['ordered']['status'],'supported')
        self.assertEqual([x[1] for x in views['ordered']['evidence']], [1,2])
        self.assertEqual(self.reference['canonical_evidence']['direct_reversed_evidence'],'equal')

    def test_cp13_12_equivalent_duplicate_catalog_dedup_direct_duplicate_rejected(self):
        canonical=self.reference['canonical_evidence']
        views=canonical['catalog_permutations']
        self.assertEqual(views['ordered'],views['duplicate_equivalent'])
        self.assertEqual(len(views['ordered']['evidence']),2)
        self.assertEqual(len({tuple(x) for x in views['ordered']['evidence']}),2)
        self.assertEqual(canonical['direct_duplicate_evidence'],'rejected')

    def test_cp13_13_four_capability_plan_preview_audit_fields_deterministic(self):
        for fixture in SUPPORTED_FIXTURES:
            fx=self.reference['fixture_cases'][fixture]
            for cap in CAPABILITIES:
                with self.subTest(fixture=fixture,cap=cap):
                    item=fx['capabilities'][cap]
                    self.assertEqual(item['status'],'supported')
                    plan=item['plan']; preview=item['preview']
                    self.assertEqual(plan['expected_source_sha256'],fx['source_sha256'])
                    self.assertEqual(preview['source']['sha256'],fx['source_sha256'])
                    self.assertEqual(preview['plan']['sha256'],item['plan_sha256'])
                    self.assertEqual(preview['plan']['operation_count'],len(plan['operations']))
                    self.assertEqual(preview['status'],'changes_pending')
                    changes=preview['audit']['changes']
                    expected_fields=set(FIELD_CONTRACT[cap])
                    self.assertEqual({ch['field_path'].rsplit('.',1)[-1] for ch in changes},expected_fields)
                    self.assertEqual({ch['target_index'] for ch in changes},set(item['indices']))
                    self.assertEqual([ch['operation_index'] for ch in changes], sorted(ch['operation_index'] for ch in changes))
                    self.assertEqual(preview['audit']['summary']['changed_fields'],len(changes))
                    self.assertEqual(preview['audit']['summary']['material_fields'],len(changes))
                    self.assertEqual(preview['audit']['summary']['model_fields'],0)
                    self.assertEqual(preview['audit']['summary']['texture_fields'],0)

    def test_cp13_14_semantic_preview_nonwriting_public_root_api_frozen(self):
        import mmd_registry
        self.assertEqual(mmd_registry.__version__,'0.9.5.11')
        self.assertEqual(mmd_registry.__all__,('__version__',))
        for fixture in SUPPORTED_FIXTURES:
            for cap in CAPABILITIES:
                with self.subTest(fixture=fixture,cap=cap):
                    item=self.reference['fixture_cases'][fixture]['capabilities'][cap]
                    preview=item['preview']
                    self.assertRegex(item['semantic_sha256'],r'^[0-9a-f]{64}$')
                    self.assertTrue(preview['dry_run'])
                    self.assertEqual(preview['output'],{'sha256':None,'written':False})
                    self.assertEqual(preview['verification'],{'input_unchanged':True,'semantic':'passed'})
                    self.assertRegex(item['plan_sha256'],r'^[0-9a-f]{64}$')
                    self.assertEqual(set(op['op'] for op in item['plan']['operations']),{'update_material'})


if __name__ == '__main__':
    unittest.main()
