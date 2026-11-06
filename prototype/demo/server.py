"""Demo web server for text2answer graph analysis.

Standard library only. Serves the single-page UI in demo/static and a small JSON API:
  GET  /api/datasets           shipped graphs, uploads and example questions
  GET  /api/profile?path=..    profile card for a file (graphs stay loaded in memory)
  POST /api/ask                {path, name, description, question, system, model} -> {job}
  GET  /api/job/<id>           job status and result
  POST /api/upload             raw file body, header X-Filename
  GET  /api/scenes             recorded scenes for replay (demo/scenes/*.json)
  GET  /api/catalogue          operator catalogue

Run:  python3 demo/server.py [--port 8765] [--model claude-opus-5-5]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["T2R_GRAPH_CACHE"] = "1"

from t2r.graphs import cache_status, load_graph, profile_card  # noqa: E402
from t2r.ir import _ref_of  # noqa: E402
from t2r.llm import LLM  # noqa: E402
from t2r.ops import CATALOGUE  # noqa: E402
from t2r.systems import SYSTEMS  # noqa: E402
sys.path.insert(0, HERE)
from viz import make_viz  # noqa: E402

STATIC = os.path.join(HERE, "static")
SCENES = os.path.join(HERE, "scenes")
UPLOADS = os.path.join(HERE, "uploads")
JOBS: dict[str, dict] = {}
DEFAULT_MODEL = "claude-opus-5-5"
# Resident graphs: a graph is loaded once per server process (memory cache in t2r.graphs), restored from the binary
# disk cache when one exists, and every later question on it skips loading entirely. LOADS tracks the state per file
# so the UI can show "loading" without blocking; RESULT_CACHE memoises operator results across questions.
LOADS: dict[str, dict] = {}
CARDS: dict[str, dict] = {}
RESULT_CACHE: dict = {}
LOCK = threading.Lock()

EXAMPLES = {
    "trust": ["Who is the most trusted person?", "Who trusts the most people?", "Who has the strongest tie to the most-trusting person?", "How many people are there, and how many trust relations?"],
    "emails": ["Who sent the most emails?", "How many pairs of people have exchanged email?", "How many emails were sent in total?", "Which pair exchanged the most messages?"],
    "roads": ["What is the shortest route from J0 to J299, and how long is it?", "Which junction lies on the most shortest routes?", "How many junctions are within 3 hops of J0?"],
    "follows": ["Who has the most followers?", "Who follows the most accounts?", "How many accounts does 7 follow?", "Is there a path from 3 to 40?"],
    "purchases": ["How many communities of customers are there, if you connect customers who bought the same product?", "Which product was bought by the most customers?", "Is this graph bipartite?"],
    "citations": ["Which paper is cited the most?", "How many papers cite nothing?", "Which paper has the highest PageRank?"],
    "indexed": ["Which node has the highest degree?", "How many nodes and edges does this graph have?", "How many triangles are there?"],
    "similarity": ["Which two items are most similar?", "How many clusters of items are there?", "What is the most central item?"],
    "bothways": ["How many friendships are there?", "Who has the most friends?", "What is the diameter of the network?"],
    "lesmis": ["Who is the most central character?", "How many communities are there?", "What is the shortest path from Valjean to Javert?", "Who co-occurs most often with Cosette?"],
    "karate": ["Who are the two leaders of the club?", "How many factions does the club split into?", "What is the clustering coefficient?"],
    "facebook": ["Which 10 users have the highest betweenness?", "How many triangles does the network contain?", "What is the diameter?"],
    "enron": ["Who are the top 5 people by PageRank?", "How many connected components are there?", "What is the average clustering coefficient?"],
    "epinions": ["Who is trusted by the most people?", "How many strongly connected components are there?", "Who trusts the most people but is trusted by nobody?"],
}

STAGES = {
    "full": ["load graph", "profile card", "plan (LLM)", "validate + cost tiering", "execute", "verify", "explain (LLM)"],
    "no_verify": ["load graph", "profile card", "plan (LLM)", "validate + cost tiering", "execute", "explain (LLM)"],
    "no_interp": ["load graph", "raw facts", "plan (LLM)", "validate + cost tiering", "execute", "verify", "explain (LLM)"],
    "flat": ["file facts", "tool-calling loop (LLM)", "final answer"],
    "codegen": ["file facts", "write script (LLM)", "run script"],
    "codegen_nofacts": ["write script (LLM)", "run script"],
}


def _datasets() -> list[dict]:
    out = []
    for fname, tier in (("datasets.json", "base"), ("datasets_hard.json", "hard"), ("datasets_scale.json", "scale")):
        p = os.path.join(ROOT, "bench", fname)
        if not os.path.exists(p):
            continue
        for name, d in json.load(open(p)).items():
            path = d["path"] if os.path.isabs(d["path"]) else os.path.join(ROOT, d["path"])
            if not os.path.exists(path):
                continue
            with open(path, "r", errors="replace") as f:
                head = [next(f, "").rstrip("\n") for _ in range(4)]
            st = LOADS.get(os.path.abspath(path), {})
            out.append({"name": name, "path": path, "file": os.path.basename(path), "tier": tier, "bytes": os.path.getsize(path),
                        "description": d.get("description") or "", "head": head, "examples": EXAMPLES.get(name, []),
                        "state": st.get("state", "not loaded"), "cached": cache_status(path)["cached"]})
    for fn in sorted(os.listdir(UPLOADS)) if os.path.isdir(UPLOADS) else []:
        path = os.path.join(UPLOADS, fn)
        with open(path, "r", errors="replace") as f:
            head = [next(f, "").rstrip("\n") for _ in range(4)]
        st = LOADS.get(os.path.abspath(path), {})
        out.append({"name": os.path.splitext(fn)[0], "path": path, "file": fn, "tier": "upload", "bytes": os.path.getsize(path), "description": "", "head": head, "examples": [],
                    "state": st.get("state", "not loaded"), "cached": cache_status(path)["cached"]})
    return out


def _load_key(path: str, description: str) -> str:
    return os.path.abspath(path)


def ensure_loaded(path: str, name: str, description: str) -> dict:
    """Start loading in the background if needed; return the load state {state, seconds, source, error}."""
    key = _load_key(path, description)
    with LOCK:
        st = LOADS.get(key)
        if st and st["state"] in ("loading", "ready"):
            if st["state"] == "loading":
                st["seconds"] = round(time.time() - st["started"], 1)
            return st
        st = {"state": "loading", "started": time.time(), "seconds": 0.0, "name": name}
        LOADS[key] = st

    def work():
        try:
            lg = load_graph(name, path, description or "")
            card = _profile(path, name, description)
            with LOCK:
                CARDS[key] = card
                st.update({"state": "ready", "seconds": round(time.time() - st["started"], 1), "source": lg.load_info.get("source"),
                           "load_seconds": lg.load_info.get("seconds"), "n": lg.g.vcount(), "m": lg.g.ecount()})
        except Exception as e:  # noqa: BLE001
            with LOCK:
                st.update({"state": "error", "error": f"{type(e).__name__}: {e}", "seconds": round(time.time() - st["started"], 1)})
    threading.Thread(target=work, daemon=True).start()
    return st


def _profile(path: str, name: str, description: str) -> dict:
    lg = load_graph(name, path, description or "")
    card = profile_card(lg, with_inference=True)
    card["load_info"] = lg.load_info
    card["binary_cache"] = cache_status(path)
    f = lg.facts
    card["facts"] = {"rows": f.n_rows, "header": f.header, "n_columns": f.n_columns, "sample_rows": f.sample_rows[:4],
                     "reciprocity_of_rows": round(f.reciprocity, 3), "distinct_pairs_directed": f.n_rows_dedup_directed,
                     "distinct_pairs_undirected": f.n_rows_dedup_undirected, "self_loops": f.n_self_loops,
                     "weight_column": f.weight_column_name, "weight_range": [f.weight_min, f.weight_max] if f.weight_column_numeric else None,
                     "weight_has_fractions": f.weight_has_fractions, "row_index_column": f.row_index_column, "ids_numeric": f.ids_numeric}
    try:
        card["viz"] = make_viz(lg)  # overview: neighbourhood of the hubs, nothing highlighted
    except Exception as e:  # noqa: BLE001
        card["viz"] = {"error": str(e)}
    return card


def _plan_graph(plan: dict | None) -> dict | None:
    """Edges between plan steps from argument references, plus the return type of each step."""
    if not isinstance(plan, dict) or not plan.get("steps"):
        return None
    ids = {s["id"] for s in plan["steps"]}
    nodes, edges = [], []

    def refs(v):
        if isinstance(v, str):
            if v in ids:
                return [v]
            r = _ref_of(v)
            return [r[0]] if r and r[0] in ids else []
        if isinstance(v, dict):
            r = _ref_of(v)
            return [r[0]] if r and r[0] in ids else []
        if isinstance(v, list):
            return [x for item in v for x in refs(item)]
        return []
    for s in plan["steps"]:
        spec = CATALOGUE.get(s["op"])
        nodes.append({"id": s["id"], "op": s["op"], "args": s.get("args", {}), "note": s.get("note"),
                      "returns": spec.returns if spec else "?", "cost": spec.cost if spec else "?", "doc": spec.doc if spec else ""})
        for k, v in (s.get("args") or {}).items():
            for src in refs(v):
                edges.append({"from": src, "to": s["id"], "arg": k})
    ans = plan.get("answer") or {}
    answer_steps = [ans.get("step")] if ans.get("step") else list((ans.get("steps") or {}).values())
    answer_steps = [str(a).split(".")[0] for a in answer_steps if a]
    return {"nodes": nodes, "edges": edges, "answer_steps": answer_steps}


def _run_job(job: dict) -> None:
    req = job["request"]
    job["status"] = "running"; job["started"] = time.time()
    try:
        llm = LLM(model=req.get("model") or DEFAULT_MODEL)
        card = None
        if req["system"] in ("full", "no_verify", "no_interp", "flat", "codegen"):
            try:
                card = _profile(req["path"], req["name"], req.get("description") or "")
            except Exception as e:  # noqa: BLE001
                card = {"error": f"{type(e).__name__}: {e}"}
        res = SYSTEMS[req["system"]](req.get("qid") or "demo", req["path"], req["name"], req.get("description") or None, req["question"], llm=llm, cache=RESULT_CACHE)
        d = asdict(res)
        d["card"] = card
        d["plan_graph"] = _plan_graph(d.get("plan")) if isinstance(d.get("plan"), dict) else None
        d["question"] = req["question"]; d["dataset"] = req["name"]; d["model"] = llm.model
        try:
            ov = {k: v for k, v in (d.get("assumptions") or {}).items() if k in ("directed", "weighted") and isinstance(v, bool)}
            lg = load_graph(req["name"], req["path"], req.get("description") or "", override=ov or None)
            d["viz"] = make_viz(lg, d.get("answer"))
        except Exception as e:  # noqa: BLE001
            d["viz"] = {"error": str(e)}
        job["result"] = json.loads(json.dumps(d, default=str))
        job["status"] = "done"
    except Exception as e:  # noqa: BLE001
        job["status"] = "error"; job["error"] = f"{type(e).__name__}: {e}"; job["traceback"] = traceback.format_exc()
    job["finished"] = time.time()


def _scenes() -> list[dict]:
    out = []
    if not os.path.isdir(SCENES):
        return out
    for fn in sorted(os.listdir(SCENES)):
        if fn.endswith(".json") and not fn.startswith("card_"):
            try:
                out.append(json.load(open(os.path.join(SCENES, fn))))
            except Exception:  # noqa: BLE001
                continue
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=STATIC, **k)

    def log_message(self, fmt, *args):  # quieter
        if "/api/job/" not in (args[0] if args else ""):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/datasets":
                return self._json(_datasets())
            if u.path == "/api/profile":
                st = ensure_loaded(q["path"], q.get("name") or os.path.basename(q["path"]), q.get("description", ""))
                if st["state"] == "ready":
                    card = CARDS.get(_load_key(q["path"], "")) or _profile(q["path"], q.get("name") or os.path.basename(q["path"]), q.get("description", ""))
                    return self._json({"state": "ready", "load": st, "card": card})
                return self._json({"state": st["state"], "load": st, "error": st.get("error")})
            if u.path == "/api/load":
                return self._json(ensure_loaded(q["path"], q.get("name") or os.path.basename(q["path"]), q.get("description", "")))
            if u.path == "/api/status":
                return self._json({"graphs": [{"path": k, **{kk: vv for kk, vv in v.items() if kk != "started"}} for k, v in LOADS.items()],
                                   "cached_results": len(RESULT_CACHE)})
            if u.path.startswith("/api/job/"):
                job = JOBS.get(u.path.rsplit("/", 1)[1])
                return self._json(job or {"status": "unknown"}, 200 if job else 404)
            if u.path == "/api/scenes":
                return self._json(_scenes())
            if u.path == "/api/catalogue":
                return self._json([{"name": s.name, "doc": s.doc, "params": s.params, "returns": s.returns, "cost": s.cost, "tiers": s.tiers} for s in CATALOGUE.values()])
            if u.path == "/api/stages":
                return self._json(STAGES)
            if u.path == "/":
                self.path = "/index.html"
            return super().do_GET()
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        try:
            if u.path == "/api/ask":
                req = json.loads(body or b"{}")
                for k in ("path", "question", "system"):
                    if not req.get(k):
                        return self._json({"error": f"missing {k}"}, 400)
                if req["system"] not in SYSTEMS:
                    return self._json({"error": f"unknown system {req['system']}"}, 400)
                req.setdefault("name", os.path.splitext(os.path.basename(req["path"]))[0])
                jid = uuid.uuid4().hex[:10]
                job = {"id": jid, "status": "queued", "request": req, "created": time.time(), "stages": STAGES.get(req["system"], [])}
                JOBS[jid] = job
                threading.Thread(target=_run_job, args=(job,), daemon=True).start()
                return self._json({"job": jid, "stages": job["stages"]})
            if u.path == "/api/upload":
                fn = os.path.basename(self.headers.get("X-Filename") or f"upload_{int(time.time())}.txt")
                os.makedirs(UPLOADS, exist_ok=True)
                with open(os.path.join(UPLOADS, fn), "wb") as f:
                    f.write(body)
                return self._json({"ok": True, "path": os.path.join(UPLOADS, fn), "name": os.path.splitext(fn)[0]})
            return self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()}, 500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default=os.environ.get("T2R_MODEL", DEFAULT_MODEL))
    ap.add_argument("--preload", default=os.environ.get("T2R_PRELOAD", ""), help="comma-separated dataset names to load at start (or 'all')")
    a = ap.parse_args()
    globals()["DEFAULT_MODEL"] = a.model
    if a.preload:
        want = None if a.preload == "all" else {x.strip() for x in a.preload.split(",") if x.strip()}
        for d in _datasets():
            if want is None or d["name"] in want:
                ensure_loaded(d["path"], d["name"], d.get("description") or "")
                print("preloading", d["name"], flush=True)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"text2answer demo on http://{a.host}:{a.port}  (model {a.model})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
