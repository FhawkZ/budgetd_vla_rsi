"""CPU-only contract tests for run_phone_coherent_pair.verify (stdlib unittest).

Synthetic temporary protocols only; never imports skills or starts processes.
Deployment modules are imported from the reviewed mirror scripts directory
(override with RSI_SCRIPTS_DIR).
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPTS = Path(os.environ.get('RSI_SCRIPTS_DIR', '/Users/liqz/.cache/budgetd-vla-rsi-sync/checkout/scripts'))
sys.path.insert(0, str(SCRIPTS)); sys.path.insert(0, str(HERE))
import run_phone_coherent_pair as pair  # noqa: E402


def h(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class VerifyContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); t = Path(self.tmp.name).resolve()
        self.runtime = t / 'runtime'; self.durable = t / 'outputs'; self.durable.mkdir()
        (self.runtime / 'weights').mkdir(parents=True)
        (self.runtime / 'weights/clip.pt').write_bytes(b'clip')
        src = {str(pair.SCRIPTS / n): h(pair.SCRIPTS / n) for n in pair.REQUIRED_SCRIPTS}
        src[str(pair.SELF)] = h(pair.SELF)
        for pkg in (pair.PKG_A, pair.PKG_B):
            d = self.runtime / 'vendor/frozen_skills' / pkg; d.mkdir(parents=True)
            for f in ('skills.py', 'perception.py'):
                (d / f).write_text(f'# {pkg} {f}\n'); src[str(d / f)] = h(d / f)
        self.extra = t / 'extra_source.py'; self.extra.write_text('x = 1\n'); src[str(self.extra)] = h(self.extra)
        cases = []
        for i, (skill, seed) in enumerate([(pair.PKG_A, 1), (pair.PKG_B, 1), (pair.PKG_B, 2), (pair.PKG_A, 2)]):
            cfg = {'id': f'phone-case-{i}', 'status': 'FROZEN', 'attempts_max': 1, 'qwen_max': 0, 'vla_max': 0,
                   'denoiser': 'none', 'vendor': 'vendor', 'native': 'native', 'clip_weight': 'weights/clip.pt',
                   'clip_sha256': h(self.runtime / 'weights/clip.pt'), 'limits': dict(pair.V2_LIMITS),
                   'monitor': {}, 'task_cards': {pair.TASK: {}}, 'source_files': {},
                   'cases': [{'task': pair.TASK, 'skill': skill, 'seed': seed}]}
            p = t / f'case-{i}.json'; p.write_text(json.dumps(cfg))
            cases.append({'task': pair.TASK, 'skill': skill, 'seed': seed, 'protocol': str(p), 'sha256': h(p)})
        self.c = {'status': 'FROZEN_PHONE_PAIR', 'gpu': 3, 'task': pair.TASK,
                  'packages': {'A': pair.PKG_A, 'B': pair.PKG_B}, 'attempts_max': 4, 'qwen_max': 0, 'vla_max': 0,
                  'process_wall_seconds': 300, 'total_wall_seconds': 1320, 'expected_output_bytes': 268435456,
                  'cases': cases, 'source_files': src, 'output': str(self.durable / 'phone-pair-run')}

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, c):
        return pair.verify(c, self.runtime, output_root=self.durable)

    def rejects(self, c):
        with self.assertRaises((pair.ContractError, KeyError, TypeError, OSError, ValueError)):
            self.check(c)

    def test_valid_pair_accepted(self):
        self.assertEqual(len(self.check(self.c)), 4)

    def test_wrong_order_rejected(self):
        c = copy.deepcopy(self.c); c['cases'][0], c['cases'][1] = c['cases'][1], c['cases'][0]
        self.rejects(c)
        c = copy.deepcopy(self.c); c['cases'] = c['cases'][2:] + c['cases'][:2]
        self.rejects(c)

    def test_wrong_seeds_rejected(self):
        c = copy.deepcopy(self.c)
        for x in c['cases']: x['seed'] = 1
        self.rejects(c)
        c = copy.deepcopy(self.c); c['cases'][1]['seed'] = 3
        self.rejects(c)

    def test_case_protocol_content_must_match(self):
        c = copy.deepcopy(self.c); p = Path(c['cases'][0]['protocol'])
        cfg = json.loads(p.read_text()); cfg['cases'][0]['seed'] = 7; p.write_text(json.dumps(cfg))
        c['cases'][0]['sha256'] = h(p)
        self.rejects(c)

    def test_illegal_budgets_rejected(self):
        for k, v in [('attempts_max', 5), ('qwen_max', 1), ('vla_max', 1), ('process_wall_seconds', 600),
                     ('total_wall_seconds', 1321), ('expected_output_bytes', 1), ('gpu', 0), ('gpu', 1),
                     ('status', 'FROZEN_DEPLOYMENT_PAIR'), ('attempts_max', 4.0)]:
            with self.subTest(k=k, v=v):
                c = copy.deepcopy(self.c); c[k] = v; self.rejects(c)

    def test_non_durable_output_rejected(self):
        for o in ['/tmp/phone-pair-run', str(self.durable / 'a/b'), str(self.durable),
                  str(self.durable / '..' / 'escape'), 'relative/out']:
            with self.subTest(o=o):
                c = copy.deepcopy(self.c); c['output'] = o; self.rejects(c)

    def test_source_hash_change_rejected(self):
        self.check(self.c)
        self.extra.write_text('x = 2\n')
        self.rejects(self.c)

    def test_case_protocol_hash_change_rejected(self):
        c = copy.deepcopy(self.c); Path(c['cases'][2]['protocol']).write_text('{}')
        self.rejects(c)

    def test_missing_required_source_rejected(self):
        c = copy.deepcopy(self.c); del c['source_files'][str(pair.CASE_RUNNER)]
        self.rejects(c)


if __name__ == '__main__':
    unittest.main()
