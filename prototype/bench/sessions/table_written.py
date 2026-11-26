"""Model-written sessions: one row per writer, graph and repetition of our system, against one reference.

  python bench/sessions/table_written.py runs/written-runs --ours claude-haiku-5-5/full-cache --reps 2 3 4 --ref claude-opus-5-5/codegen_independent-cache@1

Needs compare_written.py and judge_written.py to have run for each repetition (to_check.<ours>@<rep>.judged.jsonl).
same = loose match or judged same; variant (with --variants, the output of rerun_reference.py --all) = judged different
from the reference's main answer, but equal to an alternative the reference script itself printed, so the two systems
computed the same thing under a convention the reference listed (which one the user meant is not decided); incomplete = our answer holds the ingredients but not the value asked for;
different = the two answers conflict (who is right is not decided here).
"""
from __future__ import annotations

import argparse
import collections
import json
import os

import sys
import types

from compare_written import agree, atoms, load, val

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


def variant_match(ours, cands):
    """Labels of the reference's alternatives our answer equals. The loose test accepts a short answer whose numbers all
    occur in a long one, so the two must also be of similar size here: a single number is not matched to a ranking."""
    n = len(atoms(ours)) or 1
    out = []
    for c in cands:
        a = c["answer"]
        if c["label"] == "main" or a is None or isinstance(a, str) and len(a) >= 60000:
            continue
        m = len(atoms(a)) or 1
        if min(n, m) / max(n, m) >= 0.5 and agree(ours, a):
            out.append(c["label"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--ours", required=True); ap.add_argument("--reps", nargs="+", required=True); ap.add_argument("--ref", required=True)
    ap.add_argument("--variants", help="ref_variants.jsonl from rerun_reference.py --all")
    a = ap.parse_args()
    variants = {tuple(r["key"]): r for r in map(json.loads, open(a.variants))} if a.variants else {}
    rerun = {k for k, r in variants.items() if not r.get("error")}
    ref = load(a.root, a.ref, "1")
    labels = {}
    cols = ["turns", "answer", "by code", "unconfirmed", "unsupported", "clarify", "error", "no answer", "same", "code same", "code different", "first_incomplete", "variant", "different", "unjudged", "no ref", "guarded", "guarded same", "guarded different"]
    print("writer graph rep " + " ".join(cols) + " compute_s")
    for rep in a.reps:
        ours = load(a.root, a.ours, rep)
        jf = os.path.join(a.root, f"to_check.{a.ours.replace('/', '_')}@{rep}.judged.jsonl")
        judged = {tuple(r["key"]): r["verdict"] for r in map(json.loads, open(jf))} if os.path.exists(jf) else {}
        tab, secs = collections.defaultdict(collections.Counter), collections.Counter()
        names = collections.defaultdict(collections.Counter)
        labels[rep] = {}
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
                    if v in ("different", "unjudged") and key in rerun:
                        hit = variant_match(val(o), variants[key]["candidates"])
                        if hit:
                            v = "variant"
                            if g[0] == "all":
                                labels[rep][key] = hit
                    c[v] += 1
                    if code and v in ("same", "different"):
                        c["code " + v] += 1
                    if guarded and v in ("same", "different"):
                        c["guarded " + v] += 1
                        names[v].update(guard_flags(o, ours, key))
        for g in sorted(tab):
            print(g[0], g[1], rep, " ".join(str(tab[g][k]) for k in cols), round(secs[g]))
        print("# guards rep", rep, {v: {k: n // 2 for k, n in c.items()} for v, c in names.items()})    # each turn is counted in its group and in "all"


    if a.variants:
        print("# reference scripts run again:", len(rerun), "of", len(variants), "tried; main answer reproduced:", sum(bool(variants[k].get("main_reproduced")) for k in rerun))
        for rep in a.reps:
            print("# variant rep", rep, len(labels[rep]), "turns")
        out = os.path.join(a.root, f"variant_matches.{a.ours.replace('/', '_')}.json")
        json.dump({rep: {"/".join(map(str, k)): v for k, v in sorted(labels[rep].items())} for rep in a.reps}, open(out, "w"), indent=1)
        print("# labels ->", out)


if __name__ == "__main__":
    main()
