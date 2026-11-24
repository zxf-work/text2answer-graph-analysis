"""Record a session for replay in the interface (demo/sessions/<name>.json). Calls a model: run on a server.

Usage: python demo/make_session.py <edge file> <attribute> --name pokec [--model M] [--choose B] [--description "..."]
Each recorded step is what the interface would receive live, including the pending two-contract state before the choice.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from session_api import RECORDED, audit, turn_payload  # noqa: E402
from t2r.llm import LLM  # noqa: E402
from t2r.session import Session  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("path"); ap.add_argument("attribute"); ap.add_argument("--name", required=True)
ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--choose", default="B"); ap.add_argument("--description", default="")
ap.add_argument("--title", default=""); ap.add_argument("--questions", default="", help="JSON list; {x} and {y} are the two most common attribute values")
a = ap.parse_args()

s = Session(a.path, name=a.name, description=a.description)
top = s.card["node_attributes"]["attributes"][a.attribute]["top_values"]
x, y = top[0]["value"], top[1]["value"]
questions = json.loads(a.questions) if a.questions else [
    "Who are the 10 most influential users?",
    f"Which {a.attribute} is each of them from?",
    "Show the top 20 instead.",
    f"Who are the 10 most influential users within {a.attribute} \"{{x}}\"?",
    f"And within {a.attribute} \"{{y}}\"?",
    f"Which 5 values of {a.attribute} have the highest total PageRank?",
]
llm = LLM(model=a.model)
steps = []
for q in questions:
    q = q.replace("{x}", x).replace("{y}", y)
    t = s.ask(q, llm, explain=True)
    steps.append({"kind": "ask", "question": q, "turn": turn_payload(s, t), "ledger": s.ledger()})
    print(t["turn"], q, "->", t["outcome"], t.get("error") or "", flush=True)
    if t["outcome"] == "clarify" and t.get("contracts"):
        i = next((k for k, c in enumerate(t["contracts"]) if c["reading"] == a.choose), 0)
        t = s.explain(s.choose(i), llm)
        steps.append({"kind": "choose", "index": i, "turn": turn_payload(s, t), "ledger": s.ledger()})
        print("   chose", t["contracts"][i]["reading"], "->", t["outcome"], flush=True)
        other = "A" if a.choose == "B" else "B"
        t2 = s.explain(s.use_reading(other, t["turn"]), llm)
        steps.append({"kind": "reading", "reading": other, "of_turn": t["turn"], "turn": turn_payload(s, t2), "ledger": s.ledger()})
        s.scope_choice = {"reading": a.choose, "turn": t["turn"]}          # the recorded user looks at the other reading, then keeps the first choice
        print("   looked at", other, "->", t2["outcome"], flush=True)
os.makedirs(RECORDED, exist_ok=True)
card = {k: v for k, v in s.card.items()}
rec = {"name": a.name, "title": a.title or f"{a.name}: a {len(questions)}-question session", "model": a.model, "description": a.description,
       "file": os.path.basename(a.path), "card": card, "steps": steps, "audit": audit(s, a.model)}
out = os.path.join(RECORDED, f"{a.name}.json")
json.dump(rec, open(out, "w"), ensure_ascii=False, default=str)
json.dump(sorted(f for f in os.listdir(RECORDED) if f.endswith(".json") and f != "index.json"), open(os.path.join(RECORDED, "index.json"), "w"))
print("wrote", out, os.path.getsize(out) // 1024, "kB;", f"${llm.usage.cost_usd:.3f}")
