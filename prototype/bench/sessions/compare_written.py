"""Model-written sessions: what each system did with every question, and where two systems give the same answer.

  python bench/sessions/compare_written.py runs/written-runs --ours claude-haiku-5-5/full-cache --ref claude-opus-5-5/codegen_independent-cache [--rep 1]

No gold plans exist for these questions. Two systems that share no code path (a typed plan run by the engine, a script
written from scratch) giving the same value is the evidence that the value is right; where they differ, or where one
has no answer, the turn goes to the list for a hand check (<root>/to_check.<ours>.jsonl). Agreement is tested loosely
on purpose (the same numbers and node ids, in any layout), so a turn counted as agreeing can still differ in order:
the hand check samples those too.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os


def atoms(x, out=None):
    """The numbers and identifiers of an answer, whatever its layout. Keys of objects count: {"DE": 12} carries "DE"."""
    out = [] if out is None else out
    if isinstance(x, bool) or x is None:
        return out
    if isinstance(x, (int, float)):
        out.append(f"{float(x):.4g}")
    elif isinstance(x, str):
        s = x.strip()
        if s[:1] in "[{":                                  # an answer object given as text
            try:
                return atoms(json.loads(s), out)
            except ValueError:
                pass
        try:
            out.append(f"{float(s):.4g}")
        except ValueError:
            if s and len(s) <= 60:
                out.append(s.lower())
    elif isinstance(x, dict):
        for k, v in x.items():
            if k not in ("node", "value", "label", "answer", "nodes", "values", "count", "rank") :
                atoms(k, out)
            atoms(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            atoms(v, out)
    return out


def bools(x):
    """The yes/no values of an answer, in order (a bare true against a bare false is not agreement)."""
    if isinstance(x, bool):
        return [x]
    if isinstance(x, str) and x.strip().lower() in ("true", "false", "yes", "no"):
        return [x.strip().lower() in ("true", "yes")]
    if isinstance(x, dict):
        return [b for v in x.values() for b in bools(v)]
    if isinstance(x, (list, tuple)):
        return [b for v in x for b in bools(v)]
    return []


def agree(a, b) -> bool:
    A, B = collections.Counter(atoms(a)), collections.Counter(atoms(b))
    if not A or not B:
        return not A and not B and bools(a) == bools(b)    # both empty lists, or the same yes/no
    small, big = (A, B) if sum(A.values()) <= sum(B.values()) else (B, A)
    numeric = [k for k in small if k.replace(".", "").replace("e", "").replace("-", "").replace("+", "").isdigit()]
    hit = sum(min(small[k], big[k]) for k in numeric)
    # every number of the shorter answer appears in the longer one (labels may be worded differently)
    return bool(numeric) and hit == sum(small[k] for k in numeric)


def val(o):
    """The answer to compare: for a turn answered by generated code, the value without the witness (two correct
    solutions may show different members or paths)."""
    return o["answer_value"] if o.get("answer_value") is not None else o["answer"]


def load(root, system, rep):
    system, rep = (system.split("@") + [rep])[:2]          # "<model>/<variant>@<rep>" picks another repetition
    rows = {}
    for f in glob.glob(os.path.join(root, "*", "*", system, f"rep{rep}", "turns.jsonl")):
        for r in map(json.loads, open(f)):
            rows[(r["writer"], r["graph"], r["session"], r["turn"])] = r
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--ours", required=True); ap.add_argument("--ref", required=True); ap.add_argument("--rep", default="1")
    a = ap.parse_args()
    ours, ref = load(a.root, a.ours, a.rep), load(a.root, a.ref, a.rep)
    tab = collections.defaultdict(collections.Counter)
    check = open(os.path.join(a.root, f"to_check.{a.ours.replace('/', '_')}.jsonl"), "w")
    for key in sorted(ours):
        o, r = ours[key], ref.get(key)
        c = tab[key[:2]]
        c["turns"] += 1
        c[f"ours: {o['outcome']}"] += 1
        if r is None:
            c["no reference run"] += 1
            continue
        both = o["outcome"] == "answer" and r["outcome"] == "answer"
        kind = ("agree" if agree(val(o), r["answer"]) else "differ") if both else f"ours {o['outcome']} / ref {r['outcome']}"
        c[kind] += 1
        if kind != "agree":
            cut = lambda v: v if len(json.dumps(v, default=str)) <= 1500 else json.dumps(v, default=str)[:1500] + " ..."  # noqa: E731
            check.write(json.dumps({"key": key, "q": o["q"], "kind": kind, "ours": cut(val(o)), "ref": cut(r["answer"]), "unsupported": o.get("unsupported"),
                                    "clarification": o.get("clarification"), "error": o.get("error"), "ref_error": r.get("error"), "plan": cut(o.get("plan"))}, default=str) + "\n")
    for k in sorted(tab):
        print(k, json.dumps(dict(sorted(tab[k].items()))))
    tot = collections.Counter()
    for c in tab.values():
        tot.update(c)
    print("all", json.dumps(dict(sorted(tot.items()))))


if __name__ == "__main__":
    main()
