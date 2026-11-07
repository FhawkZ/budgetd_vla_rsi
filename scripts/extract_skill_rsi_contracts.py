#!/usr/bin/env python3
"""Read-only syntactic contract extractor for the seven pinned skill packages.

Parses source/*/{skills,perception,SKILL.md} with stdlib ast/hashlib only. Never imports or runs skill code.
Everything emitted is syntactic evidence with line numbers; it is not a semantic or physical guarantee.
"""
import ast
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "source"
OUT = HERE / "structural-contracts.json"
FILES = ("SKILL.md", "skills.py", "perception.py")
EXPECTED_PACKAGES = 7


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def seg(text, node):
    return ast.get_source_segment(text, node) or ast.dump(node)


def signature(text, fn):
    return "def %s(%s)" % (fn.name, ast.unparse(fn.args))


def api_root(node):
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def api_calls(text, fn):
    calls = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and api_root(n.func) == "api":
            calls.append({"method": ast.unparse(n.func), "line": n.lineno, "source": seg(text, n)})
    calls.sort(key=lambda c: (c["line"], c["method"]))
    return calls


def returns(text, fn):
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Return):
            out.append({"line": n.lineno, "source": seg(text, n)})
    out.sort(key=lambda r: r["line"])
    return out


def top_functions(tree):
    return [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def extract_atoms(tree):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ATOMS" for t in n.targets):
            try:
                val = ast.literal_eval(n.value)
            except Exception:
                return None, n.lineno
            return list(val), n.lineno
    return None, None


def parse_skills(path):
    text = path.read_text()
    tree = ast.parse(text, filename=str(path))
    atoms, atoms_line = extract_atoms(tree)
    funcs = top_functions(tree)
    by_name = {f.name: f for f in funcs}
    atom_set = set(atoms or [])
    exported = []
    for f in funcs:
        if f.name.startswith("_"):
            continue
        exported.append({
            "name": f.name,
            "signature": signature(text, f),
            "line": f.lineno,
            "end_line": f.end_lineno,
            "is_atom": f.name in atom_set,
            "api_calls": api_calls(text, f),
            "returns": returns(text, f),
        })
    return {
        "atoms": atoms,
        "atoms_line": atoms_line,
        "atoms_count": len(atoms or []),
        "atoms_defined": {a: (a in by_name) for a in (atoms or [])},
        "atoms_missing_definition": [a for a in (atoms or []) if a not in by_name],
        "exported_functions": exported,
    }


def dict_keys(text, d):
    keys = []
    for k in d.keys:
        keys.append(ast.literal_eval(k) if isinstance(k, ast.Constant) else seg(text, k) if k else "**")
    return keys


def parse_perception(path):
    text = path.read_text()
    tree = ast.parse(text, filename=str(path))
    detect = [f for f in top_functions(tree) if f.name == "detect"]
    det = None
    if detect:
        f = detect[0]
        det = {"signature": signature(text, f), "line": f.lineno, "end_line": f.end_lineno,
               "returns": returns(text, f)}

    module_constants = []
    module_dicts = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) for t in n.targets):
            names = [t.id for t in n.targets]
            if isinstance(n.value, ast.Dict):
                module_dicts.append({"names": names, "line": n.lineno, "keys": dict_keys(text, n.value),
                                     "source": seg(text, n)})
            elif names and all(x.isupper() or x.replace("_", "").isupper() for x in names):
                module_constants.append({"names": names, "line": n.lineno, "source": seg(text, n)})

    dict_literals = []
    slice_caps = []
    owner = {}
    for f in top_functions(tree):
        for n in ast.walk(f):
            owner.setdefault(id(n), f.name)
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            dict_literals.append({"function": owner.get(id(n)), "line": n.lineno, "keys": dict_keys(text, n)})
        elif isinstance(n, ast.Slice) and n.upper is not None:
            slice_caps.append({"function": owner.get(id(n)), "line": n.lineno, "upper": seg(text, n.upper),
                               "upper_is_literal": isinstance(n.upper, ast.Constant),
                               "source": seg(text, n)})
    dict_literals.sort(key=lambda d: d["line"])
    slice_caps.sort(key=lambda d: d["line"])
    return {
        "detect": det,
        "module_constants": module_constants,
        "module_dict_constants": module_dicts,
        "dict_literals": dict_literals,
        "slice_upper_limits": slice_caps,
    }


def main():
    global SRC, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SRC)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    SRC, OUT = args.source, args.output
    pkgs = sorted(p for p in SRC.iterdir() if p.is_dir())
    problems = []
    if len(pkgs) != EXPECTED_PACKAGES:
        problems.append("expected %d packages, found %d" % (EXPECTED_PACKAGES, len(pkgs)))
    result = {
        "note": "Syntactic extraction only (stdlib ast). Not a semantic or physical guarantee; "
                "does not replace manual semantic review or robot experiments. No skill code imported or executed.",
        "source_dir": "source",
        "package_count": len(pkgs),
        "packages": {},
    }
    total_atoms = 0
    total_files = 0
    for pkg in pkgs:
        entry = {"files": {}}
        for fn in FILES:
            p = pkg / fn
            if p.is_file():
                entry["files"][fn] = {"sha256": sha256(p), "bytes": p.stat().st_size,
                                      "lines": len(p.read_text().splitlines())}
                total_files += 1
            else:
                problems.append("%s/%s missing" % (pkg.name, fn))
        if (pkg / "skills.py").is_file():
            entry["skills"] = parse_skills(pkg / "skills.py")
            total_atoms += entry["skills"]["atoms_count"]
            if entry["skills"]["atoms_missing_definition"]:
                problems.append("%s: atoms without definition: %s" % (pkg.name, entry["skills"]["atoms_missing_definition"]))
        if (pkg / "perception.py").is_file():
            entry["perception"] = parse_perception(pkg / "perception.py")
        result["packages"][pkg.name] = entry
    result["file_count"] = total_files
    result["total_atoms"] = total_atoms
    result["problems"] = problems
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print("packages=%d files=%d atoms=%d problems=%d" % (len(pkgs), total_files, total_atoms, len(problems)))
    for p in problems:
        print("PROBLEM:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
