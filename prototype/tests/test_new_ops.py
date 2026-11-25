"""The operators added for questions we did not write (edges between groups, neighbours' values, map arithmetic, quantiles,
correlation, text filters): each checked against a direct computation on a small random graph with a node table."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t2r.graphs import load_graph  # noqa: E402
from t2r.ir import Plan, execute, validate  # noqa: E402

N = 120


def build(tmp_path, directed):
    rng = np.random.default_rng(3)
    pairs = {(int(a), int(b)) for a, b in rng.integers(0, N, size=(900, 2)) if a != b}
    if not directed:
        pairs = {(min(a, b), max(a, b)) for a, b in pairs}
    p = str(tmp_path / "e.txt")
    with open(p, "w") as f:
        f.writelines(f"{a}\t{b}\n" for a, b in sorted(pairs))
    lang = ["EN", "DE", "FR"]
    rows = {i: (lang[i % 3], int(rng.integers(1, 1000)), f"20{10 + i % 9}-0{1 + i % 9}-15") for i in range(N)}
    with open(str(tmp_path / "e.nodes.tsv"), "w") as f:
        f.write("id\tlang\tviews\tcreated\n")
        f.writelines(f"{i}\t{r[0]}\t{r[1]}\t{r[2]}\n" for i, r in rows.items())
    lg = load_graph("g", p, "test", override={"directed": directed, "weighted": False})
    return lg, pairs, rows


def run(lg, steps):
    plan = Plan.model_validate({"steps": [{"id": i, "op": op, "args": a} for i, op, a in steps], "answer": {"step": steps[-1][0]}})
    assert validate(plan, lg, 1e12) == []
    ctx, _ = execute(plan, lg)
    return ctx.values


@pytest.mark.parametrize("directed", [True, False])
def test_edges_between_groups_and_mixing(tmp_path, directed):
    lg, pairs, rows = build(tmp_path, directed)
    L = lambda i: rows[i][0]  # noqa: E731
    v = run(lg, [("en", "filter_by_attribute", {"attribute": "lang", "value": "EN"}), ("de", "filter_by_attribute", {"attribute": "lang", "value": "DE"}),
                 ("x", "edges_between", {"a": "en", "b": "de"}), ("i", "edges_between", {"a": "en", "b": "en"}), ("t", "edges_touching", {"nodes": "en"}),
                 ("m", "mixing_matrix", {"attribute": "lang"}), ("r", "attribute_assortativity", {"attribute": "lang"}),
                 ("tot", "edge_count", {}), ("share", "arithmetic", {"a": "t", "op": "/", "b": "tot"})])
    cross = sum(L(a) == "EN" and L(b) == "DE" or (not directed and L(a) == "DE" and L(b) == "EN") for a, b in pairs)
    assert v["x"] == cross and v["i"] == sum(L(a) == L(b) == "EN" for a, b in pairs)
    assert v["t"] == sum("EN" in (L(a), L(b)) for a, b in pairs) and v["share"] == pytest.approx(v["t"] / len(pairs))
    cell = {(r["a"], r["b"]): r["count"] for r in v["m"]}
    assert sum(cell.values()) == len(pairs)
    assert cell[("EN", "EN")] == v["i"] and (cell[("EN", "DE")] if directed else cell[("DE", "EN")]) == cross
    import networkx as nx
    G = (nx.DiGraph if directed else nx.Graph)(list(pairs))
    nx.set_node_attributes(G, {i: L(i) for i in G}, "lang")
    assert v["r"] == pytest.approx(nx.attribute_assortativity_coefficient(G, "lang"), abs=1e-9)


@pytest.mark.parametrize("directed", [True, False])
def test_neighbour_values_and_map_arithmetic(tmp_path, directed):
    lg, pairs, rows = build(tmp_path, directed)
    out = {i: set() for i in range(N)}
    for a, b in pairs:
        out[a].add(b)
        if not directed:
            out[b].add(a)
    v = run(lg, [("en", "filter_by_attribute", {"attribute": "lang", "value": "EN"}), ("k", "neighbours_in_set", {"nodes": "en", "mode": "out"}),
                 ("d", "degree", {"mode": "out"}), ("s", "map_arithmetic", {"a": "k", "op": "/", "b": "d"}), ("views", "attribute_map", {"attribute": "views"}),
                 ("nv", "neighbour_aggregate", {"values": "views", "agg": "mean", "mode": "out"}), ("twice", "map_arithmetic", {"a": "d", "op": "*", "b": 2}),
                 ("top", "top_k", {"map": "d", "k": 5}), ("reach", "neighbourhood_of_set", {"nodes": "top", "k": 2, "mode": "out"})])
    for i in range(N):
        nb = out[i]
        if str(i) not in v["d"]:
            continue
        assert v["k"][str(i)] == sum(rows[j][0] == "EN" for j in nb) and v["twice"][str(i)] == 2 * len(nb)
        if nb:
            assert v["s"][str(i)] == pytest.approx(sum(rows[j][0] == "EN" for j in nb) / len(nb))
            assert v["nv"][str(i)] == pytest.approx(np.mean([rows[j][1] for j in nb]))
        else:
            assert str(i) not in v["s"] and str(i) not in v["nv"]
    seeds = {int(r["node"]) for r in v["top"]}
    one = set().union(*(out[i] for i in seeds))
    two = one | set().union(*(out[i] for i in one))
    assert set(map(int, v["reach"])) == two - seeds


def test_quantiles_bins_groups_correlation_and_text_filters(tmp_path):
    lg, pairs, rows = build(tmp_path, False)
    v = run(lg, [("views", "attribute_map", {"attribute": "views"}), ("d", "degree", {}), ("q", "map_quantile", {"map": "d", "q": 0.9}),
                 ("b", "map_bins", {"map": "views", "bins": 10}), ("g", "group_by_map", {"groups": "b", "values": "d", "agg": "median"}),
                 ("rho", "map_correlation", {"a": "views", "b": "d", "method": "spearman"}), ("r", "map_correlation", {"a": "views", "b": "d"}),
                 ("late", "filter_by_attribute", {"attribute": "created", "op": ">=", "value": "2015-01-01"}),
                 ("y12", "filter_by_attribute", {"attribute": "created", "op": "startswith", "value": "2012"}),
                 ("two", "filter_by_attribute", {"attribute": "lang", "value": ["EN", "DE"]}),
                 ("c", "communities", {"method": "louvain"}), ("mm", "membership_map", {"partition": "c"}), ("sizes", "group_by_map", {"groups": "mm"}),
                 ("st", "map_stats", {"map": "views"})])
    nodes = list(v["d"])
    deg = np.array([v["d"][n] for n in nodes]); views = np.array([rows[int(n)][1] for n in nodes], dtype=float)
    assert v["q"] == pytest.approx(np.quantile(deg, 0.9))
    rank = lambda x: np.array([(x < a).sum() + ((x == a).sum() + 1) / 2 for a in x])  # noqa: E731  average rank, counted directly
    pearson = lambda x, y: float(((x - x.mean()) * (y - y.mean())).sum() / np.sqrt(((x - x.mean()) ** 2).sum() * ((y - y.mean()) ** 2).sum()))  # noqa: E731
    assert v["rho"] == pytest.approx(pearson(rank(views), rank(deg))) and v["r"] == pytest.approx(pearson(views, deg))
    assert [r["count"] for r in v["g"]] == [len(nodes) // 10] * 10 if len(nodes) % 10 == 0 else sum(r["count"] for r in v["g"]) == len(nodes)
    lowest = sorted(nodes, key=lambda n: v["views"][n])[: v["g"][0]["count"]]
    assert max(v["views"][n] for n in lowest) <= min(v["views"][n] for n in nodes if v["b"][n] > 1)
    assert v["g"][0]["median"] == pytest.approx(np.median([v["d"][n] for n in nodes if v["b"][n] == 1]))
    assert set(map(int, v["late"])) == {int(n) for n in nodes if rows[int(n)][2] >= "2015-01-01"}
    assert set(map(int, v["y12"])) == {int(n) for n in nodes if rows[int(n)][2].startswith("2012")}
    assert set(map(int, v["two"])) == {int(n) for n in nodes if rows[int(n)][0] in ("EN", "DE")}
    assert [r["count"] for r in v["sizes"]] == sorted((r["count"] for r in v["sizes"]), reverse=True) and v["sizes"][0]["value"] == 1
    assert v["st"]["sum"] == pytest.approx(views.sum())


def test_a_list_where_one_number_is_needed_says_so(tmp_path):
    lg, _, _ = build(tmp_path, False)
    with pytest.raises(ValueError, match="must be one number"):
        run(lg, [("g", "group_by_attribute", {"attribute": "lang"}), ("x", "arithmetic", {"a": "g.count", "op": "/", "b": 3})])
    v = run(lg, [("g", "group_by_attribute", {"attribute": "lang"}), ("x", "arithmetic", {"a": "g.count[0]", "op": "/", "b": 4})])
    assert v["x"] == v["g"][0]["count"] / 4


def test_empty_groups_give_no_value_instead_of_a_crash(tmp_path):
    lg, _, rows = build(tmp_path, False)
    v = run(lg, [("none", "filter_by_attribute", {"attribute": "created", "op": "<", "value": "1990-01-01"}),
                 ("n", "set_size", {"nodes": "none"}),
                 ("views", "attribute_map", {"attribute": "views"}),
                 ("r", "restrict_map", {"map": "views", "nodes": "none"}),
                 ("st", "map_stats", {"map": "r"}),
                 ("share", "arithmetic", {"a": "n", "op": "/", "b": "n"}),
                 ("zero", "arithmetic", {"a": "n", "op": "-", "b": "n"}),
                 ("sub", "induced_subgraph", {"graph": "G", "nodes": "none"}),
                 ("c", "components", {"graph": "sub", "mode": "weak"}),
                 ("all", "map_stats", {"map": "views"}),
                 ("g", "group_by_attribute", {"attribute": "lang", "values": "views", "agg": "median"})])
    assert v["n"] == 0 and v["st"]["n"] == 0 and v["st"]["mean"] is None and v["share"] is None and v["zero"] == 0
    assert v["c"]["count"] == 0 and v["c"]["largest"] == 0
    xs = np.array([r[1] for r in rows.values()], dtype=float)
    assert v["all"]["std"] == pytest.approx(xs.std())
    en = np.median([r[1] for r in rows.values() if r[0] == "EN"])
    assert next(r for r in v["g"] if r["value"] == "EN")["median"] == pytest.approx(en)


def test_reciprocated_links_per_node_and_the_mutual_graph(tmp_path):
    lg, pairs, _ = build(tmp_path, True)
    v = run(lg, [("md", "mutual_degree", {"graph": "G"}),
                 ("mg", "mutual_graph", {"graph": "G"}),
                 ("m", "edge_count", {"graph": "mg"}),
                 ("d", "degree", {"graph": "mg", "mode": "all"}),
                 ("n", "node_count", {"graph": "mg"}),
                 ("full", "mutual_graph", {"graph": "G", "keep_isolated": True}),
                 ("en", "filter_by_attribute", {"attribute": "lang", "op": "==", "value": "EN", "graph": "full"})])
    both = {(a, b) for a, b in pairs if (b, a) in pairs}
    want = {str(i): float(sum(1 for a, _ in both if a == i)) for i in range(N)}
    assert both and {k: v["md"].get(k, 0.0) for k in want} == want
    assert v["m"] == len(both) // 2
    assert {k: v["d"].get(k, 0.0) for k in want} == want
    assert v["n"] == len(v["d"]) == sum(1 for x in want.values() if x)      # nodes without a mutual tie are left out by default
    assert len(v["en"]) == N // 3


def test_direction_dropped_counts_a_pair_linked_both_ways_once(tmp_path):
    lg, pairs, _ = build(tmp_path, True)
    v = run(lg, [("u", "undirected_graph", {"graph": "G"}),
                 ("m", "edge_count", {"graph": "u"}),
                 ("d", "degree", {"graph": "u", "mode": "all"}),
                 ("nb", "neighbours", {"graph": "G", "node": "0", "mode": "all"})])
    und = {frozenset(p) for p in pairs if p[0] != p[1]}
    assert v["m"] == len(und) < len(pairs)
    assert v["d"]["0"] == sum(1 for p in und if 0 in p) == len(v["nb"]) == len(set(v["nb"]))
