"""Session endpoints of the demo server, and the serialisation shared with recorded sessions.

  POST /api/session/start    {path, name, description, model, on_ambiguity}  -> {job}   result: {sid, card, ledger}
  POST /api/session/ask      {sid, question}                                 -> {job}   result: {turn, ledger}
  POST /api/session/choose   {sid, turn, index}                              -> {job}   the user picks a contract
  POST /api/session/reading  {sid, turn, reading}                            -> {job}   rerun a turn under the other scope reading
  POST /api/session/submit   {sid, question, plan}                           -> {job}   run a plan edited in the interface
  POST /api/session/event    {sid}                                           -> {job}   result: {event}; the next file change of the
                                                                             script, on a scripted graph only (see add_live)
  GET  /api/session/recorded                                                 recorded sessions (demo/sessions/*.json)
  GET  /api/session/audit?sid=..                                             the whole session as one audit record
  GET  /api/compare                                                          side-by-side records (demo/compare/*.json)
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
LIVE: dict[str, dict] = {}     # name -> a scripted graph: a working copy of its files that the script's events may change


def event_text(info: dict) -> str:
    if info.get("type") == "append_edges":
        return f"{info['edges_added']:,} rows were appended to the edge file: new incoming links for users {' and '.join(info['targets'])}."
    return json.dumps(info)


def add_live(edge: str, script: str, work: str) -> dict:
    """Offer the script's graph for live sessions (server.py --live). The session runs on a copy of the files under
    `work`, so the script's events really change what the session reads; the original files are never written."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "bench", "sessions"))
    sc = json.load(open(script))
    LIVE[sc["name"]] = {"script": sc, "work": work, "files": None, "lock": threading.Lock(),
                        "spec": {"name": sc["name"], "path": edge, "directed": True, "weighted": False, "description": sc["description"]}}
    return LIVE[sc["name"]]


def live_datasets() -> list[dict]:
    out = []
    for name, lv in LIVE.items():
        p = lv["spec"]["path"]
        with open(p, "r", errors="replace") as f:
            head = [next(f, "").rstrip("\n") for _ in range(4)]
        out.append({"name": name, "path": "live:" + name, "file": os.path.basename(p), "tier": "scripted", "bytes": os.path.getsize(p),
                    "description": lv["spec"]["description"], "head": head, "examples": [], "state": "not loaded", "cached": False})
    return out


def _live_start(lv: dict) -> tuple[str, list[dict]]:
    """A fresh working copy (a file changed by an earlier session is not carried over), and the script's steps."""
    from run_stale import Files
    with lv["lock"]:
        if lv["files"] is None or lv["files"].version:
            lv["files"] = Files(lv["spec"], lv["work"])
    return lv["files"].live, [dict(st) for st in lv["script"]["steps"]]


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


def recorded(d: str = "") -> list[dict]:
    out, RECORDED = [], d or globals()["RECORDED"]
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
            lv = LIVE.get(req["path"][5:]) if req["path"].startswith("live:") else None
            path, steps = _live_start(lv) if lv else (req["path"], [])
            s = Session(path, name=req.get("name"), description=req.get("description") or "",
                        on_ambiguity=req.get("on_ambiguity") or "ask", reuse=req.get("reuse", True),
                        replay_plans=req.get("replay_plans", True), code_fallback=req.get("code_fallback", True))
            sid = uuid.uuid4().hex[:10]
            SESSIONS[sid] = {"session": s, "llm": LLM(model=req.get("model") or default_model), "lock": threading.Lock(), "live": lv,
                             "events": [st["event"] for st in steps if "event" in st]}
            script = []
            if lv:
                top = s.card["node_attributes"]["attributes"][lv["script"]["attribute"]]["top_values"]
                for st in steps:
                    script.append({"event": True} if "event" in st else
                                  {"ask": st["ask"].replace("{x}", str(top[0]["value"])).replace("{y}", str(top[1]["value"]))})
            return {"sid": sid, "card": s.card, "ledger": s.ledger(), "load_info": s.lg.load_info, "script": script}
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
    if path == "/api/session/event":
        if not ent.get("live") or not ent["events"]:
            return {"error": "this session has no file change left to apply"}

        def change():
            with ent["lock"]:
                info = ent["live"]["files"].event(ent["events"].pop(0))
                return {"event": {"text": event_text(info), "info": info}, "left": len(ent["events"])}
        return _job(jobs, change)
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
    if path == "/api/compare":
        return recorded(os.path.join(HERE, "compare"))
    if path == "/api/session/recorded":
        return recorded()
    if path == "/api/session/audit":
        ent = SESSIONS.get(q.get("sid") or "")
        return audit(ent["session"], ent["llm"].model) if ent else {"error": "unknown session"}
    return None
