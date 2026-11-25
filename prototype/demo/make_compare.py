"""Side-by-side record of one session run by two systems, for demo/static/compare.html. Calls no model.

  python demo/make_compare.py <runs dir of system A> <runs dir of GraphAudit> --session pokec/refresh --name refresh

Each runs dir holds turns.jsonl and run_meta.txt as written by bench/sessions/run_stale.py: the answer of every turn,
the harness's correct answer on the file as it was at that turn, and whether the answer equals the correct answer of an
earlier state of the file (stale). Nothing is recomputed here; the page shows those records.
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = {"codegen_stateful": "Stateful agent", "codegen_stateful_warned": "Stateful agent, warned", "codegen_independent": "Independent agent", "full": "GraphAudit"}
WHAT = {"codegen_stateful": "Writes and runs Python each turn in one process that stays alive, so variables from earlier turns are still there.",
        "codegen_stateful_warned": "The stateful agent, told once that the files may change between turns.",
        "codegen_independent": "Writes and runs a new Python script each turn, with nothing kept.",
        "full": "Plans over checked operators; a stored result is reused only when its lineage, back to the file's content, is unchanged."}


def norm(v):
    """A ranking as a list of node ids (text), anything else as it is."""
    if isinstance(v, dict) and "nodes" in v:
        return {"kind": "ranking", "nodes": [str(x) for x in v["nodes"]]}
    if isinstance(v, list) and v and all(isinstance(x, dict) and "node" in x for x in v):
        return {"kind": "ranking", "nodes": [str(x["node"]) for x in v]}
    if isinstance(v, list) and v and all(isinstance(x, (int, str)) for x in v):
        return {"kind": "ranking", "nodes": [str(x) for x in v]}
    return {"kind": "scalar", "value": v}


def evidence(code):
    """The line of the agent's own code that decides whether an earlier variable is used."""
    lines = code.splitlines()
    for pat in (r"^\s*#.*\b(reuse|still in|earlier|previous|turn \d)", r"not in globals\(\)|in globals\(\)"):
        for ln in lines:
            if re.search(pat, ln, re.I):
                return ln.strip()
    return None


def load(d, session):
    turns = [t for t in map(json.loads, open(os.path.join(d, "turns.jsonl"))) if t["session"] == session]
    meta = dict(kv.split("=", 1) for kv in open(os.path.join(d, "run_meta.txt")).read().split() if "=" in kv)
    v = turns[0]["variant"]
    out = []
    for t in turns:
        r = {"answer": norm(t["answer"]), "correct": bool(t["correct"]), "stale": bool(t["stale"]), "outcome": t["outcome"], "flags": t.get("flags") or [],
             "error": t.get("error"), "steps_reused": t["steps_reused"], "steps_executed": t["steps_executed"], "llm_calls": t["llm_calls"],
             "compute_seconds": t["compute_seconds"], "model_seconds": t["model_seconds"], "setup_seconds": t.get("setup_seconds") or 0, "cost_usd": t["cost_usd"]}
        if isinstance(t["plan"], str):
            r["code"], r["evidence"] = t["plan"], evidence(t["plan"])
        elif isinstance(t["plan"], dict):
            r["steps"] = [{"id": s["id"], "op": s["op"], "args": s.get("args") or {}} for s in t["plan"].get("steps") or []]
        out.append(r)
    tot = {"correct": sum(r["correct"] for r in out), "stale": sum(r["stale"] for r in out), "turns": len(out), "llm_calls": sum(r["llm_calls"] for r in out),
           "compute_seconds": round(sum(r["compute_seconds"] + r["setup_seconds"] for r in out), 1), "cost_usd": round(sum(r["cost_usd"] for r in out), 4)}
    return turns, {"variant": v, "label": LABEL.get(v, v), "what": WHAT.get(v, ""), "model": turns[0]["model"], "commit": meta.get("commit", "")[:7],
                   "job": meta.get("job"), "started": meta.get("started"), "run": os.path.relpath(d), "turns": out, "totals": tot}


ap = argparse.ArgumentParser()
ap.add_argument("a"); ap.add_argument("b"); ap.add_argument("--session", required=True); ap.add_argument("--name", required=True)
ap.add_argument("--title", default=""); ap.add_argument("--file", default="")
a = ap.parse_args()
ta, A = load(a.a, a.session)
tb, B = load(a.b, a.session)
assert [t["q"] for t in ta] == [t["q"] for t in tb], "the two runs are not the same session"
turns = []
for t in ta:
    ev = t.get("event")
    turns.append({"turn": t["turn"], "question": t["q"], "kind": t["kind"], "gold": norm(t["gold"][0]),
                  "event": (f"{ev['edges_added']:,} rows were appended to the edge file: new incoming links for users {' and '.join(ev['targets'])}. Neither system was told."
                            if ev and ev.get("type") == "append_edges" else json.dumps(ev) if ev else None)})
out = os.path.join(HERE, "compare")
os.makedirs(out, exist_ok=True)
doc = {"name": a.name, "session": a.session, "title": a.title or a.session, "file": a.file, "turns": turns, "systems": [A, B]}
json.dump(doc, open(os.path.join(out, a.name + ".json"), "w"), ensure_ascii=False)
json.dump(sorted(f for f in os.listdir(out) if f.endswith(".json") and f != "index.json"), open(os.path.join(out, "index.json"), "w"))
print("wrote", os.path.join(out, a.name + ".json"), [(s["label"], s["totals"]) for s in doc["systems"]])
