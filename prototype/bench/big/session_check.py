"""Manual check of session reuse on a large attributed graph (no model calls): hand-written plans for a five-turn session.

Usage: python bench/big/session_check.py <edge file> <categorical attribute> [value]
Prints, per turn, which steps were reused or executed and the time spent and saved.
"""
import json
import sys
import time

sys.path.insert(0, ".")
from t2r.graphs import load_graph, profile_card  # noqa: E402
from t2r.ir import Plan, execute, validate  # noqa: E402

path, attr = sys.argv[1], sys.argv[2]
t0 = time.time()
lg = load_graph("session", path, "", override={"directed": True})
print(f"load {time.time() - t0:.1f}s ({lg.load_info}); nodes {lg.g.vcount()} edges {lg.g.ecount()}")
t0 = time.time(); card = profile_card(lg); print(f"profile card {time.time() - t0:.1f}s")
print(json.dumps(card.get("node_attributes"), ensure_ascii=False)[:1500])
value = sys.argv[3] if len(sys.argv) > 3 else card["node_attributes"]["attributes"][attr]["top_values"][0]["value"]

S = lambda i, op, **a: {"id": i, "op": op, "args": a}  # noqa: E731
turns = [
    ("1 top 10 by PageRank", [S("pr", "pagerank"), S("top", "top_k", map="pr", k=10)], "top"),
    (f"2 their {attr}", [S("pr", "pagerank"), S("top", "top_k", map="pr", k=10), S("a", "attribute_of", nodes="top", attribute=attr)], "a"),
    ("3 top 20 instead", [S("pr", "pagerank"), S("top", "top_k", map="pr", k=20)], "top"),
    (f"4a within {attr}={value}: whole-graph scores, filtered", [S("pr", "pagerank"), S("in", "filter_by_attribute", attribute=attr, value=value),
                                                                  S("r", "restrict_map", map="pr", nodes="in"), S("top", "top_k", map="r", k=10)], "top"),
    (f"4b within {attr}={value}: PageRank on the induced subgraph", [S("in", "filter_by_attribute", attribute=attr, value=value), S("g", "induced_subgraph", nodes="in"),
                                                                       S("pr", "pagerank", graph="g"), S("top", "top_k", map="pr", k=10)], "top"),
    ("5 repeat of 4b", [S("in", "filter_by_attribute", attribute=attr, value=value), S("g", "induced_subgraph", nodes="in"),
                        S("pr", "pagerank", graph="g"), S("top", "top_k", map="pr", k=10)], "top"),
]
cache: dict = {}
answers = {}
for title, steps, ans in turns:
    plan = Plan.model_validate({"steps": steps, "answer": {"step": ans, "kind": "table"}})
    problems = validate(plan, lg, budget_ops=1e11)
    t0 = time.time(); ctx, trace = execute(plan, lg, cache=cache); dt = time.time() - t0
    saved = sum(t.get("seconds_saved", 0) for t in trace)
    print(f"\n== {title}   wall {dt:.2f}s   saved {saved:.2f}s   problems {problems}")
    for t in trace:
        print(f"   {'REUSED  ' if t['cached'] else 'EXECUTED'} {t['step']:<4} {t['op']:<20} {t['seconds']:>7.2f}s  key {t['key']}")
    answers[title[:2]] = [r["node"] for r in ctx.values[ans]][:10]
    print("   answer:", json.dumps(ctx.values[ans][:3], ensure_ascii=False)[:300])
a, b = answers["4a"], answers["4b"]
print(f"\ntop-10 overlap between the two readings of turn 4: {len(set(a) & set(b))}/10; same order: {a == b}")
