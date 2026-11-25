"""Checked code fallback for a request the catalogue cannot compute (the planner said "unsupported").

What is checked, and what is not:
  1. The inputs are prepared by catalogue operators (selecting nodes, inducing a subgraph, dropping direction), under
     the same validation, reuse and cost rules as any plan. The generated code never reads the file, so how the graph
     is loaded and read is not left to it.
  2. Two functions are written by two separate model calls that do not see each other, with different instructions
     about which library to use, and are run on the same inputs in separate processes.
  3. The value is returned only when both give the same value ("answer by code"). Otherwise the turn is "unconfirmed":
     no answer, both candidates shown.
Not checked: that the task statement handed to the two writers says what the user meant (both writers read the same
statement), and the witness (members, path, order), which may differ between two correct solutions.
Results of the generated code are not stored for reuse; the prepared inputs are, like any step result.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import subprocess
import sys
import tempfile
import time
from typing import Any

import igraph as ig
import numpy as np

from .ir import auto_tier, execute, validate
from .llm import parse_json
from .ops import _edges
from .systems import _extract_code, _jsonable, _last_json

PREP = """

Your plan for this request was "unsupported": {reason}
The missing part will now be computed by a short Python function instead. Return a plan in the same JSON format with:
- "steps": catalogue operators only, preparing the inputs the function needs and nothing more: select the nodes, induce the subgraph, drop direction (undirected_graph) or keep only mutual links (mutual_graph), compute degrees or attributes the function needs. Rules S1 to S3 apply (copy unchanged steps of earlier turns, resolve references). An empty list is right when the function needs only the whole graph.
- "code_inputs": {{"<python name>": "<step id>" or "G"}}: the values handed to the function. Hand over the smallest inputs that suffice (an induced subgraph of 50 nodes, not the whole graph and a list of 50 ids); "G" is the whole graph as loaded.
- "code_task": what the function must compute from exactly these inputs, in one to three precise sentences that a programmer can implement without seeing the conversation: the quantity, how direction counts in the inputs as handed over, tie-breaking, the starting node if any, and what to return as the value (the number, yes/no or list asked for) and as the witness (members, path or order, when the user asked for one).
- "unsupported": null, "answer": null, "clarification": null. Keep "interpretation" and the session fields as usual.
The function must return the value the user asked for, in the unit the user named (a question about regions is answered per region, not per a coarser grouping used in an earlier turn). If an input that value needs cannot be prepared from the data as it is now (for example a result on the data before a change, which is no longer stored), do not hand over a task that returns something else: return "unsupported" again with that reason, with "steps": [] and no "code_task"."""

WRITER = """You write one Python function for a graph analysis tool. It runs in a fresh process with Python 3, python-igraph, networkx 3, numpy and scipy.

def solve(inputs: dict) -> dict

The entries of `inputs` are described in the message. Kinds of entries:
- graph: {{"directed": bool, "nodes": [id, ...], "edges": numpy int array of shape (m, 2) whose entries are positions in "nodes", "attributes": {{name: [one value per node]}}}}. Two helpers are already defined: to_igraph(graph) (vertex attribute "name" holds the id, the other attributes are copied) and to_networkx(graph) (the nodes are the ids, attributes copied; DiGraph if directed).
- node set: list of ids. node map: dict id -> value. table: list of dicts. scalar: number, string or boolean.
Node ids are strings. Return ids exactly as given. When the task orders or compares ids ("lowest id first", ties by id) and the ids are whole numbers written as strings, compare them as numbers, not as text.

Return {{"value": <exactly the quantity asked for: a number, a boolean, a string, or a list or dict of them>, "witness": <the members, path or order that shows the value, when the task asks for one; else null>, "method": "<algorithm used>"}}.
The result must be exact. If an exact result is not feasible for inputs of this size, raise NotImplementedError with the reason; never return an approximation or a heuristic result.
{style}
Reply with only the function and its imports inside a ```python fence."""

STYLES = ("Prefer igraph's built-in algorithms for the core computation.",
          "For the core computation prefer networkx, scipy, or a direct implementation of your own over igraph's built-in routine, so that the result does not depend on igraph's implementation.")

HARNESS = r'''
import json, pickle, sys
import numpy as np

def to_igraph(x):
    import igraph as ig
    g = ig.Graph(n=len(x["nodes"]), edges=x["edges"], directed=x["directed"])
    g.vs["name"] = x["nodes"]
    for k, v in x["attributes"].items():
        g.vs[k] = v
    return g

def to_networkx(x):
    import networkx as nx
    G = nx.DiGraph() if x["directed"] else nx.Graph()
    names = x["nodes"]
    G.add_nodes_from(names)
    for k, v in x["attributes"].items():
        nx.set_node_attributes(G, dict(zip(names, v)), k)
    G.add_edges_from((names[a], names[b]) for a, b in x["edges"].tolist())
    return G

def _plain(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, (set, frozenset, tuple, np.ndarray)):
        return list(o)
    return str(o)

with open(sys.argv[1], "rb") as _f:
    inputs = pickle.load(_f)
exec(compile(open(sys.argv[2]).read(), "solve.py", "exec"))
print(json.dumps(solve(inputs), default=_plain))
'''


def export(val: Any) -> tuple[Any, str]:
    """A step value as plain data for the function, and one line describing it to the writer."""
    if hasattr(val, "g") and isinstance(getattr(val, "g"), ig.Graph):     # the loaded graph
        val = val.g
    if isinstance(val, ig.Graph):
        attrs = {a: val.vs[a] for a in val.vs.attributes() if a != "name"}
        names = [str(x) for x in val.vs["name"]] if "name" in val.vs.attributes() else [str(i) for i in range(val.vcount())]
        edges = np.column_stack(_edges(val)).astype(np.int64)
        ex = {a: next((x for x in v if x is not None), None) for a, v in attrs.items()}
        return ({"directed": val.is_directed(), "nodes": names, "edges": edges, "attributes": attrs},
                f"graph, {'directed' if val.is_directed() else 'undirected'}, {val.vcount()} nodes, {val.ecount()} edges, node attributes with an example value: {json.dumps(ex, default=str)}")
    if isinstance(val, dict):
        return val, f"dict with {len(val)} entries (a node map if the keys are node ids), the first: {json.dumps(dict(list(val.items())[:3]), default=str)[:300]}"
    if isinstance(val, list):
        kind = "table" if val and isinstance(val[0], dict) else "node set"
        return val, f"{kind} with {len(val)} entries, the first: {json.dumps(val[:3], default=str)[:300]}"
    return _jsonable(val), f"value: {json.dumps(_jsonable(val), default=str)[:400]}"


def same_value(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().casefold() == b.strip().casefold()
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same_value(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return set(map(str, a)) == set(map(str, b)) and all(same_value(v, b.get(k, b.get(str(k)))) for k, v in a.items())
    return a is None and b is None


def run_code(code: str, pkl: str, timeout: int) -> tuple[Any, str, float]:
    """-> (result object or None, error text, seconds)"""
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        for name, text in (("harness.py", HARNESS), ("solve.py", code)):
            with open(os.path.join(d, name), "w") as f:
                f.write(text)
        mem_kb = int(os.environ.get("T2R_SCRIPT_MEM_MB", "24000")) * 1024
        try:
            r = subprocess.run(["bash", "-c", f"ulimit -v {mem_kb}; exec {sys.executable} -I harness.py {pkl} solve.py"], capture_output=True, text=True, timeout=timeout, cwd=d)
        except subprocess.TimeoutExpired:
            return None, f"timeout after {timeout}s", time.time() - t0
    res = _last_json(r.stdout) if r.returncode == 0 else None
    if res is None or "value" not in res:
        return None, (r.stderr.strip().splitlines() or ["no result object printed"])[-1][:600] if r.returncode else "the function did not return {'value': ...}", time.time() - t0
    return res, "", time.time() - t0


def write_and_run(llm, task: str, described: str, style: str, pkl: str, timeout: int) -> dict[str, Any]:
    system = WRITER.format(style=style)
    user = f"Task: {task}\n\nInputs:\n{described}"
    code = _extract_code(llm.chat(system, user).text)
    res, err, secs = run_code(code, pkl, timeout)
    repaired = False
    if res is None and not err.startswith("timeout") and "NotImplementedError" not in err:
        repaired = True
        code = _extract_code(llm.chat(system, user + f"\n\nYour function failed:\n```python\n{code}\n```\nError: {err}\nReturn a corrected function.").text)
        res, err, more = run_code(code, pkl, timeout)
        secs += more
    return {"code": code, "value": (res or {}).get("value"), "witness": (res or {}).get("witness"), "method": (res or {}).get("method"),
            "error": err or None, "seconds": round(secs, 3), "repaired": repaired, "ok": res is not None}


def run_fallback(session, turn: dict, question: str, llm) -> dict:
    """Turn an "unsupported" turn into "answer by code" (two scripts agree) or "unconfirmed" (they do not, or one failed)."""
    from .session import TurnPlan, conventions          # session imports this module lazily
    reason = turn["unsupported"]
    timeout = int(os.environ.get("T2R_FALLBACK_TIMEOUT", "300"))
    t0 = time.time()
    session.turns.remove(turn)                          # the prompt describes the session as it was when the turn was asked
    try:
        fixed_sys, fixed_user, system, user = session._prompt(question)
    finally:
        session.turns.append(turn)
    reply = llm.chat(system, user + PREP.format(reason=reason), fixed_system=fixed_sys, fixed_user=fixed_user).text
    plan = TurnPlan.model_validate(parse_json(reply))
    task, names = plan.code_task, dict(plan.code_inputs or {})
    if plan.unsupported and not task:                   # the inputs cannot be prepared either: the turn stays unsupported
        turn["unsupported"] = plan.unsupported
        turn["code"] = {"declined": plan.unsupported}
        return turn
    plan.unsupported, plan.answer, plan.clarification = reason, None, None
    lg, _ = session._graph_for(plan)
    ids = {s.id for s in plan.steps} | {"G"}
    problems = validate(plan, lg, session.budget_ops) + [f"code_inputs: {k} refers to unknown step {v}" for k, v in names.items() if v not in ids]
    if not task or not names:
        problems.append("code_task and code_inputs are required")
    turn["code"] = {"task": task, "inputs": names}
    if problems:
        turn["code"]["error"] = "the inputs could not be prepared: " + "; ".join(problems)
        return turn
    auto_tier(plan, lg, session.budget_ops)
    ctx, trace = execute(plan, lg, seed=session.seed, cache=session.store if session.reuse else None)
    data, lines = {}, []
    for name, ref in names.items():
        data[name], line = export(lg if ref == "G" else ctx.values[ref])
        lines.append(f"- inputs[{json.dumps(name)}] ({'the whole graph as loaded' if ref == 'G' else 'from step ' + ref}): {line}")
    with tempfile.TemporaryDirectory() as d:
        pkl = os.path.join(d, "inputs.pkl")
        with open(pkl, "wb") as f:
            pickle.dump(data, f, protocol=4)
        runs = [write_and_run(llm, task, "\n".join(lines), style, pkl, timeout) for style in STYLES]
    agree = all(r["ok"] for r in runs) and same_value(runs[0]["value"], runs[1]["value"])
    reused = sum(t["cached"] for t in trace)
    turn.update({"plan": plan.model_dump(), "trace": trace, "steps_reused": reused, "steps_executed": len(trace) - reused,
                 "seconds_saved": round(sum(t.get("seconds_saved", 0) for t in trace), 3),
                 "execute_seconds": round(time.time() - t0, 3), "sizes": {}, "findings": [
                     {"check": "outside_catalogue", "ok": False, "severity": "warn",
                      "detail": f"no operator computes this ({reason}); the value comes from generated code run on inputs prepared by {len(trace)} checked step{'s' if len(trace) != 1 else ''}"},
                     {"check": "code_cross_check", "ok": agree, "severity": "info" if agree else "error",
                      "detail": "two functions written separately give the same value" if agree else
                      "two functions written separately do not give the same value: " + "; ".join(r["error"] or json.dumps(r["value"], default=str)[:120] for r in runs)}]})
    turn["code"].update({"input_lines": lines, "scripts": runs, "agree": agree})
    turn["conventions"] = conventions(lg)
    if agree:
        turn["outcome"] = "answer by code"
        turn["answer"] = _jsonable({"value": runs[0]["value"], "witness": runs[0]["witness"]} if runs[0]["witness"] is not None else runs[0]["value"])
        turn["answer_value"] = _jsonable(runs[0]["value"])
    else:
        turn["outcome"] = "unconfirmed"
        turn["candidates"] = [_jsonable(r["value"]) for r in runs if r["ok"]]
    return turn
