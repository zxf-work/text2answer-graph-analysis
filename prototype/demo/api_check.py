"""End-to-end check of the session endpoints against a running demo server (calls a model). Usage: python demo/api_check.py <port> <edge file>"""
import json
import sys
import time
import urllib.request

port, path = sys.argv[1], sys.argv[2]
base = f"http://127.0.0.1:{port}"


def call(p, body=None):
    req = urllib.request.Request(base + p, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def job(p, body):
    r = call(p, body)
    assert "job" in r, r
    while True:
        j = call(f"/api/job/{r['job']}")
        if j["status"] == "done":
            return j["result"]
        if j["status"] == "error":
            raise SystemExit(f"{p} failed: {j['error']}\n{j.get('traceback')}")
        time.sleep(0.5)


for _ in range(120):
    try:
        call("/api/stages"); break
    except Exception:  # noqa: BLE001
        time.sleep(1)
r = job("/api/session/start", {"path": path, "name": "pokec", "model": "claude-haiku-5-5", "description": "Pokec social network: each row is a directed friendship."})
sid = r["sid"]; print("started", sid, r["load_info"], list(r["card"]["node_attributes"]["attributes"]))
x = r["card"]["node_attributes"]["attributes"]["region"]["top_values"][0]["value"]
show = lambda t: print(f"  turn {t['turn']}: {t['outcome']:<14} reading {t.get('reading')} reused {t.get('steps_reused')} executed {t.get('steps_executed')} explanation {len(t.get('explanation') or '')} chars {t.get('error') or ''}")  # noqa: E731
t1 = job("/api/session/ask", {"sid": sid, "question": "Who are the 10 most influential users by PageRank?", "explain": True})["turn"]; show(t1)
t2 = job("/api/session/ask", {"sid": sid, "question": f'Who are the 10 most influential users within region "{x}"?', "explain": True})["turn"]; show(t2)
assert t2["pending"] and len(t2["contracts"]) == 2 and all(c["plan_graph"] for c in t2["contracts"])
i = next(k for k, c in enumerate(t2["contracts"]) if c["reading"] == "B")
t2 = job("/api/session/choose", {"sid": sid, "turn": t2["turn"], "index": i})["turn"]; show(t2)
assert t2["reading"] == "B" and t2["explanation"] and not t2["pending"]
t3 = job("/api/session/reading", {"sid": sid, "turn": t2["turn"], "reading": "A"})["turn"]; show(t3)
assert t3["reading"] == "A" and any(s["cached"] and s["op"] == "pagerank" and s["from_turn"] == 1 for s in t3["trace"])
plan = t1["plan"]; next(s for s in plan["steps"] if s["op"] == "top_k")["args"]["k"] = 25
r4 = job("/api/session/submit", {"sid": sid, "plan": plan, "question": "edited: top 25"}); t4 = r4["turn"]; show(t4)
assert t4["outcome"] == "partial reuse" and len(t4["answer"]) == 25
a = call(f"/api/session/audit?sid={sid}")
print("audit:", len(a["turns"]), "turns;", a["ledger"]["steps_reused"], "reused,", a["ledger"]["steps_executed"], "executed; choices", [c.get("answered") for c in a["clarifications"] if c.get("answered")])
print("recorded sessions served:", [s["name"] for s in call("/api/session/recorded")])
print("ALL OK")
