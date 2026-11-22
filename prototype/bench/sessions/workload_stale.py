"""E2b workload: sessions in which an earlier result looks reusable but is not.

Every session builds some state, then something changes (the reading of the graph, the file, a name is reused for
another group, an upstream parameter, the graph is cut), then come **trap turns**, whose correct answer needs the
new state while an outdated one is at hand, and **valid-reuse turns**, where an earlier result is right to reuse.

A turn is T(...) from workload.py plus:
  event    applied to the files before the turn: {"type": "append_edges" | "edit_table", ...}
  reading  the reading of the graph from this turn on (a load override), e.g. {"directed": False}
  trap     the class (R1..R6) when this is a trap turn
  stale    what an outdated state would answer: a list of {"plan": steps (default: the turn's gold), "version": k
           (file version, default: current; negative counts back from the current one), "reading": {...}}
  valid    True when an earlier result is valid to reuse here
Gold and stale answers are computed by the harness on the file version and reading in force. Wording and gold were
written before any system was run on them and are not to be changed after.

Classes: R1 reading changed; R2 data changed, announced; R3 data changed, not announced; R4 a name reused for another
group; R5 an upstream parameter changed; R6 the graph was cut.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reuse_fault import P  # noqa: E402
from workload import T  # noqa: E402

PR = ("pagerank", {})
DIN = ("degree", {"mode": "in"})
UND = {"directed": False}


def top(k, src="@1"):
    return ("top_k", {"map": src, "k": k})


def reading_plain(spec, unit="links"):
    """R1 on a directed graph without attributes."""
    return {"id": "reading", "class": "R1", "turns": [
        T("Who are the top 10 nodes by PageRank?", "new", "ranking", [PR, top(10)]),
        T(f"From now on treat every link as mutual, ignoring its direction. Who are the top 10 by PageRank now?", "new", "ranking", [PR, top(10)], reading=UND),
        T(f"Which 10 nodes have the most {unit}?", "new", "ranking", [("degree", {"mode": "all"}), top(10)], trap="R1", stale=[{"reading": {"directed": True}}]),
        T("Show the PageRank top 5.", "param", "ranking", [PR, top(5)], trap="R1", stale=[{"reading": {"directed": True}}]),
        T("Go back to reading the links as directed. Who are the top 10 by PageRank?", "repeat", "ranking", [PR, top(10)], reading={"directed": True}, valid=True),
    ]}


def cut_plain(spec, who="nodes", unit="incoming links"):
    """R6 on a directed graph without attributes."""
    cut = [DIN, top(5), ("remove_nodes", {"nodes": "@2"})]
    return {"id": "cut", "class": "R6", "turns": [
        T("How many weakly connected components does the network have?", "new", "scalar", [("components", {"mode": "weak"})], field="count"),
        T(f"Remove the 5 {who} with the most {unit}. How many weakly connected components does the rest of the network have?", "new", "scalar",
          cut + [("components", {"graph": "@3", "mode": "weak"})], field="count"),
        T(f"On the full network again: which 10 {who} have the most {unit}?", "new", "ranking", [DIN, top(10)], trap="R6",
          stale=[{"plan": cut + [("degree", {"graph": "@3", "mode": "in"}), top(10, "@4")]}]),
        T(f"How many {who} does the full network have?", "new", "scalar", [("node_count", {})], trap="R6", stale=[{"plan": cut + [("node_count", {"graph": "@3"})]}]),
        T(f"Without those 5 {who} again: how many weakly connected components?", "repeat", "scalar", cut + [("components", {"graph": "@3", "mode": "weak"})], field="count", valid=True),
    ]}


def attributed(spec):
    a, (x, y) = spec["attr"], spec["values"][:2]
    f = lambda v: ("filter_by_attribute", {"attribute": a, "value": v})  # noqa: E731
    inside = lambda v, k: [f(v), ("induced_subgraph", {"nodes": "@1"}), ("pagerank", {"graph": "@2"}), top(k, "@3")]  # noqa: E731
    boost = {"type": "append_edges", "targets": [30, 60], "n": 3000}
    pr5 = ("pagerank", {"damping": 0.5})

    r = reading_plain(spec)
    r["turns"] = [dict(t) for t in r["turns"]]
    for t, q in zip(r["turns"], ["Who are the 10 most influential users by PageRank?",
                                 "From now on treat every friendship as mutual, ignoring its direction. Who are the top 10 by PageRank now?",
                                 "Which 10 users have the most friends?", None, "Go back to reading friendships as directed. Who are the top 10 by PageRank?"]):
        t["q"] = q or t["q"]
    r["turns"].insert(4, T(f"Which {a} is each of the PageRank top 10 from?", "drill", "map", [PR, top(10), ("attribute_of", {"nodes": "@2", "attribute": a})],
                           trap="R1", stale=[{"reading": {"directed": True}}]))
    yield r

    yield {"id": "append", "class": "R2", "turns": [
        T("Which 10 users have the most incoming friendships?", "new", "ranking", [DIN, top(10)]),
        T("Who are the top 10 users by PageRank?", "new", "ranking", [PR, top(10)]),
        T("I have appended new friendships to the file. Which 10 users have the most incoming friendships now?", "repeat", "ranking", [DIN, top(10)],
          event=boost, trap="R2", stale=[{"version": -1}]),
        T("And who are the top 10 by PageRank?", "repeat", "ranking", [PR, top(10)], trap="R2", stale=[{"version": -1}]),
        T("Show the 10 users with the most incoming friendships again.", "repeat", "ranking", [DIN, top(10)], valid=True),
    ]}

    count_x = [f(x), ("set_size", {"nodes": "@1"})]
    yield {"id": "silent", "class": "R3", "turns": [
        T("Which 10 users have the most incoming friendships?", "new", "ranking", [DIN, top(10)]),
        T(f'How many users are in {a} "{x}"?', "new", "scalar", count_x),
        T("Who are the top 10 users by PageRank?", "new", "ranking", [PR, top(10)], event=boost, trap="R3", stale=[{"version": -1}]),
        T("Show the 10 users with the most incoming friendships again.", "repeat", "ranking", [DIN, top(10)], trap="R3", stale=[{"version": -1}]),
        T(f'How many users are in {a} "{x}"?', "repeat", "scalar", count_x, event={"type": "edit_table", "attribute": a, "from": y, "to": x, "n": 300},
          trap="R3", stale=[{"version": -1}]),
        T("Who are the top 10 users by PageRank?", "repeat", "ranking", [PR, top(10)], valid=True),
    ]}

    yield {"id": "shadow", "class": "R4", "turns": [
        T(f'Consider only the users in {a} "{x}" and the friendships among them. Who are the 10 most influential of them by PageRank?', "new", "ranking", inside(x, 10)),
        T(f'The same for {a} "{y}".', "param", "ranking", inside(y, 10)),
        T("How many of those 10 are male?", "drill", "scalar", inside(y, 10) + [("filter_by_attribute", {"attribute": "gender", "value": "male", "nodes": "@4"}), ("set_size", {"nodes": "@5"})]),
        T(f'Back to "{x}": which 5 were on top there?', "repeat", "ranking", inside(x, 5), trap="R4", stale=[{"plan": inside(y, 5)}]),
        T("And over the whole network, with all friendships, who are the top 10 by PageRank?", "new", "ranking", [PR, top(10)], trap="R4",
          stale=[{"plan": inside(x, 10)}, {"plan": inside(y, 10)}]),
        T(f'Show the top 10 of "{y}" again.', "repeat", "ranking", inside(y, 10), valid=True),
    ]}

    in_x = lambda m, k: [m, f(x), ("restrict_map", {"map": "@1", "nodes": "@2"}), top(k, "@3")]  # noqa: E731
    mean = lambda m: [m, ("group_by_attribute", {"attribute": a, "values": "@1", "agg": "mean"})]  # noqa: E731
    yield {"id": "upstream", "class": "R5", "turns": [
        T("Who are the 10 most influential users by PageRank?", "new", "ranking", [PR, top(10)]),
        T(f"Which 5 values of {a} have the highest average PageRank over their users?", "drill", "groups", mean(PR), n=5),
        T("From now on use a damping factor of 0.5 for PageRank. Who are the top 10?", "param", "ranking", [pr5, top(10)]),
        T(f'Using the scores computed on the whole network, who are the top 20 among the users of {a} "{x}"?', "scope", "ranking", in_x(pr5, 20),
          trap="R5", stale=[{"plan": in_x(PR, 20)}]),
        T(f"Which 5 values of {a} have the highest average PageRank over their users?", "repeat", "groups", mean(pr5), n=5, trap="R5", stale=[{"plan": mean(PR)}]),
        T("Use the standard damping factor of 0.85 again. Who are the top 10?", "repeat", "ranking", [PR, top(10)], valid=True),
    ]}

    yield cut_plain(spec, "users", "incoming friendships")


def sessions(spec):
    if spec.get("attr"):
        gen = list(attributed(spec))
    elif spec["name"] in ("follows", "citations"):
        gen = [reading_plain(spec), cut_plain(spec)]
    else:
        gen = []
    out = []
    for s in gen:
        turns = []
        for t in s["turns"]:
            t = dict(t)
            t["steps"] = t["gold"]
            t["gold"] = {"-": P(t["steps"])}
            turns.append(t)
        out.append({**s, "turns": turns, "id": f"{spec['name']}/{s['id']}", "graph": spec["name"]})
    return out
