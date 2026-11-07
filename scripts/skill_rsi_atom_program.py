"""Persistent typed JSON atom-program interpreter (CPU, stdlib only).

Not generated Python, not a sandbox, not an upstream-loop reproduction. A program is
strict JSON that a trusted owner-supplied OwnerContract constrains.

Program schema (version 1; every key below is required, unknown keys reject):
  {"version":1,"package_id":S,"package_digest":HEX64,"contract_digest":HEX64,
   "entry":NODE,"nodes":{NODE: node}}
  node = {"op":"call","atom":A,"args":{ARG: operand},"next":NODE}
       | {"op":"branch","left":ref_operand,"right":operand,
          "yes":NODE,"no":NODE,"unknown":NODE}     # typed equality only
       | {"op":"stop","status":"done"|"abstain"}   # label only; never a success claim
  operand = {"lit": bool|int|float|str} | {"ref":{"node":CALL_NODE,"path":DECLARED_PATH}}

OwnerContract (trusted, never from the program):
  {"package_id":S,"package_digest":HEX64,
   "atoms":{A:{"args":{ARG:{"type":T,"values":[..enum only..]}},"result":{PATH:T}}}}
  T in bool|int|number|string|enum (enum is arg-only; results use string).
Only declared result paths survive projection; everything else is dropped before the
program can read it. Bounds (JSON bytes/depth/nodes/transitions/attempted atom calls)
are fixed by Limits, supplied by the owner, never by the program.

Semantics: a ref to a not-yet-bound value refuses a call before dispatch; in a branch it
takes the explicit "unknown" edge. Attempts are counted before dispatch; a dispatch
exception stops immediately (result unknown, no retry). LIMITATION: a blocking native
call cannot be interrupted by this code; a wall deadline needs a trusted supervisor.
Loading an artifact never executes anything and never grants acceptance/rollout.
"""
import copy, hashlib, json, math, os, re
from dataclasses import dataclass

HEX64 = re.compile(r'^[0-9a-f]{64}$')
NAME = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}$')
PATH = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,63}(\.[A-Za-z_][A-Za-z0-9_]{0,63}){0,3}$')
TYPES = ('bool', 'int', 'number', 'string')
MAX_STR = 256


class ProgramError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 65536
    max_depth: int = 8
    max_nodes: int = 64
    max_transitions: int = 200
    max_attempts: int = 20

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ProgramError('owner limits must be positive finite integers')


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def sha(obj):
    return hashlib.sha256(canon(obj).encode()).hexdigest()


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ProgramError('duplicate key ' + k)
        d[k] = v
    return d


def _bad_const(c):
    raise ProgramError('non-finite constant ' + c)


def strict_loads(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_bad_const)


def type_of(v):
    """Strict value type; bool is never int/number, nan/inf are untyped (None)."""
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, int):
        return 'int'
    if isinstance(v, float):
        return 'number' if math.isfinite(v) else None
    if isinstance(v, str) and len(v) <= MAX_STR:
        return 'string'
    return None


def fits(t, v):
    """Does value v satisfy declared type t (int is acceptable as number)."""
    vt = type_of(v)
    return vt == t or (t == 'number' and vt == 'int')


def _depth(o, d=1):
    if isinstance(o, dict):
        return max([_depth(v, d + 1) for v in o.values()] + [d])
    if isinstance(o, list):
        return max([_depth(v, d + 1) for v in o] + [d])
    return d


def _keys(d, required, where):
    if not isinstance(d, dict) or set(d) != set(required):
        raise ProgramError('bad keys in ' + where)


class OwnerContract:
    def __init__(self, contract, limits=None):
        c = json.loads(canon(contract))  # deep copy, finite, JSON-only
        _keys(c, ('package_id', 'package_digest', 'atoms'), 'contract')
        if not NAME.match(str(c['package_id'])) or not HEX64.match(str(c['package_digest'])):
            raise ProgramError('bad package id/digest')
        if not isinstance(c['atoms'], dict) or not c['atoms']:
            raise ProgramError('contract needs atoms')
        for a, spec in c['atoms'].items():
            _keys(spec, ('args', 'result'), 'atom ' + a)
            if not NAME.match(a):
                raise ProgramError('bad atom name')
            for n, s in spec['args'].items():
                t = s.get('type') if isinstance(s, dict) else None
                if not NAME.match(n) or t not in TYPES + ('enum',):
                    raise ProgramError('bad arg decl')
                if t == 'enum':
                    _keys(s, ('type', 'values'), 'enum')
                    if not s['values'] or any(type_of(x) != 'string' for x in s['values']):
                        raise ProgramError('bad enum')
                else:
                    _keys(s, ('type',), 'arg')
            for p, t in spec['result'].items():
                if not PATH.match(p) or t not in TYPES:
                    raise ProgramError('bad result decl')
        self.data, self.limits = c, limits or Limits()
        self.package_id, self.package_digest = c['package_id'], c['package_digest']
        self.atoms, self.sha = c['atoms'], sha(c)

    def project(self, atom, raw):
        """Keep only declared, correctly typed result paths (flat dotted dict)."""
        out, dropped = {}, []
        for p, t in self.atoms[atom]['result'].items():
            cur = raw
            for part in p.split('.'):
                cur = cur.get(part, _MISSING) if isinstance(cur, dict) else _MISSING
            if cur is _MISSING:
                continue
            if fits(t, cur):
                out[p] = cur
            else:
                dropped.append(p)
        return out, dropped


_MISSING = object()


class AtomProgram:
    """Validated, frozen (deep-copied) program bound to an owner contract."""

    def __init__(self, program, contract):
        if not isinstance(contract, OwnerContract):
            raise ProgramError('owner contract required')
        contract = OwnerContract(contract.data, contract.limits)  # snapshot owner state
        text = canon(program)  # rejects NaN/inf and non-JSON types
        if len(text.encode()) > contract.limits.max_bytes:
            raise ProgramError('program too large')
        p = strict_loads(text)
        if _depth(p) > contract.limits.max_depth:
            raise ProgramError('program too deep')
        self._validate(p, contract)
        self._p, self.contract, self.sha = p, contract, sha(p)

    @property
    def program(self):
        return copy.deepcopy(self._p)

    @staticmethod
    def _validate(p, c):
        _keys(p, ('version', 'package_id', 'package_digest', 'contract_digest', 'entry', 'nodes'), 'program')
        if p['version'] != 1 or type(p['version']) is not int:
            raise ProgramError('bad version')
        if (p['package_id'], p['package_digest'], p['contract_digest']) != (c.package_id, c.package_digest, c.sha):
            raise ProgramError('package/digest mismatch')
        nodes = p['nodes']
        if not isinstance(nodes, dict) or not 0 < len(nodes) <= c.limits.max_nodes or p['entry'] not in nodes:
            raise ProgramError('bad nodes/entry')
        if any(not NAME.match(n) for n in nodes):
            raise ProgramError('bad node id')

        def edge(n):
            if n not in nodes:
                raise ProgramError('bad edge ' + str(n))

        def operand(o, want=None):
            if not isinstance(o, dict) or len(o) != 1:
                raise ProgramError('bad operand')
            if 'lit' in o:
                t = type_of(o['lit'])
                if t is None:
                    raise ProgramError('bad literal')
            elif 'ref' in o:
                r = o['ref']
                _keys(r, ('node', 'path'), 'ref')
                n = nodes.get(r['node']) if isinstance(r['node'], str) else None
                if not n or n['op'] != 'call':
                    raise ProgramError('ref must target a call node')
                t = c.atoms[n['atom']]['result'].get(r['path'])
                if t is None:
                    raise ProgramError('undeclared result path')
            else:
                raise ProgramError('bad operand')
            return t

        for nid, n in nodes.items():  # call nodes first so refs can see 'atom'
            if not isinstance(n, dict) or n.get('op') not in ('call', 'branch', 'stop'):
                raise ProgramError('bad node op')
            if n['op'] == 'call':
                _keys(n, ('op', 'atom', 'args', 'next'), nid)
                if n['atom'] not in c.atoms:
                    raise ProgramError('atom not in owner contract')
        for nid, n in nodes.items():
            if n['op'] == 'call':
                decl = c.atoms[n['atom']]['args']
                if not isinstance(n['args'], dict) or set(n['args']) != set(decl):
                    raise ProgramError('args must match contract exactly')
                for a, o in n['args'].items():
                    t, d = operand(o), decl[a]
                    if d['type'] == 'enum':
                        ok = (t == 'string') and ('ref' in o or o['lit'] in d['values'])
                    else:
                        ok = t == d['type'] or (t == 'int' and d['type'] == 'number')
                    if not ok:
                        raise ProgramError('arg type mismatch ' + a)
                edge(n['next'])
            elif n['op'] == 'branch':
                _keys(n, ('op', 'left', 'right', 'yes', 'no', 'unknown'), nid)
                if 'ref' not in n['left'] or operand(n['left']) != operand(n['right']):
                    raise ProgramError('branch needs ref left and equal types')
                for k in ('yes', 'no', 'unknown'):
                    edge(n[k])
            else:
                _keys(n, ('op', 'status'), nid)
                if n['status'] not in ('done', 'abstain'):
                    raise ProgramError('bad status')

    def run(self, dispatch):
        """Execute with fresh bindings. dispatch(atom, args) is trusted; returns an audit dict."""
        c, lim, nodes = self.contract, self.contract.limits, self._p['nodes']
        bind, trace = {}, []  # bind: call-node -> projected result (ephemeral per run)
        st = dict(attempts=0, transitions=0)

        def val(o):
            if 'lit' in o:
                return o['lit']
            return bind.get(o['ref']['node'], {}).get(o['ref']['path'], _MISSING)

        def end(terminal):
            trace.append({'ev': 'terminal', 'terminal': terminal})
            return {'program_sha': self.sha, 'terminal': terminal, 'trace': trace, 'attempts': st['attempts'],
                    'transitions': st['transitions'], 'accepted': False, 'rollout_authorized': False}

        cur = self._p['entry']
        while True:
            if st['transitions'] >= lim.max_transitions:
                return end('budget:transitions')
            st['transitions'] += 1
            n = nodes[cur]
            if n['op'] == 'stop':
                return end('stop:' + n['status'])
            if n['op'] == 'branch':
                l, r = val(n['left']), val(n['right'])
                if l is _MISSING or r is _MISSING:
                    k = 'unknown'
                else:
                    # Both operands already share a declared type. number permits int values.
                    k = 'yes' if l == r else 'no'
                trace.append({'ev': 'branch', 'node': cur, 'edge': k, 'missing': k == 'unknown'})
                cur = n[k]
                continue
            args, spec = {}, c.atoms[n['atom']]['args']
            for a, o in n['args'].items():
                v = val(o)
                if v is _MISSING:
                    trace.append({'ev': 'refusal', 'node': cur, 'reason': 'missing_binding', 'arg': a})
                    return end('refused:missing_binding')
                ok = v in spec[a]['values'] if spec[a]['type'] == 'enum' else fits(spec[a]['type'], v)
                if not ok:
                    trace.append({'ev': 'refusal', 'node': cur, 'reason': 'bad_arg_value', 'arg': a})
                    return end('refused:bad_arg_value')
                args[a] = v
            if st['attempts'] >= lim.max_attempts:
                trace.append({'ev': 'refusal', 'node': cur, 'reason': 'attempt_budget'})
                return end('budget:attempts')
            st['attempts'] += 1  # counted BEFORE dispatch
            trace.append({'ev': 'attempt', 'node': cur, 'atom': n['atom'], 'args': dict(args), 'n': st['attempts']})
            try:
                raw = dispatch(n['atom'], copy.deepcopy(args))
            except BaseException as e:  # no retry; result unknown
                if isinstance(e, (KeyboardInterrupt, SystemExit)):
                    raise
                trace.append({'ev': 'exception', 'node': cur, 'type': type(e).__name__})
                return end('exception')
            if not isinstance(raw, dict):
                trace.append({'ev': 'result', 'node': cur, 'values': {}, 'dropped': ['<non-dict>']})
                bind[cur] = {}
            else:
                bind[cur], dropped = c.project(n['atom'], raw)
                trace.append({'ev': 'result', 'node': cur, 'values': dict(bind[cur]), 'dropped': dropped})
            cur = n['next']


def native_dispatch(contract, namespace, projected_api):
    """Owner-supplied adapter: calls namespace[atom](projected_api, args) for contract atoms only."""
    def dispatch(atom, args):
        if atom not in contract.atoms:
            raise ProgramError('atom not in contract')
        return namespace[atom](projected_api, args)
    return dispatch


def save_program(path, prog):
    """Owner save: exclusive creation (FileExistsError if present)."""
    body = {'program': prog.program, 'program_sha': prog.sha, 'contract_sha': prog.contract.sha,
            'package_digest': prog.contract.package_digest}
    art = dict(body, accepted=False, rollout_authorized=False, artifact_sha=sha(body))
    with open(path, 'x', encoding='utf-8') as f:
        f.write(canon(art))
        f.flush()
        os.fsync(f.fileno())
    return prog.sha


def load_program(path, contract):
    """Owner load: verify integrity, re-validate against the owner contract; executes nothing."""
    with open(path, 'rb') as f:
        raw = f.read(contract.limits.max_bytes * 2 + 1)
    if len(raw) > contract.limits.max_bytes * 2:
        raise ProgramError('artifact too large')
    art = strict_loads(raw.decode('utf-8'))
    _keys(art, ('program', 'program_sha', 'contract_sha', 'package_digest', 'accepted', 'rollout_authorized',
                'artifact_sha'), 'artifact')
    if art['accepted'] is not False or art['rollout_authorized'] is not False:
        raise ProgramError('artifact may not carry acceptance')
    body = {k: art[k] for k in ('program', 'program_sha', 'contract_sha', 'package_digest')}
    if sha(body) != art['artifact_sha'] or art['contract_sha'] != contract.sha \
            or art['package_digest'] != contract.package_digest:
        raise ProgramError('artifact integrity mismatch')
    prog = AtomProgram(art['program'], contract)
    if prog.sha != art['program_sha']:
        raise ProgramError('program sha mismatch')
    return prog
