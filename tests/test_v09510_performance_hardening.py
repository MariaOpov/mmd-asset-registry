"""CP14 Performance Hardening: frozen synthetic observation and safety tests.

14 unittest methods: three catalog workloads, eight preview workloads,
measurement integrity, scale observations (no absolute time budget),
and immutable source/API/dry-run semantics.

The embedded benchmark only creates in-memory synthetic PMX and catalog data.
No Git/source/PMX writes are permitted by this test module.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import unittest

SIZES = (16, 64, 256)
REPEATS = 7
CAPABILITIES = ('material_color', 'transparency', 'material_specular', 'material_edge')
REF_SOURCE_SHA256 = {
    'single': '2445e393222357452dbdbc9f1d6ab16d501fc45c2c3cefa5583a3e9e9722bc8b',
    'multi': '682698fe99dff0588aa3cd58b7997fe477a71ad4af3fb34e789a4582a1894d9f',
}
# The bundled CP14 audit probe is injected below as an immutable Python string.
PROBE = "# CP14 PERFORMANCE BASELINE PROBE. NO FILE SYSTEM WRITES.\nimport gc\nimport hashlib\nimport io\nimport json\nimport statistics\nimport time\nimport tracemalloc\n\nfrom mmd_registry.services import _smart_inspection\nfrom mmd_registry.services._smart_material_draft import (\n    discover_smart_material_capability, group_smart_materials,\n)\nfrom mmd_registry.services.structural_authoring_catalog import PmxStructuralAuthoringMaterialCatalogEntry\nfrom mmd_registry.smart_parts import SmartPartKind\nfrom tests.test_v09510_preview_apply_parity_hardening import _source, _build\n\nSIZES=(16,64,256)\nREPEATS=7\nCAPABILITIES=('material_color','transparency','material_specular','material_edge')\n\n\ndef materials(n):\n    return tuple(PmxStructuralAuthoringMaterialCatalogEntry(\n        source_index=i,\n        local_name='Eyes' if i % 4 == 0 else 'UnrelatedMaterial',\n        universal_name='', texture_index=-1, sphere_texture_index=-1,\n        surface_index_count=0,\n    ) for i in range(n))\n\n\ndef analyze(entries):\n    result=_smart_inspection._analyze_entries(entries)\n    cap=discover_smart_material_capability(result,SmartPartKind.EYES)\n    group=group_smart_materials(result,SmartPartKind.EYES)\n    return cap,group\n\n\ndef median_millis(numbers):\n    return round(statistics.median(numbers)/1_000_000, 6)\n\n\ndef measure(fn, validator):\n    validator(fn()) # correctness before measuring; warmup deliberately excluded\n    samples=[]\n    for _ in range(REPEATS):\n        gc.collect()\n        start=time.perf_counter_ns()\n        value=fn()\n        samples.append(time.perf_counter_ns()-start)\n        validator(value)\n    gc.collect()\n    tracemalloc.start()\n    try:\n        tracemalloc.reset_peak()\n        validator(fn())\n        _,peak=tracemalloc.get_traced_memory()\n    finally:\n        tracemalloc.stop()\n    return {\n        'samples_ns':samples,\n        'median_ms':median_millis(samples),\n        'min_ms':round(min(samples)/1_000_000,6),\n        'max_ms':round(max(samples)/1_000_000,6),\n        'peak_alloc_bytes':peak,\n    }\n\nresult={'schema':'CP14_PERFORMANCE_BASELINE_V1','catalog':{},'pmx_pipeline':{},\n        'environment':{'repeats':REPEATS,'catalog_sizes':list(SIZES),\n        'capabilities':list(CAPABILITIES)},'all_correct':True}\n\nfor n in SIZES:\n    entries=materials(n)\n    expected=tuple(range(0,n,4))\n    def valid_catalog(value):\n        cap,group=value\n        assert cap.supported and cap.material_indices==expected\n        assert group.material_indices==expected\n        assert len({e.source_index for e in cap.evidence if e.source_kind.value=='material'})==len(expected)\n        assert tuple(e.source_index for e in cap.evidence if e.source_kind.value=='material') == expected\n    row=measure(lambda:analyze(entries),valid_catalog)\n    row['entry_count']=n\n    row['eyes_count']=len(expected)\n    result['catalog'][str(n)]=row\n\nfor mode in ('single','multi'):\n    source=_source(mode)\n    source_sha=hashlib.sha256(source).hexdigest()\n    expected_targets=(0,) if mode=='single' else (1,2)\n    for cap in CAPABILITIES:\n        def valid_pipeline(value):\n            draft,preview,confirmation=value\n            assert draft.expected_source_sha256==source_sha==preview.source_sha256\n            assert preview.plan_sha256==confirmation.plan_sha256\n            assert tuple(op.material_index for op in draft.operations)==expected_targets\n            assert preview.to_dict()['dry_run'] is True\n            assert preview.to_dict()['output']['written'] is False\n        row=measure(lambda:_build(source,cap),valid_pipeline)\n        row['source_sha256']=source_sha\n        row['target_count']=len(expected_targets)\n        result['pmx_pipeline'][mode+'_'+cap]=row\n\n# The source is in-memory only, and identity must be stable through benchmarking.\nassert len(result['catalog'])==len(SIZES)\nassert len(result['pmx_pipeline'])==8\nassert all(len(item['samples_ns'])==REPEATS for section in ('catalog','pmx_pipeline')\n           for item in result[section].values())\nassert all(item['peak_alloc_bytes'] >= 0 for section in ('catalog','pmx_pipeline')\n           for item in result[section].values())\ncanonical=json.dumps(result,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False)\nprint('CP14_BENCHMARK_JSON='+canonical)\nprint('CP14_BENCHMARK_SHA256='+hashlib.sha256(canonical.encode('utf-8')).hexdigest())\n"


class V09510PerformanceHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        env['PYTHONNOUSERSITE'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8:strict'
        p = subprocess.run(
            [sys.executable, '-B', '-c', PROBE],
            env=env, capture_output=True, text=True, encoding='utf-8',
            errors='strict', check=False, timeout=180,
        )
        if p.returncode != 0 or p.stderr.strip():
            raise AssertionError('CP14 synthetic benchmark subprocess failed: '
                                 + repr(p.stderr[-1200:]))
        lines = p.stdout.splitlines()
        if len(lines) != 2 or not lines[0].startswith('CP14_BENCHMARK_JSON=') or not lines[1].startswith('CP14_BENCHMARK_SHA256='):
            raise AssertionError('CP14 benchmark must produce exactly two canonical output lines')
        canonical = lines[0].split('=', 1)[1]
        observed_digest = lines[1].split('=', 1)[1]
        if not re.fullmatch(r'[a-f0-9]{64}', observed_digest):
            raise AssertionError('Invalid benchmark digest')
        if hashlib.sha256(canonical.encode('utf-8')).hexdigest() != observed_digest:
            raise AssertionError('Benchmark JSON digest mismatch')
        document = json.loads(canonical)
        if json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False) != canonical:
            raise AssertionError('Noncanonical benchmark JSON')
        cls.data = document
        cls.benchmark_digest = observed_digest
        cls.raw_benchmark_json = canonical

    def check_record(self, record):
        self.assertIs(type(record), dict)
        self.assertTrue({'samples_ns', 'min_ms', 'median_ms', 'max_ms', 'peak_alloc_bytes'}.issubset(record))
        samples = record['samples_ns']
        self.assertIs(type(samples), list)
        self.assertEqual(len(samples), REPEATS)
        for elapsed in samples:
            self.assertIs(type(elapsed), int)
            self.assertGreater(elapsed, 0)
        peak = record['peak_alloc_bytes']
        self.assertIs(type(peak), int)
        self.assertGreaterEqual(peak, 0)
        ordered = sorted(samples)
        for field in ('median_ms', 'min_ms', 'max_ms'):
            self.assertIs(type(record[field]), float)
            self.assertTrue(math.isfinite(record[field]))
            self.assertGreaterEqual(record[field], 0)
        self.assertEqual(record['min_ms'], round(ordered[0] / 1e6, 6))
        self.assertEqual(record['median_ms'], round(ordered[REPEATS // 2] / 1e6, 6))
        self.assertEqual(record['max_ms'], round(ordered[-1] / 1e6, 6))
        self.assertLessEqual(record['min_ms'], record['median_ms'])
        self.assertLessEqual(record['median_ms'], record['max_ms'])
        return samples

    def check_catalog(self, n):
        row = self.data['catalog'][str(n)]
        self.check_record(row)
        self.assertEqual(row['entry_count'], n)
        self.assertEqual(row['eyes_count'], n // 4)

    def check_pipeline(self, mode, capability):
        record = self.data['pmx_pipeline'][mode + '_' + capability]
        self.check_record(record)
        self.assertEqual(record['target_count'], 1 if mode == 'single' else 2)
        self.assertEqual(record['source_sha256'], REF_SOURCE_SHA256[mode])

    def test_cp14_01_catalog_16_entries(self):
        self.check_catalog(16)

    def test_cp14_02_catalog_64_entries(self):
        self.check_catalog(64)

    def test_cp14_03_catalog_256_entries(self):
        self.check_catalog(256)

    def test_cp14_04_single_material_color(self):
        self.check_pipeline('single', 'material_color')

    def test_cp14_05_single_transparency(self):
        self.check_pipeline('single', 'transparency')

    def test_cp14_06_single_material_specular(self):
        self.check_pipeline('single', 'material_specular')

    def test_cp14_07_single_material_edge(self):
        self.check_pipeline('single', 'material_edge')

    def test_cp14_08_multi_material_color(self):
        self.check_pipeline('multi', 'material_color')

    def test_cp14_09_multi_transparency(self):
        self.check_pipeline('multi', 'transparency')

    def test_cp14_10_multi_material_specular(self):
        self.check_pipeline('multi', 'material_specular')

    def test_cp14_11_multi_material_edge(self):
        self.check_pipeline('multi', 'material_edge')

    def test_cp14_12_seven_repeats_eleven_workloads_77_samples(self):
        self.assertEqual(set(self.data), {'schema', 'catalog', 'pmx_pipeline', 'environment', 'all_correct'})
        self.assertEqual(self.data['schema'], 'CP14_PERFORMANCE_BASELINE_V1')
        self.assertIs(self.data['all_correct'], True)
        self.assertEqual(self.data['environment'], {
            'repeats': REPEATS, 'catalog_sizes': list(SIZES),
            'capabilities': list(CAPABILITIES)})
        self.assertEqual(set(self.data['catalog']), {str(n) for n in SIZES})
        self.assertEqual(set(self.data['pmx_pipeline']), {
            mode + '_' + cap for mode in ('single', 'multi') for cap in CAPABILITIES})
        records = tuple(self.data['catalog'].values()) + tuple(self.data['pmx_pipeline'].values())
        self.assertEqual(len(records), 11)
        self.assertEqual(sum(len(self.check_record(row)) for row in records), 77)
        self.assertRegex(self.benchmark_digest, r'^[a-f0-9]{64}$')

    def test_cp14_13_scaling_and_reference_ratios_are_observations(self):
        catalog = self.data['catalog']
        # Scaling is recorded and finite; NO arbitrary latency or memory budget.
        for a, b in ((16,64), (64,256), (16,256)):
            lhs = catalog[str(a)]['median_ms']
            rhs = catalog[str(b)]['median_ms']
            ratio = rhs / lhs if lhs else float('nan')
            self.assertTrue(math.isfinite(ratio))
            self.assertGreater(ratio, 0)
        for cap in CAPABILITIES:
            single = self.data['pmx_pipeline']['single_' + cap]
            multi = self.data['pmx_pipeline']['multi_' + cap]
            ratio = multi['median_ms'] / single['median_ms'] if single['median_ms'] else float('nan')
            self.assertTrue(math.isfinite(ratio))
            self.assertGreater(ratio, 0)
            self.assertGreaterEqual(single['peak_alloc_bytes'], 0)
            self.assertGreaterEqual(multi['peak_alloc_bytes'], 0)
        # No accept/reject against CP14 read-only median baselines.

    def test_cp14_14_synthetic_dry_run_and_public_api_immutable(self):
        import mmd_registry
        from mmd_registry.pmx import serialize_pmx
        from tests.test_v09510_preview_apply_parity_hardening import _source, _build
        self.assertEqual(mmd_registry.__version__, '0.9.5.9')
        self.assertEqual(mmd_registry.__all__, ('__version__',))
        for mode in ('single', 'multi'):
            source = _source(mode)
            expected_sha = REF_SOURCE_SHA256[mode]
            self.assertEqual(hashlib.sha256(source).hexdigest(), expected_sha)
            for cap in CAPABILITIES:
                with self.subTest(mode=mode, capability=cap):
                    first_draft, first_preview, first_confirm = _build(source, cap)
                    second_draft, second_preview, second_confirm = _build(source, cap)
                    self.assertEqual(first_draft.to_dict(), second_draft.to_dict())
                    self.assertEqual(first_preview.to_dict(), second_preview.to_dict())
                    self.assertEqual(first_confirm.plan_sha256, first_preview.plan_sha256)
                    self.assertEqual(second_confirm.plan_sha256, second_preview.plan_sha256)
                    self.assertEqual(first_draft.expected_source_sha256, expected_sha)
                    self.assertEqual(hashlib.sha256(serialize_pmx(first_preview.document)).hexdigest(),
                                     hashlib.sha256(serialize_pmx(second_preview.document)).hexdigest())
                    self.assertEqual(tuple(op.material_index for op in first_draft.operations),
                                     (0,) if mode == 'single' else (1, 2))
                    payload = first_preview.to_dict()
                    self.assertIs(payload['dry_run'], True)
                    self.assertEqual(payload['output'], {'sha256': None, 'written': False})
                    self.assertEqual(payload['verification'], {'input_unchanged': True, 'semantic': 'passed'})
            self.assertEqual(hashlib.sha256(source).hexdigest(), expected_sha)


if __name__ == '__main__':
    unittest.main()
