"""A live session on a large attributed graph: the model plans every turn, the engine decides reuse.

Usage: python bench/big/session_live.py <edge file> <categorical attribute> [--model M] [--out DIR] [--choose A|B]
Questions follow the running example of the demo plan. When a turn comes back with two contracts, --choose picks one.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, ".")
from t2r.llm import LLM  # noqa: E402
from t2r.session import Session  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("path"); ap.add_argument("attribute")
ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--out", default="")
ap.add_argument("--choose", default="B"); ap.add_argument("--budget", type=float, default=1e10)
ap.add_argument("--description", default="")
a = ap.parse_args()

t0 = time.time()
s = Session(a.path, description=a.description, budget_ops=a.budget)
print(f"session ready in {time.time() - t0:.1f}s: {s.lg.g.vcount()} nodes, {s.lg.g.ecount()} edges, load {s.lg.load_info}", flush=True)
top = s.card["node_attributes"]["attributes"][a.attribute]["top_values"]
x, y = top[0]["value"], top[1]["value"]
questions = [
    "Who are the 10 most influential users by PageRank?",
    f"Which {a.attribute} is each of them from?",
    "Show the top 20 instead.",
    f"Who are the 10 most influential users within {a.attribute} \"{x}\"?",
    f"And within {a.attribute} \"{y}\"?",
    f"Which 5 values of {a.attribute} have the highest total PageRank?",
    "Show the top 20 again.",
]
llm = LLM(model=a.model)
log = []
for q in questions:
    t = s.ask(q, llm)
    if t["outcome"] == "clarify" and t.get("contracts"):
        print(f"\n== turn {t['turn']}: {q}\n   CLARIFY: {t['clarification']}")
        for c in t["contracts"]:
            print(f"   contract {c['reading']} ({c['source']}): would reuse {c['preview']['reused']} step(s), execute {c['preview']['to_execute']}")
        i = next((k for k, c in enumerate(t["contracts"]) if c["reading"] == a.choose), 0)
        t = s.choose(i)
        print(f"   user chooses {t['contracts'][i]['reading']}")
    print(f"\n== turn {t['turn']}: {q}\n   intent {t.get('intent')} patch {t.get('patch')} based_on {t.get('based_on')}  ->  {t['outcome']}"
          f"   plan+run {t['seconds']:.1f}s, execute {t.get('execute_seconds')}s, saved {t.get('seconds_saved')}s, {t['llm_calls']} model call(s), {t['tokens_in']} tokens in")
    if t.get("error"):
        print("   ERROR", t["error"])
    for r in t.get("trace") or []:
        print(f"   {'REUSED  ' if r['cached'] else 'EXECUTED'} {r['step']:<8} {r['op']:<20} {r['seconds']:>7.2f}s  key {r['key']}")
    for f in t.get("reuse_findings") or []:
        print(f"   rule: {f['check']}: {f['detail']}")
    bad = [f for f in t.get("findings") or [] if not f["ok"]]
    print(f"   verifier: {len(t.get('findings') or [])} checks, {len(bad)} not ok {[f['check'] for f in bad]}")
    print("   references:", json.dumps(t.get("references"), ensure_ascii=False), "\n   answer:", json.dumps(t.get("answer"), ensure_ascii=False)[:400], flush=True)
    log.append(s.public(t))
print(f"\ntotal: {llm.usage.calls} model calls, {llm.usage.input_tokens} tokens in, {llm.usage.output_tokens} out, ${llm.usage.cost_usd:.4f}")
if a.out:
    os.makedirs(a.out, exist_ok=True)
    json.dump({"model": a.model, "path": a.path, "turns": log}, open(os.path.join(a.out, "session.json"), "w"), ensure_ascii=False, indent=1)
