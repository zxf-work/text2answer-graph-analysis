"""Rescore finished E2 runs from their turns.jsonl with the current scorer (no model calls, but loads graphs: run on a server).

Usage: python bench/sessions/rescore.py <attributed graph>... -- <run dir>...
Rewrites summary.json in place (the previous one is kept as summary.before_rescore.json) and marks it "rescored".
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ["T2R_GRAPH_CACHE"] = "1"
from reuse_fault import run as run_plan  # noqa: E402
from run_sessions import specs  # noqa: E402
from workload import alternative_golds, gold_value, matches, sessions  # noqa: E402
from t2r.graphs import load_graph  # noqa: E402


def main():
    i = sys.argv.index("--")
    graphs, runs = sys.argv[1:i], sys.argv[i + 1:]
    gold = {}   # (session, turn) -> (turn spec, {reading: gold}, alternatives)
    for spec in specs(graphs):
        lg = load_graph(spec["name"], spec["path"], spec["description"], override={"directed": spec["directed"], "weighted": spec["weighted"]})
        for sess in sessions(spec):
            for n, t in enumerate(sess["turns"], 1):
                g = {}
                for reading, plan in t["gold"].items():
                    vals, _ = run_plan(plan, lg, 1, None, {})
                    g[reading] = gold_value(t["expect"], vals[plan.steps[-1].id], t)
                gold[(sess["id"], n)] = (t, g, alternative_golds(t, lg, spec["path"]))
    for run in runs:
        rows = [json.loads(l) for l in open(os.path.join(run, "turns.jsonl"))]
        changed = []
        for r in rows:
            t, g, alts = gold[(r["session"], r["turn"])]
            amb = "user" in t
            want = g[t["user"]] if amb else g["-"]
            ok = any(matches(t["expect"], w, r.get("answer")) for w in [want] + alts)
            other = [k for k in g if amb and k != t["user"]]
            if ok != r["correct"]:
                changed.append(f"{r['session']} t{r['turn']} {'+' if ok else '-'}")
            r["correct"] = ok
            r["other_reading"] = bool(other) and matches(t["expect"], g[other[0]], r.get("answer")) and not ok
            if amb and not r.get("asked_contracts") and not r["asked"]:
                r["decision_ok"] = bool(t.get("carried")) and (r.get("reading") == t["user"] or (r.get("reading") is None and ok))
        sp = os.path.join(run, "summary.json")
        S = json.load(open(sp))
        if not os.path.exists(os.path.join(run, "summary.before_rescore.json")):
            json.dump(S, open(os.path.join(run, "summary.before_rescore.json"), "w"), indent=1)
        fol = [r for r in rows if r["kind"] != "new"]; am = [r for r in rows if r["ambiguous"]]
        S.update(answer_accuracy=round(sum(r["correct"] for r in rows) / len(rows), 4), follow_up_accuracy=round(sum(r["correct"] for r in fol) / len(fol), 4),
                 ambiguous_handled=sum(r["decision_ok"] for r in am), ambiguous_correct=sum(r["correct"] for r in am),
                 silent_other_reading=sum(r["other_reading"] and not r["asked"] for r in am),
                 wrong_turns=[f"{r['session']} t{r['turn']} ({r['kind']})" for r in rows if not r["correct"]], rescored=True)
        json.dump(S, open(sp, "w"), indent=1)
        print(run, S["answer_accuracy"], "follow-ups", S["follow_up_accuracy"], "ambiguous handled", S["ambiguous_handled"], "correct", S["ambiguous_correct"],
              "silent other", S["silent_other_reading"], "| changed:", changed, "| wrong:", S["wrong_turns"], flush=True)


if __name__ == "__main__":
    main()
