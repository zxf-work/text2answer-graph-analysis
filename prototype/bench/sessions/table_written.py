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

from compare_written import agree, load, val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--ours", required=True); ap.add_argument("--reps", nargs="+", required=True); ap.add_argument("--ref", required=True)
    a = ap.parse_args()
    ref = load(a.root, a.ref, "1")
    cols = ["turns", "answer", "by code", "unconfirmed", "unsupported", "clarify", "error", "no answer", "same", "code same", "code different", "first_incomplete", "different", "unjudged", "no ref"]
    print("writer graph rep " + " ".join(cols) + " compute_s")
    for rep in a.reps:
        ours = load(a.root, a.ours, rep)
        jf = os.path.join(a.root, f"to_check.{a.ours.replace('/', '_')}@{rep}.judged.jsonl")
        judged = {tuple(r["key"]): r["verdict"] for r in map(json.loads, open(jf))} if os.path.exists(jf) else {}
        tab, secs = collections.defaultdict(collections.Counter), collections.Counter()
        for key, o in sorted(ours.items()):
            for g in (key[:2], ("all", "all")):
                c = tab[g]
                c["turns"] += 1; c[o["outcome"]] += 1; secs[g] += o.get("compute_seconds") or 0
                if o["outcome"] != "answer":
                    continue
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
        for g in sorted(tab):
            print(g[0], g[1], rep, " ".join(str(tab[g][k]) for k in cols), round(secs[g]))


if __name__ == "__main__":
    main()
