"""Model-written sessions: one row per writer, graph and repetition of our system, against one reference.

  python bench/sessions/table_written.py runs/written-runs --ours claude-haiku-5-5/full-cache --reps 2 3 4 --ref claude-opus-5-5/codegen_independent-cache@1

Needs compare_written.py and judge_written.py to have run for each repetition (to_check.<ours>@<rep>.judged.jsonl).
same = loose match or judged same; incomplete = our answer holds the ingredients but not the value asked for;
different = the two answers conflict (who is right is not decided here).
"""
from __future__ import annotations

import argparse
import collections
import json
import os

import sys
import types

from compare_written import agree, load, val

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from t2r.verify import guards  # noqa: E402


def guard_flags(o, ours, key):
    """The guards, evaluated again on the stored plan, question and answer, so that every repetition is held to the guards
    as they are now. The comparison guard needs the executed values: it is taken from the flags the run recorded."""
    kept = [f for f in o.get("flags") or [] if f == "guard_boolean_from_comparison"]
    plan = o.get("plan")
    if not plan or not plan.get("steps"):
        return kept
    b = plan.get("based_on")
    base = (ours.get(key[:3] + (b,)) or {}).get("plan") if b else None
    fs = guards(types.SimpleNamespace(steps=plan["steps"], answer=None), None, o.get("q"), val(o), base, b, directed=key[1] != "twitch")
    return kept + [f["check"] for f in fs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--ours", required=True); ap.add_argument("--reps", nargs="+", required=True); ap.add_argument("--ref", required=True)
    a = ap.parse_args()
    ref = load(a.root, a.ref, "1")
    cols = ["turns", "answer", "by code", "unconfirmed", "unsupported", "clarify", "error", "no answer", "same", "code same", "code different", "first_incomplete", "different", "unjudged", "no ref", "guarded", "guarded same", "guarded different"]
    print("writer graph rep " + " ".join(cols) + " compute_s")
    for rep in a.reps:
        ours = load(a.root, a.ours, rep)
        jf = os.path.join(a.root, f"to_check.{a.ours.replace('/', '_')}@{rep}.judged.jsonl")
        judged = {tuple(r["key"]): r["verdict"] for r in map(json.loads, open(jf))} if os.path.exists(jf) else {}
        tab, secs = collections.defaultdict(collections.Counter), collections.Counter()
        names = collections.defaultdict(collections.Counter)
        for key, o in sorted(ours.items()):
            for g in (key[:2], ("all", "all")):
                c = tab[g]
                c["turns"] += 1; c[o["outcome"]] += 1; secs[g] += o.get("compute_seconds") or 0
                if o["outcome"] != "answer":
                    continue
                guarded = bool(guard_flags(o, ours, key))                # an answer the guards of t2r/verify.py flag
                c["guarded"] += guarded
                r = ref.get(key)
                if r is None or r["outcome"] != "answer":
                    c["no ref"] += 1
                    c["by code"] += o.get("session_outcome") == "answer by code"
                else:
                    code = o.get("session_outcome") == "answer by code"      # counted in "answer" too
                    c["by code"] += code
                    v = "same" if agree(val(o), r["answer"]) else judged.get(key, "unjudged")
                    c[v] += 1
                    if code and v in ("same", "different"):
                        c["code " + v] += 1
                    if guarded and v in ("same", "different"):
                        c["guarded " + v] += 1
                        names[v].update(guard_flags(o, ours, key))
        for g in sorted(tab):
            print(g[0], g[1], rep, " ".join(str(tab[g][k]) for k in cols), round(secs[g]))
        print("# guards rep", rep, {v: {k: n // 2 for k, n in c.items()} for v, c in names.items()})    # each turn is counted in its group and in "all"


if __name__ == "__main__":
    main()
