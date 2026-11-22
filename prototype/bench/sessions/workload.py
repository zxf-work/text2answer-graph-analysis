"""E2 session workload: annotated multi-turn sessions over attributed and plain graphs.

Each turn carries the question, its kind, the gold plan(s) that define a correct answer, and, when the request has
two scope readings, the reading the (simulated) user means. Gold answers are computed by executing the gold plans,
so they are exact for the graph at hand. `sessions(spec)` builds the sessions that apply to one graph.

Turn kinds: new, drill (uses an earlier result), param (changed parameter), measure (changed measure),
scope (restriction to a group; ambiguous unless stated), repeat.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reuse_fault import P  # noqa: E402


def T(q, kind, expect, gold, **kw):
    """expect: ranking | node | scalar | numbers | map | groups. gold: steps, or {"A": steps, "B": steps} for an ambiguous scope
    turn (then `user` names the reading the user means). `field` picks a field of the final value; `n` the group count."""
    return {"q": q, "kind": kind, "expect": expect, "gold": gold, **kw}


PR = ("pagerank", {})


def top(k, src="@1"):
    return ("top_k", {"map": src, "k": k})


def attributed(spec):
    a, (x, y) = spec["attr"], spec["values"][:2]
    f = lambda v: ("filter_by_attribute", {"attribute": a, "value": v})  # noqa: E731
    in_group_a = lambda m, v, k: [m, f(v), ("restrict_map", {"map": "@1", "nodes": "@2"}), top(k, "@3")]  # noqa: E731
    in_group_b = lambda m, v, k: [f(v), ("induced_subgraph", {"nodes": "@1"}), (m[0], {**m[1], "graph": "@2"}), top(k, "@3")]  # noqa: E731
    din = ("degree", {"mode": "in"})
    yield {"id": "influence", "turns": [
        T("Who are the 10 most influential users by PageRank?", "new", "ranking", [PR, top(10)]),
        T(f"Which {a} is each of them from?", "drill", "map", [PR, top(10), ("attribute_of", {"nodes": "@2", "attribute": a})]),
        T("Show the top 20 instead.", "param", "ranking", [PR, top(20)]),
        T(f'Who are the 10 most influential users within {a} "{x}"?', "scope", "ranking", {"A": in_group_a(PR, x, 10), "B": in_group_b(PR, x, 10)}, user="B"),
        T(f'And within {a} "{y}"?', "scope", "ranking", {"A": in_group_a(PR, y, 10), "B": in_group_b(PR, y, 10)}, user="B", carried=True),
        T(f"Over the whole network, which 5 values of {a} have the highest total PageRank?", "drill", "groups",
          [PR, ("group_by_attribute", {"attribute": a, "values": "@1", "agg": "sum"})], n=5),
        T("Back to the whole network: who are the top 5 users by PageRank?", "repeat", "ranking", [PR, top(5)]),
    ]}
    yield {"id": "degree", "turns": [
        T("Which 10 users have the most incoming friendships?", "new", "ranking", [din, top(10)]),
        T("And which 10 have the most outgoing friendships?", "measure", "ranking", [("degree", {"mode": "out"}), top(10)]),
        T(f'How many users are in {a} "{x}"?', "new", "scalar", [f(x), ("set_size", {"nodes": "@1"})]),
        T("Among them, who has the most incoming friendships?", "scope", "node", {"A": in_group_a(din, x, 1), "B": in_group_b(din, x, 1)}, user="A"),
        T("How many strongly connected components does the whole network have?", "new", "scalar", [("components", {"mode": "strong"})], field="count"),
        T("Show the 10 users with the most incoming friendships again.", "repeat", "ranking", [din, top(10)]),
    ]}
    yield {"id": "attributes", "turns": [
        T("How many users are male and how many are female?", "new", "numbers", [("group_by_attribute", {"attribute": "gender"})], field="count"),
        T("What is the average age for each gender?", "new", "numbers", [("attribute_map", {"attribute": "age"}), ("group_by_attribute", {"attribute": "gender", "values": "@1", "agg": "mean"})], field="mean"),
        T("What is the degeneracy (the largest k for which a k-core exists) of the network?", "new", "scalar", [("max_core", {})], field="k"),
        T("How many users are in that innermost core?", "drill", "scalar", [("max_core", {})], field="size"),
        T("Who are the top 5 users by PageRank?", "new", "ranking", [PR, top(5)]),
        T("How many of those five are male?", "drill", "scalar", [PR, top(5), ("filter_by_attribute", {"attribute": "gender", "value": "male", "nodes": "@2"}), ("set_size", {"nodes": "@3"})]),
    ]}


def plain_directed(spec):
    din = ("degree", {"mode": "in"})
    yield {"id": "ranking", "turns": [
        T("Who are the top 5 nodes by PageRank?", "new", "ranking", [PR, top(5)]),
        T("Show the top 10 instead.", "param", "ranking", [PR, top(10)]),
        T("Rank by the number of incoming links instead: who are the top 10?", "measure", "ranking", [din, top(10)]),
        T("How many strongly connected components are there?", "new", "scalar", [("components", {"mode": "strong"})], field="count"),
        T("Show the PageRank top 5 again.", "repeat", "ranking", [PR, top(5)]),
    ]}


def roads(spec):
    bw = ("betweenness", {"use_weights": True})
    yield {"id": "routes", "turns": [
        T("How long is the shortest route from J0 to J299, in km?", "new", "scalar", [("shortest_path", {"source": "J0", "target": "J299", "use_weights": True})], field="length"),
        T("And from J0 to J150?", "param", "scalar", [("shortest_path", {"source": "J0", "target": "J150", "use_weights": True})], field="length"),
        T("Which junction lies on the most shortest routes, measuring routes in km?", "new", "node", [bw, top(1)]),
        T("Show the top 5 instead.", "param", "ranking", [bw, top(5)]),
        T("How many junctions are within 2 hops of J0?", "new", "scalar", [("k_hop_neighbourhood", {"node": "J0", "k": 2}), ("set_size", {"nodes": "@1"})]),
    ]}


def emails(spec):
    so, si = ("strength", {"mode": "out"}), ("strength", {"mode": "in"})
    yield {"id": "senders", "turns": [
        T("Who sent the most emails?", "new", "node", [so, top(1)]),
        T("Show the top 5 senders instead.", "param", "ranking", [so, top(5)]),
        T("And the top 5 recipients?", "measure", "ranking", [si, top(5)]),
        T("How many emails were sent in total?", "new", "scalar", [("edge_count", {})]),
        T("Show the top 5 senders again.", "repeat", "ranking", [so, top(5)]),
    ]}


def sessions(spec):
    gen = attributed if spec.get("attr") else {"roads": roads, "emails": emails}.get(spec["name"], plain_directed)
    out = []
    for s in gen(spec):
        for t in s["turns"]:
            g = t["gold"]
            t["gold"] = {k: P(v) for k, v in g.items()} if isinstance(g, dict) else {"-": P(g)}
        out.append({**s, "id": f"{spec['name']}/{s['id']}", "graph": spec["name"]})
    return out


# ------------------------------------------------------------------------------------------------------ scoring
def gold_value(expect, val, turn):
    f = turn.get("field")
    if expect in ("ranking", "node"):
        rows = val if isinstance(val, list) else [val]
        return {"nodes": [str(r["node"]) for r in rows], "values": [r["value"] for r in rows]}
    if expect == "scalar":
        return val[f] if f and isinstance(val, dict) else val
    if expect == "numbers":
        return [r[f] for r in val]
    if expect == "map":
        return {str(r["node"]): r["value"] for r in val}
    if expect == "groups":
        return [r["value"] for r in val[:turn.get("n", 5)]]
    raise ValueError(expect)


def _close(a, b):
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))


def _walk(x):
    yield x
    if isinstance(x, dict):
        for v in x.values():
            yield from _walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v)


def _rank_lists(ans):
    """Every ordered list of nodes found in the answer, with values when given."""
    for x in _walk(ans):
        if isinstance(x, list) and x:
            if all(isinstance(r, dict) and "node" in r for r in x):
                yield [str(r["node"]) for r in x], [r.get("value") for r in x]
            elif all(isinstance(r, (str, int)) and not isinstance(r, bool) for r in x):
                yield [str(r) for r in x], None
        elif isinstance(x, dict) and "node" in x:
            yield [str(x["node"])], [x.get("value")]


def matches(expect, gold, ans) -> bool:
    """Whether the system's answer contains the gold answer. Answers may carry extra parts (variants, joined attributes)."""
    if ans is None:
        return False
    if expect in ("ranking", "node"):
        k = len(gold["nodes"])
        for nodes, vals in _rank_lists(ans):
            if expect == "node" and nodes[:1] == gold["nodes"]:
                return True
            if nodes == gold["nodes"]:
                return True
            # ties: same scores in the same order, and the same nodes wherever the gold scores are unique
            if len(nodes) == k and vals and all(v is not None for v in vals) and all(_close(a, b) for a, b in zip(vals, gold["values"])):
                uniq = [i for i, v in enumerate(gold["values"]) if sum(_close(v, w) for w in gold["values"]) == 1 and i < k - 1]
                if all(nodes[i] == gold["nodes"][i] for i in uniq):
                    return True
        return False
    if expect == "scalar":
        return any(_close(x, gold) for x in _walk(ans) if isinstance(x, (int, float, str)) and not isinstance(x, bool))
    if expect == "numbers":
        nums = [x for x in _walk(ans) if isinstance(x, (int, float)) and not isinstance(x, bool)]
        return all(any(_close(x, g) for x in nums) for g in gold)
    if expect == "map":
        got = {}
        for x in _walk(ans):
            if isinstance(x, dict) and "node" in x and "value" in x:
                got.setdefault(str(x["node"]), set()).add(str(x["value"]))
        return all(str(v) in got.get(n, ()) for n, v in gold.items())
    if expect == "groups":
        for x in _walk(ans):
            if isinstance(x, list) and len(x) >= len(gold):
                names = [str(r.get("value")) if isinstance(r, dict) else str(r) for r in x[:len(gold)]]
                if names == [str(g) for g in gold]:
                    return True
        return False
    return False
