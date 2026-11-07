"""Synthetic interface tests for skill_rsi_atom_program (fake backend; no robots/models/GPU)."""
import copy, os, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_rsi_atom_program as M

PKG = 'a' * 64
CONTRACT = {'package_id': 'pkgA', 'package_digest': PKG, 'atoms': {
    'probe': {'args': {'mode': {'type': 'enum', 'values': ['a', 'b']}},
              'result': {'ready': 'bool', 'level': 'int', 'info.gain': 'number'}},
    'act': {'args': {'amount': {'type': 'number'}}, 'result': {'ok': 'bool'}}}}


def oc(limits=None):
    return M.OwnerContract(CONTRACT, limits)


def prog(c, nodes, entry='n0', **over):
    p = {'version': 1, 'package_id': 'pkgA', 'package_digest': PKG, 'contract_digest': c.sha,
         'entry': entry, 'nodes': nodes}
    p.update(over)
    return p


def probe(nxt, mode='a'):
    return {'op': 'call', 'atom': 'probe', 'args': {'mode': {'lit': mode}}, 'next': nxt}


def eq(path, lit, yes, no, unk, node='p'):
    return {'op': 'branch', 'left': {'ref': {'node': node, 'path': path}}, 'right': {'lit': lit},
            'yes': yes, 'no': no, 'unknown': unk}


def stop(s):
    return {'op': 'stop', 'status': s}


class Backend:
    """Finite stateful fake: ready after ready_after probes; secret_score is a hidden field."""
    def __init__(self, ready_after=1, omit_ready=False, fail_on=None):
        self.n, self.ra, self.omit, self.fail, self.log = 0, ready_after, omit_ready, fail_on, []

    def dispatch(self, atom, args):
        self.log.append(atom)
        if atom == self.fail:
            raise RuntimeError('boom')
        if atom == 'probe':
            self.n += 1
            r = {'level': self.n, 'secret_score': 0.99, 'info': {'gain': 0.5, 'hidden': 1}}
            if not self.omit:
                r['ready'] = self.n >= self.ra
            return r
        return {'ok': True, 'secret_score': 1.0}


def prog_a(c):  # probe; ready==true -> done, else act -> abstain; unknown -> abstain
    return prog(c, {
        'p': probe('b'), 'b': eq('ready', True, 'ok', 'act', 'ab'),
        'act': {'op': 'call', 'atom': 'act', 'args': {'amount': {'ref': {'node': 'p', 'path': 'level'}}}, 'next': 'ab'},
        'ok': stop('done'), 'ab': stop('abstain')}, entry='p')


class T(unittest.TestCase):
    def setUp(self):
        self.c = oc()

    def run_p(self, p, be):
        return M.AtomProgram(p, self.c).run(be.dispatch)

    def test_reuse_two_fresh_runs_and_changed_program(self):
        ap = M.AtomProgram(prog_a(self.c), self.c)
        b1, b2 = Backend(1), Backend(99)
        r1, r2 = ap.run(b1.dispatch), ap.run(b2.dispatch)
        self.assertEqual((b1.log, r1['terminal']), (['probe'], 'stop:done'))
        self.assertEqual((b2.log, r2['terminal']), (['probe', 'act'], 'stop:abstain'))
        self.assertEqual(r1['program_sha'], r2['program_sha'])
        changed = prog_a(self.c)  # now branch on level==3 : different call path from same backend
        changed['nodes']['b'] = eq('level', 3, 'ok', 'act', 'ab')
        b3 = Backend(1)
        self.assertEqual(self.run_p(changed, b3)['terminal'], 'stop:abstain')
        self.assertEqual(b3.log, ['probe', 'act'])
        self.assertNotEqual(M.AtomProgram(changed, self.c).sha, ap.sha)
        self.assertFalse(r1['accepted'] or r1['rollout_authorized'])

    def test_unknown_edge_and_missing_never_defaulted(self):
        r = self.run_p(prog_a(self.c), Backend(omit_ready=True))
        br = [e for e in r['trace'] if e['ev'] == 'branch'][0]
        self.assertEqual((br['edge'], br['missing']), ('unknown', True))

    def test_hidden_return_dropped_and_undeclared_ref_rejected(self):
        r = self.run_p(prog_a(self.c), Backend(1))
        res = [e for e in r['trace'] if e['ev'] == 'result'][0]
        self.assertNotIn('secret_score', str(r['trace']))
        self.assertEqual(set(res['values']), {'ready', 'level', 'info.gain'})
        p = prog_a(self.c)
        p['nodes']['b'] = eq('secret_score', 0.99, 'ok', 'act', 'ab')
        with self.assertRaises(M.ProgramError):
            M.AtomProgram(p, self.c)

    def test_typed_binding_and_bool_not_number(self):
        p = prog_a(self.c)
        p['nodes']['act']['args']['amount'] = {'ref': {'node': 'p', 'path': 'ready'}}  # bool -> number
        with self.assertRaises(M.ProgramError):
            M.AtomProgram(p, self.c)
        p = prog_a(self.c)
        p['nodes']['act']['args']['amount'] = {'lit': True}
        with self.assertRaises(M.ProgramError):
            M.AtomProgram(p, self.c)
        p = prog_a(self.c)
        p['nodes']['b'] = eq('ready', 1, 'ok', 'act', 'ab')  # bool vs int
        with self.assertRaises(M.ProgramError):
            M.AtomProgram(p, self.c)

    def test_rejections_before_any_action(self):
        bad = []
        def mut(f):
            p = prog_a(self.c); f(p); bad.append(p)
        mut(lambda p: p.update(package_id='other'))
        mut(lambda p: p.update(package_digest='b' * 64))
        mut(lambda p: p.update(contract_digest='c' * 64))
        mut(lambda p: p.update(extra=1))
        mut(lambda p: p['nodes']['p'].update(atom='scorer'))
        mut(lambda p: p['nodes']['p'].update(rawargs={'x': 1}))
        mut(lambda p: p['nodes']['p']['args'].update(extra={'lit': 1}))
        mut(lambda p: p['nodes']['p']['args'].update(mode={'lit': 'zzz'}))
        mut(lambda p: p['nodes']['p'].update(next='nowhere'))
        mut(lambda p: p.update(entry='nowhere'))
        mut(lambda p: p['nodes']['ok'].update(op='code'))
        mut(lambda p: p['nodes']['act']['args'].update(amount={'lit': float('nan')}))
        mut(lambda p: p['nodes']['act']['args'].update(amount={'lit': float('inf')}))
        mut(lambda p: p['nodes']['act']['args'].update(amount={'ref': {'node': 'ok', 'path': 'x'}}))
        mut(lambda p: p['nodes']['act']['args'].update(amount={'lit': [1]}))
        for p in bad:
            with self.assertRaises((M.ProgramError, ValueError)):
                M.AtomProgram(p, self.c)
        with self.assertRaises(M.ProgramError):
            M.strict_loads('{"a":NaN}')
        with self.assertRaises(M.ProgramError):
            M.strict_loads('{"a":1,"a":2}')

    def test_size_and_node_bounds(self):
        small = oc(M.Limits(max_nodes=2))
        p = prog_a(small)
        with self.assertRaises(M.ProgramError):
            M.AtomProgram(p, small)
        tiny = oc(M.Limits(max_bytes=50))
        with self.assertRaises(M.ProgramError):
            M.AtomProgram(prog_a(tiny), tiny)

    def test_missing_binding_refuses_before_call(self):
        p = prog(self.c, {'act': {'op': 'call', 'atom': 'act', 'args': {'amount': {'ref': {'node': 'p', 'path': 'level'}}},
                                  'next': 'p'}, 'p': probe('s'), 's': stop('done')}, entry='act')
        be = Backend()
        r = self.run_p(p, be)
        self.assertEqual((r['terminal'], be.log, r['attempts']), ('refused:missing_binding', [], 0))

    def test_cycle_attempt_budget_counts_before_dispatch(self):
        c = oc(M.Limits(max_attempts=3))
        p = prog(c, {'p': probe('b'), 'b': eq('ready', True, 's', 'p', 'p'), 's': stop('done')}, entry='p')
        be = Backend(ready_after=10 ** 6)
        r = M.AtomProgram(p, c).run(be.dispatch)
        self.assertEqual((r['terminal'], len(be.log), r['attempts']), ('budget:attempts', 3, 3))
        c2 = oc(M.Limits(max_transitions=5))  # transitions bound with no calls
        p2 = prog(c2, {'p': probe('b'), 'b': eq('ready', True, 's', 'p', 'p'), 's': stop('done')}, entry='p')
        r2 = M.AtomProgram(p2, c2).run(Backend(10 ** 6).dispatch)
        self.assertEqual(r2['terminal'], 'budget:transitions')

    def test_exception_stops_without_retry(self):
        be = Backend(fail_on='probe')
        r = self.run_p(prog_a(self.c), be)
        self.assertEqual((r['terminal'], be.log, r['attempts']), ('exception', ['probe'], 1))

    def test_native_signature_adapter(self):
        seen = []
        ns = {'probe': lambda api, args: seen.append((api, args)) or {'ready': True, 'level': 1},
              'evil': lambda api, args: 1 / 0}
        d = M.native_dispatch(self.c, ns, 'API')
        r = M.AtomProgram(prog_a(self.c), self.c).run(d)
        self.assertEqual((r['terminal'], seen), ('stop:done', [('API', {'mode': 'a'})]))
        with self.assertRaises(M.ProgramError):
            d('evil', {})

    def test_artifact_roundtrip_and_tamper(self):
        ap = M.AtomProgram(prog_a(self.c), self.c)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'h.json')
            M.save_program(path, ap)
            with self.assertRaises(FileExistsError):
                M.save_program(path, ap)
            ld = M.load_program(path, self.c)
            self.assertEqual(ld.sha, ap.sha)
            raw = Path(path).read_text()
            def put(name, s):
                q = os.path.join(td, name); Path(q).write_text(s); return q
            tampers = [raw.replace('"abstain"', '"done"', 1), raw.replace('false', 'true', 1),
                       raw.replace(self.c.sha, 'd' * 64), raw[:-5]]
            for i, t in enumerate(tampers):
                with self.assertRaises((M.ProgramError, ValueError)):
                    M.load_program(put('t%d.json' % i, t), self.c)
            other = M.OwnerContract(dict(CONTRACT, package_digest='e' * 64))
            with self.assertRaises(M.ProgramError):
                M.load_program(path, other)

    def test_frozen_copy_and_run_state_reset(self):
        src = prog_a(self.c)
        ap = M.AtomProgram(src, self.c)
        src['nodes']['b'] = eq('level', 3, 'ok', 'act', 'ab')  # mutating source can't alter frozen
        ap.program['nodes']['ok'] = None
        self.assertEqual(ap.sha, M.AtomProgram(prog_a(self.c), self.c).sha)
        # unknown-first program: branch before any probe; second run must also start unknown
        p = prog(self.c, {'b': eq('ready', True, 'ok', 'ab', 'p'), 'p': probe('b'),
                          'ok': stop('done'), 'ab': stop('abstain')}, entry='b')
        a2 = M.AtomProgram(p, self.c)
        for _ in range(2):
            r = a2.run(Backend(1).dispatch)
            edges = [e['edge'] for e in r['trace'] if e['ev'] == 'branch']
            self.assertEqual(edges, ['unknown', 'yes'])
        self.assertEqual(r['program_sha'], a2.sha)

    def test_declared_number_int_float_equality(self):
        p = prog_a(self.c)
        p['nodes']['b'] = eq('info.gain', 1.0, 'ok', 'act', 'ab')
        r = M.AtomProgram(p, self.c).run(lambda a, args: {'info': {'gain': 1}})
        self.assertEqual(r['terminal'], 'stop:done')
        bad = M.AtomProgram(p, self.c).run(lambda a, args: {'info': {'gain': True}})
        self.assertEqual(bad['terminal'], 'stop:abstain')
        self.assertEqual([e['edge'] for e in bad['trace'] if e['ev']=='branch'], ['unknown'])

    def test_owner_contract_snapshot(self):
        c = oc()
        ap = M.AtomProgram(prog_a(c), c)
        c.atoms['probe']['result']['ready'] = 'number'
        c.data['package_id'] = 'changed'
        self.assertEqual(ap.run(Backend(1).dispatch)['terminal'], 'stop:done')
        self.assertEqual(ap.contract.package_id, 'pkgA')

    def test_owner_limit_types(self):
        for v in (True, 0, -1, 1.5, '2', float('inf')):
            with self.assertRaises(M.ProgramError): M.Limits(max_attempts=v)

    def test_fast(self):
        t = time.time(); self.run_p(prog_a(self.c), Backend()); self.assertLess(time.time() - t, 1)


if __name__ == '__main__':
    unittest.main()
