"""Sessions an analyst would actually run, on the full Pokec network (1.6M users, 30.6M friendships, with the profile
table: gender, region, age). They exist to measure what a session costs, in model fees and in compute, with and
without reuse; the questions are ordinary follow-ups, not traps (the one file change, in `refresh`, is what a
daily data load looks like).

  campaign   picking accounts for a campaign: one expensive score (PageRank), then many cuts of it
  refresh    a morning dashboard, new friendships arrive, the same dashboard again
  hubs       what happens to the network without its largest hubs
  dashboard  a saved report of five questions run word for word three times, with a data load after the first run

Gold answers are computed by the harness from the plans below.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reuse_fault import P  # noqa: E402
from workload import T  # noqa: E402

GRAPHS = [{"name": "pokec", "file": "soc-pokec-relationships.txt", "directed": True, "weighted": False,
           "description": "The Pokec social network: each row is a directed friendship from the first user to the second. "
                          "The node table gives each user's gender, region and age."}]
PR = ("pagerank", {})
DIN = ("degree", {"mode": "in"})
WCC = [("components", {"mode": "weak"})]


def top(k, src="@1"):
    return ("top_k", {"map": src, "k": k})


def specs(snap_dir):
    return [{**g, "path": os.path.join(snap_dir, g["file"])} for g in GRAPHS if os.path.exists(os.path.join(snap_dir, g["file"]))]


def sessions(spec):
    of = lambda g, k: [PR, ("filter_by_attribute", {"attribute": "gender", "value": g}), ("restrict_map", {"map": "@1", "nodes": "@2"}), top(k, "@3")]  # noqa: E731
    who = lambda a, k=20: [PR, top(k), ("attribute_of", {"nodes": "@2", "attribute": a})]  # noqa: E731
    busy = [DIN, ("filter_nodes", {"map": "@1", "op": ">", "threshold": 1000}), ("set_size", {"nodes": "@2"})]
    cut = [DIN, top(5), ("remove_nodes", {"nodes": "@2"})]
    campaign = [
        T("Who are the 20 most influential users by PageRank?", "new", "ranking", [PR, top(20)]),
        T("What gender is each of them?", "drill", "map", who("gender")),
        T("Which region is each of them from?", "drill", "map", who("region")),
        T("Using the scores computed on the whole network, who are the top 20 among female users?", "scope", "ranking", of("female", 20)),
        T("And, again with the whole-network scores, the top 20 among male users?", "scope", "ranking", of("male", 20)),
        T("Which 5 values of region have the highest average PageRank over their users?", "drill", "groups",
          [PR, ("group_by_attribute", {"attribute": "region", "values": "@1", "agg": "mean"})], n=5),
        T("Show the overall top 50 by PageRank.", "param", "ranking", [PR, top(50)]),
        T("Which 10 users have the most incoming friendships?", "new", "ranking", [DIN, top(10)]),
        T("How many users have more than 1000 incoming friendships?", "new", "scalar", busy),
        T("Show the top 20 by PageRank again.", "repeat", "ranking", [PR, top(20)]),
    ]
    refresh = [
        T("How many weakly connected components does the network have?", "new", "scalar", WCC, field="count"),
        T("Who are the top 10 users by PageRank?", "new", "ranking", [PR, top(10)]),
        T("Which 10 users have the most incoming friendships?", "new", "ranking", [DIN, top(10)]),
        T("How many users have more than 1000 incoming friendships?", "new", "scalar", busy),
        T("Show the PageRank top 10 again.", "repeat", "ranking", [PR, top(10)], event={"type": "append_edges", "targets": [30, 60], "n": "max"},
          trap="R3", stale=[{"version": -1}]),
        T("And the 10 users with the most incoming friendships again.", "repeat", "ranking", [DIN, top(10)], trap="R3", stale=[{"version": -1}]),
        T("How many users have more than 1000 incoming friendships now?", "repeat", "scalar", busy, trap="R3", stale=[{"version": -1}]),
        T("How many weakly connected components does the network have?", "repeat", "scalar", WCC, field="count"),
        T("Show the PageRank top 20.", "param", "ranking", [PR, top(20)]),
        T("Show the PageRank top 10 once more.", "repeat", "ranking", [PR, top(10)]),
    ]
    hubs = [
        T("How many weakly connected components does the network have?", "new", "scalar", WCC, field="count"),
        T("Which 10 users have the most incoming friendships?", "new", "ranking", [DIN, top(10)]),
        T("Remove the 5 users with the most incoming friendships. How many weakly connected components does the rest of the network have?", "new", "scalar",
          cut + [("components", {"graph": "@3", "mode": "weak"})], field="count"),
        T("In the network without those 5 users, who are the top 10 by PageRank?", "new", "ranking", cut + [("pagerank", {"graph": "@3"}), top(10, "@4")]),
        T("On the full network again, who are the top 10 by PageRank?", "new", "ranking", [PR, top(10)]),
        T("Without those 5 users again: how many weakly connected components?", "repeat", "scalar", cut + [("components", {"graph": "@3", "mode": "weak"})], field="count"),
        T("And without them, the PageRank top 20?", "param", "ranking", cut + [("pagerank", {"graph": "@3"}), top(20, "@4")]),
        T("How many users does the full network have?", "new", "scalar", [("node_count", {})]),
    ]
    # a saved report: the same five questions, word for word, in the morning, after the day's new friendships are loaded,
    # and once more with nothing changed
    report = [("How many weakly connected components does the network have?", "scalar", WCC, {"field": "count"}),
              ("Who are the top 10 users by PageRank?", "ranking", [PR, top(10)], {}),
              ("Which 10 users have the most incoming friendships?", "ranking", [DIN, top(10)], {}),
              ("How many users have more than 1000 incoming friendships?", "scalar", busy, {}),
              ("Which 5 values of region have the highest average PageRank over their users?", "groups",
               [PR, ("group_by_attribute", {"attribute": "region", "values": "@1", "agg": "mean"})], {"n": 5})]
    dashboard = []
    for rnd in range(3):
        for j, (q, kind, plan, kw) in enumerate(report):
            extra = dict(kw)
            if rnd == 1 and j == 0:
                extra["event"] = {"type": "append_edges", "targets": [30, 60], "n": "max"}
            if rnd == 1 and j in (1, 2, 3):                       # the three whose answer the new rows are known to change
                extra.update(trap="R3", stale=[{"version": -1}])
            dashboard.append(T(q, "new" if rnd == 0 else "repeat", kind, plan, **extra))
    out = []
    for name, turns in (("campaign", campaign), ("refresh", refresh), ("hubs", hubs), ("dashboard", dashboard)):
        ts = []
        for t in turns:
            t = dict(t)
            t["steps"] = t["gold"]
            t["gold"] = {"-": P(t["steps"])}
            ts.append(t)
        out.append({"id": f"{spec['name']}/{name}", "class": "practice", "graph": spec["name"], "turns": ts})
    return out
