"""Model-written sessions: the questions on which our answer is judged "different" from the reference in every one of
the given repetitions, written out for a hand label (who is right is not decided by compare or judge).

  python bench/sessions/stable_differences.py runs/written-runs --ours claude-haiku-5-5/full-cache --reps 11 12 13 --ref claude-opus-5-5/codegen_independent-cache@1 --out runs/written-runs/stable_11-13.jsonl

One row per question: the session's earlier questions, ours per repetition (answer, plan steps, flags, conventions),
the reference answer and what the reference run stored of its script.
"""
from __future__ import annotations

import argparse
import json
import os

from compare_written import agree, load, val


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root"); ap.add_argument("--ours", required=True); ap.add_argument("--reps", nargs="+", required=True)
    ap.add_argument("--ref", required=True); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    ref = load(a.root, a.ref, "1")
    runs, verdicts = {}, {}
    for rep in a.reps:
        runs[rep] = load(a.root, a.ours, rep)
        jf = os.path.join(a.root, f"to_check.{a.ours.replace('/', '_')}@{rep}.judged.jsonl")
        judged = {tuple(r["key"]): r for r in map(json.loads, open(jf))}
        for k, o in runs[rep].items():
            r = ref.get(k)
            if o["outcome"] == "answer" and r is not None and r["outcome"] == "answer" and not agree(val(o), r["answer"]):
                verdicts.setdefault(k, {})[rep] = judged.get(k, {})
    n = 0
    with open(a.out, "w") as f:
        for k in sorted(verdicts):
            if len(verdicts[k]) < len(a.reps) or any(v.get("verdict") != "different" for v in verdicts[k].values()):
                continue
            first = runs[a.reps[0]]
            r = ref[k]
            row = {"key": list(k), "earlier": [first[k[:3] + (t,)]["q"] for t in range(1, k[3]) if k[:3] + (t,) in first], "q": first[k]["q"],
                   "event_before": any((first.get(k[:3] + (t,)) or {}).get("event") for t in range(1, k[3] + 1)),
                   "ref_answer": r["answer"], "ref_script": r.get("code") or r.get("plan"),
                   "ours": {rep: {"answer": val(runs[rep][k]), "by": runs[rep][k].get("session_outcome"), "flags": runs[rep][k].get("flags"),
                                  "steps": [[s["id"], s["op"], s["args"]] for s in ((runs[rep][k].get("plan") or {}).get("steps") or [])],
                                  "answer_spec": (runs[rep][k].get("plan") or {}).get("answer"),
                                  "code_task": (runs[rep][k].get("plan") or {}).get("code_task"),
                                  "judge": {x: verdicts[k][rep].get(x) for x in ("verdict", "why", "reason") if verdicts[k][rep].get(x)}} for rep in a.reps}}
            f.write(json.dumps(row, default=str) + "\n"); n += 1
    print(n, "stable differences ->", a.out)


if __name__ == "__main__":
    main()
