"""Record a session for replay in the interface (demo/sessions/<name>.json). Calls a model: run on a server.

Usage: python demo/make_session.py <edge file> --script demo/signature.json [--model M] [--work DIR]
The script (see demo/signature.json) is a list of steps: {"ask": question} or {"event": change to the files}, each
with "say", the presenter's line, which the interface shows while replaying. {x} and {y} in a question are the two most
common values of the script's attribute. The session runs on a copy of the files, so an event really changes them.
Each recorded step is what the interface would receive live, including the pending two-contract state before the choice.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "bench", "sessions"))
from session_api import RECORDED, audit, event_text, turn_payload  # noqa: E402
from run_stale import Files  # noqa: E402
from t2r.llm import LLM  # noqa: E402
from t2r.session import Session  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("path"); ap.add_argument("--script", required=True); ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--work", default="")
a = ap.parse_args()
sc = json.load(open(a.script))

work = a.work or tempfile.mkdtemp(prefix="t2a-rec-")
files = Files({"name": sc["name"], "path": a.path, "directed": True, "weighted": False, "description": sc["description"]}, work)
s = Session(files.live, name=sc["name"], description=sc["description"], code_fallback=True, replay_plans=True)
top = s.card["node_attributes"]["attributes"][sc["attribute"]]["top_values"]
x, y = top[0]["value"], top[1]["value"]
llm = LLM(model=a.model)
choose = sc.get("choose", "B")
steps = []
for st in sc["steps"]:
    if "event" in st:
        info = files.event(st["event"])
        text = event_text(info)
        steps.append({"kind": "event", "say": st.get("say"), "text": text, "info": info})
        print("event", text, flush=True)
        continue
    q = st["ask"].replace("{x}", x).replace("{y}", y)
    t = s.ask(q, llm, explain=True)
    steps.append({"kind": "ask", "question": q, "say": st.get("say"), "turn": turn_payload(s, t), "ledger": s.ledger()})
    print(t["turn"], q, "->", t["outcome"], t.get("error") or t.get("unsupported") or "", f"calls {t.get('llm_calls')}", flush=True)
    if t["outcome"] == "clarify" and t.get("contracts"):
        i = next((k for k, c in enumerate(t["contracts"]) if c["reading"] == choose), 0)
        t = s.explain(s.choose(i), llm)
        steps.append({"kind": "choose", "index": i, "turn": turn_payload(s, t), "ledger": s.ledger()})
        print("   chose", t["contracts"][i]["reading"], "->", t["outcome"], flush=True)
        other = "A" if choose == "B" else "B"
        t2 = s.explain(s.use_reading(other, t["turn"]), llm)
        steps.append({"kind": "reading", "reading": other, "of_turn": t["turn"], "turn": turn_payload(s, t2), "ledger": s.ledger()})
        s.scope_choice = {"reading": choose, "turn": t["turn"]}          # the recorded user looks at the other reading, then keeps the first choice
        print("   looked at", other, "->", t2["outcome"], flush=True)
os.makedirs(RECORDED, exist_ok=True)
rec = {"name": sc["name"], "title": sc["title"], "model": a.model, "description": sc["description"], "file": sc.get("file") or os.path.basename(a.path),
       "card": dict(s.card), "steps": steps, "close": sc.get("close"), "audit": audit(s, a.model)}
out = os.path.join(RECORDED, f"{sc['name']}.json")
json.dump(rec, open(out, "w"), ensure_ascii=False, default=str)
json.dump(sorted(f for f in os.listdir(RECORDED) if f.endswith(".json") and f != "index.json"), open(os.path.join(RECORDED, "index.json"), "w"))
print("wrote", out, os.path.getsize(out) // 1024, "kB;", f"${llm.usage.cost_usd:.3f}")
if not a.work:
    shutil.rmtree(work, ignore_errors=True)
