"""Graph visualisation data for the demo: a small neighbourhood around the answer nodes, laid out server-side.

make_viz(lg, answer) -> {"nodes": [{id, label, x, y, deg, role, rank}], "edges": [{s, t, hl}], ...}
role is "answer" (a node named in the answer, with its rank), "path" (on a returned path) or "context".
The front end only draws; no layout work happens in the browser, so the same JSON serves the static preview.
"""
from __future__ import annotations

import math
import random
from typing import Any

MAX_NODES = 140


def extract_nodes(answer: Any, depth: int = 0) -> tuple[list[str], list[list[str]]]:
    """Node labels named by an answer (in rank order) and any paths it contains."""
    nodes: list[str] = []; paths: list[list[str]] = []
    if answer is None or depth > 4:
        return nodes, paths
    if isinstance(answer, list):
        if answer and all(isinstance(x, dict) and "node" in x for x in answer):
            nodes += [str(x["node"]) for x in answer]
        elif answer and all(isinstance(x, (str, int)) for x in answer):
            nodes += [str(x) for x in answer]
        else:
            for x in answer:
                n, p = extract_nodes(x, depth + 1); nodes += n; paths += p
    elif isinstance(answer, dict):
        if isinstance(answer.get("path"), list) and all(isinstance(x, (str, int)) for x in answer["path"]):
            paths.append([str(x) for x in answer["path"]])
        if "node" in answer and isinstance(answer["node"], (str, int)):
            nodes.append(str(answer["node"]))
        for k, v in answer.items():
            if k in ("path", "node"):
                continue
            n, p = extract_nodes(v, depth + 1); nodes += n; paths += p
    elif isinstance(answer, str) and len(answer) <= 40 and " " not in answer:
        nodes.append(answer)
    seen: set[str] = set(); out: list[str] = []
    for n in nodes:
        if n not in seen:
            seen.add(n); out.append(n)
    return out, paths


def make_viz(lg, answer: Any = None, limit: int = MAX_NODES, seed: int = 7) -> dict[str, Any]:
    g = lg.g
    n_total, m_total = g.vcount(), g.ecount()
    labels, paths = extract_nodes(answer)
    ids: dict[int, str] = {}
    rank: dict[int, int] = {}
    for i, lab in enumerate(labels[:30]):
        r = lg.resolve(lab)
        if r.get("matched") is not None:
            ids[r["matched"]] = lab; rank.setdefault(r["matched"], i + 1)
    path_vids: list[list[int]] = []
    for p in paths:
        vp = []
        for lab in p:
            r = lg.resolve(lab)
            if r.get("matched") is not None:
                vp.append(r["matched"]); ids.setdefault(r["matched"], lab)
        if len(vp) >= 2:
            path_vids.append(vp)
    on_path = {v for p in path_vids for v in p}
    rng = random.Random(seed)
    note = ""
    if not ids:
        # nothing to highlight: show the neighbourhood of the highest-degree nodes
        deg = g.degree()
        hubs = sorted(range(n_total), key=lambda v: -deg[v])[:6]
        seeds = hubs
        note = "The answer names no nodes; showing the neighbourhood of the highest-degree nodes."
    else:
        seeds = list(ids)
    chosen: list[int] = []
    cs: set[int] = set()
    for v in seeds:
        if v not in cs:
            cs.add(v); chosen.append(v)
    for v in on_path:
        if v not in cs:
            cs.add(v); chosen.append(v)
    # grow: a few neighbours of each seed first, then of what was added, until the budget is spent
    frontier = list(chosen)
    per = max(2, (limit - len(chosen)) // max(1, len(chosen)))
    while frontier and len(chosen) < limit:
        nxt: list[int] = []
        for v in frontier:
            nb = g.neighbors(v, mode="all")
            if len(nb) > per:
                nb = rng.sample(nb, per)
            for u in nb:
                if u not in cs and len(chosen) < limit:
                    cs.add(u); chosen.append(u); nxt.append(u)
        frontier = nxt; per = 2
    chosen = sorted(cs)  # igraph's induced_subgraph orders vertices by original id, so index i in sub is chosen[i] only when sorted
    sub = g.induced_subgraph(chosen)
    try:
        lay = sub.layout_fruchterman_reingold(niter=400, seed=None) if sub.vcount() > 2 else sub.layout_circle()
    except Exception:  # noqa: BLE001
        lay = sub.layout_circle()
    xs = [c[0] for c in lay]; ys = [c[1] for c in lay]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    sx = (maxx - minx) or 1.0; sy = (maxy - miny) or 1.0
    deg_full = g.degree(chosen)
    nodes = []
    for i, v in enumerate(chosen):
        role = "answer" if v in ids and rank.get(v) else ("path" if v in on_path else "context")
        if v in ids and not rank.get(v):
            role = "path" if v in on_path else "answer"
        nodes.append({"id": i, "label": lg.labels[v], "x": round((xs[i] - minx) / sx, 4), "y": round((ys[i] - miny) / sy, 4),
                      "deg": int(deg_full[i]), "role": role, "rank": rank.get(v)})
    path_edges = set()
    for p in path_vids:
        for a, b in zip(p, p[1:]):
            path_edges.add((a, b)); path_edges.add((b, a))
    edges = []
    for e in sub.es:
        a, b = chosen[e.source], chosen[e.target]
        edges.append({"s": e.source, "t": e.target, "hl": (a, b) in path_edges})
    if len(edges) > 900:
        keep = [e for e in edges if e["hl"] or nodes[e["s"]]["role"] != "context" or nodes[e["t"]]["role"] != "context"]
        rest = [e for e in edges if e not in keep]
        rng.shuffle(rest); edges = keep + rest[: max(0, 900 - len(keep))]
    return {"nodes": nodes, "edges": edges, "directed": g.is_directed(), "n_total": n_total, "m_total": m_total,
            "n_shown": len(nodes), "m_shown": len(edges), "highlighted": len(ids), "paths": len(path_vids), "note": note}
