"""Session endpoints of the demo server, and the serialisation shared with recorded sessions.

  POST /api/session/start    {path, name, description, model, on_ambiguity}  -> {job}   result: {sid, card, ledger}
  POST /api/session/ask      {sid, question}                                 -> {job}   result: {turn, ledger}
  POST /api/session/choose   {sid, turn, index}                              -> {job}   the user picks a contract
  POST /api/session/reading  {sid, turn, reading}                            -> {job}   rerun a turn under the other scope reading
  POST /api/session/submit   {sid, question, plan}                           -> {job}   run a plan edited in the interface
  GET  /api/session/recorded                                                 recorded sessions (demo/sessions/*.json)
  GET  /api/session/audit?sid=..                                             the whole session as one audit record
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
RECORDED = os.path.join(HERE, "sessions")
SESSIONS: dict[str, dict] = {}


def plan_graph(plan):
    from t2r.ir import _ref_of
    from t2r.ops import CATALOGUE
    if not isinstance(plan, dict) or not plan.get("steps"):
        return None
    ids = {s["id"] for s in plan["steps"]}

    def refs(v):
        if isinstance(v, str) and v in ids:
            return [v]
        if isinstance(v, list):
            return [x for item in v for x in refs(item)]
        r = _ref_of(v)
        return [r[0]] if r and r[0] in ids else []
    nodes, edges = [], []
    for s in plan["steps"]:
        spec = CATALOGUE.get(s["op"])
        nodes.append({"id": s["id"], "op": s["op"], "args": s.get("args", {}), "note": s.get("note"), "returns": spec.returns if spec else "?",
                      "cost": spec.cost if spec else "?", "doc": spec.doc if spec else "", "scope_sensitive": bool(spec and spec.scope_sensitive)})
        for k, v in (s.get("args") or {}).items():
            edges += [{"from": src, "to": s["id"], "arg": k} for src in refs(v)]
    ans = plan.get("answer") or {}
    answer_steps = [ans.get("step")] if ans.get("step") else list((ans.get("steps") or {}).values())
    return {"nodes": nodes, "edges": edges, "answer_steps": [str(a).split(".")[0] for a in answer_steps if a]}


def turn_payload(session, turn: dict) -> dict:
    d = session.public(turn)
    d["plan_graph"] = plan_graph(d.get("plan"))
    for c in d.get("contracts") or []:
        c["plan_graph"] = plan_graph(c.get("plan"))
    d["pending"] = d.get("outcome") == "clarify" and bool(d.get("contracts"))
    return d


def audit(session, model: str = "") -> dict:
    return {"graph": {"name": session.name, "file": os.path.basename(session.path), "sha1": session.lg.facts.sha1},
            "model": model, "ledger": session.ledger(), "clarifications": session.clarifications,
            "turns": [turn_payload(session, t) for t in session.turns]}


def recorded() -> list[dict]:
    out = []
    for fn in sorted(os.listdir(RECORDED)) if os.path.isdir(RECORDED) else []:
        if fn.endswith(".json") and fn != "index.json":
            try:
                out.append(json.load(open(os.path.join(RECORDED, fn))))
            except Exception:  # noqa: BLE001
                continue
    return out


# ------------------------------------------------------------------ jobs (same polling contract as /api/ask)
def _job(jobs: dict, fn) -> dict:
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "status": "running", "created": time.time(), "started": time.time()}
    jobs[jid] = job

    def work():
        import traceback
        try:
            job["result"] = json.loads(json.dumps(fn(), default=str))
            job["status"] = "done"
        except Exception as e:  # noqa: BLE001
            job["status"] = "error"; job["error"] = f"{type(e).__name__}: {e}"; job["traceback"] = traceback.format_exc()
        job["finished"] = time.time()
    threading.Thread(target=work, daemon=True).start()
    return {"job": jid}


def handle_post(path: str, req: dict, jobs: dict, default_model: str):
    """Returns a JSON-able reply, or None if the path is not a session endpoint."""
    from t2r.llm import LLM
    from t2r.session import Session
    if path == "/api/session/start":
        def start():
            s = Session(req["path"], name=req.get("name"), description=req.get("description") or "",
                        on_ambiguity=req.get("on_ambiguity") or "ask", reuse=req.get("reuse", True))
            sid = uuid.uuid4().hex[:10]
            SESSIONS[sid] = {"session": s, "llm": LLM(model=req.get("model") or default_model), "lock": threading.Lock()}
            return {"sid": sid, "card": s.card, "ledger": s.ledger(), "load_info": s.lg.load_info}
        return _job(jobs, start)
    if not path.startswith("/api/session/"):
        return None
    ent = SESSIONS.get(req.get("sid") or "")
    if ent is None:
        return {"error": "unknown session"}
    s, llm = ent["session"], ent["llm"]

    def locked(fn):
        def run():
            with ent["lock"]:
                t = fn()
                return {"turn": turn_payload(s, t), "ledger": s.ledger()}
        return _job(jobs, run)
    if path == "/api/session/ask":
        return locked(lambda: s.ask(req["question"], llm, explain=bool(req.get("explain"))))
    if path == "/api/session/choose":
        return locked(lambda: s.explain(s.choose(int(req["index"]), int(req["turn"])), llm))
    if path == "/api/session/reading":
        return locked(lambda: s.explain(s.use_reading(req["reading"], int(req["turn"])), llm))
    if path == "/api/session/submit":
        return locked(lambda: s.explain(s.submit(req["plan"], req.get("question") or "(edited plan)"), llm))
    return {"error": "not found"}


def handle_get(path: str, q: dict):
    if path == "/api/session/recorded":
        return recorded()
    if path == "/api/session/audit":
        ent = SESSIONS.get(q.get("sid") or "")
        return audit(ent["session"], ent["llm"].model) if ent else {"error": "unknown session"}
    return None
