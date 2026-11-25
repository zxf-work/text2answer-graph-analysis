"""Model-written sessions: a judge reads the turns where two systems' answers do not match loosely (compare_written.py)
and says whether they give the same values. Calls a model: run on a server.

  python bench/sessions/judge_written.py runs/written-runs/to_check.<ours>.jsonl --model claude-opus-5-5

The judge does not know which answer is right, only whether they agree; "which one is right" stays a hand check.
Verdicts: same (same values, layout aside) | first_incomplete (the first answer lacks a part that was asked, or gives only
ingredients; what it gives does not conflict) | different (values conflict, or the first answers another question).
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from t2r.llm import LLM, parse_json  # noqa: E402

PROMPT = """Two systems answered the same question about a network dataset. Decide whether their answers give the same values.
Ignore layout, key names, rounding (4 significant digits is enough), extra detail, and the order of items unless the question asks for a ranking.

Question: {q}
First answer: {a}
Second answer: {b}

Reply with only JSON: {{"verdict": "same" | "first_incomplete" | "different", "why": "<one line>"}}
- same: the values the question asks for are the same in both.
- first_incomplete: the first answer lacks a part that was asked or gives only the ingredients of the result; what it does give does not conflict with the second.
- different: values conflict, or the first answer answers another question."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("to_check"); ap.add_argument("--model", default="claude-opus-5-5")
    a = ap.parse_args()
    llm = LLM(model=a.model)
    out = open(a.to_check.replace(".jsonl", ".judged.jsonl"), "w")
    tab = collections.defaultdict(collections.Counter)
    for r in map(json.loads, open(a.to_check)):
        if r["kind"] != "differ":
            continue
        try:
            v = parse_json(llm.chat("", PROMPT.format(q=r["q"], a=json.dumps(r["ours"], default=str)[:3000], b=json.dumps(r["ref"], default=str)[:3000]), max_tokens=2000).text)
        except Exception as e:  # noqa: BLE001
            v = {"verdict": "unjudged", "why": str(e)[:200]}
        tab[tuple(r["key"][:2])][v.get("verdict")] += 1
        out.write(json.dumps({**r, **v}, default=str) + "\n"); out.flush()
    for k in sorted(tab):
        print(k, dict(tab[k]))
    print("judge cost", round(llm.usage.cost_usd, 4))


if __name__ == "__main__":
    main()
