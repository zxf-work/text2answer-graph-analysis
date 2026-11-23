"""E4 sessions on the real large graphs: what a session costs when loading and recomputing are no longer free.

One session per graph, the same shape on all three: ordinary turns, valid-reuse turns, then the edge file is changed
without a word and two earlier requests are repeated (trap class R3, as in workload_stale.py), then two more turns
that can reuse what was computed after the change. Gold and stale answers are computed by the harness.

Graphs (SNAP): Pokec (1.6M nodes, 30.6M links, directed), LiveJournal (4.8M, 69M, directed), Orkut (3.1M, 117M,
undirected). Paths are taken from the directory given on the command line.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reuse_fault import P  # noqa: E402
from workload import T  # noqa: E402

GRAPHS = [
    {"name": "pokec", "file": "soc-pokec-relationships.txt", "directed": True, "weighted": False,
     "description": "The Pokec social network: each row is a directed friendship from the first user to the second."},
    {"name": "livejournal", "file": "soc-LiveJournal1.txt", "directed": True, "weighted": False,
     "description": "LiveJournal friendships: each row is a directed friendship link from the first user to the second."},
    {"name": "orkut", "file": "com-orkut.ungraph.txt", "directed": False, "weighted": False,
     "description": "Orkut friendships: each row is an undirected friendship between two users; each pair is listed once."},
]

PR = ("pagerank", {})


def top(k, src="@1"):
    return ("top_k", {"map": src, "k": k})


def specs(snap_dir):
    return [{**g, "path": os.path.join(snap_dir, g["file"])} for g in GRAPHS if os.path.exists(os.path.join(snap_dir, g["file"]))]


def sessions(spec):
    d = spec["directed"]
    deg = ("degree", {"mode": "in" if d else "all"})
    links = "incoming friendships" if d else "friends"
    comp = "weakly connected components" if d else "connected components"
    busy = [deg, ("filter_nodes", {"map": "@1", "op": ">", "threshold": 1000}), ("set_size", {"nodes": "@2"})]
    turns = [
        T(f"Which 10 users have the most {links}?", "new", "ranking", [deg, top(10)]),
        T("Who are the top 10 users by PageRank?", "new", "ranking", [PR, top(10)]),
        T("Show the top 20 instead.", "param", "ranking", [PR, top(20)], valid=True),
        T(f"How many {comp} does the network have?", "new", "scalar", [("components", {"mode": "weak"})], field="count"),
        T("Show the PageRank top 10 again.", "repeat", "ranking", [PR, top(10)], event={"type": "append_edges", "targets": [30, 60], "n": "max"},
          trap="R3", stale=[{"version": -1}]),
        T(f"And the 10 users with the most {links} again.", "repeat", "ranking", [deg, top(10)], trap="R3", stale=[{"version": -1}]),
        T("Show the PageRank top 20.", "param", "ranking", [PR, top(20)], valid=True),
        T(f"How many users have more than 1000 {links}?", "new", "scalar", busy, valid=True),
    ]
    out = []
    for t in turns:
        t = dict(t)
        t["steps"] = t["gold"]
        t["gold"] = {"-": P(t["steps"])}
        out.append(t)
    return [{"id": f"{spec['name']}/large", "class": "R3", "graph": spec["name"], "turns": out}]
