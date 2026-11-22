"""Lineage cache keys and node attributes. Run: python -m pytest tests -q   (from prototype/)"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t2r.graphs import load_graph, profile_card  # noqa: E402
from t2r.ir import Plan, execute, graph_key, validate  # noqa: E402

EDGES = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "a"), ("a", "c"), ("f", "a"), ("g", "a"), ("h", "a"),
         ("h", "g"), ("i", "h"), ("j", "h"), ("j", "i"), ("k", "j"), ("l", "k"), ("l", "a")]
DEPT = {"a": "eng", "b": "eng", "c": "eng", "d": "ops", "e": "ops", "f": "ops", "g": "sales", "h": "sales", "i": "sales",
        "j": "eng", "k": "ops"}            # l has no row
AGE = {"a": 41, "b": 29, "c": 35, "d": 52, "e": 23, "f": 31, "g": 44, "h": 38, "i": 27, "j": 30, "k": ""}


@pytest.fixture()
def files(tmp_path):
    e = tmp_path / "org.csv"
    e.write_text("src,dst\n" + "\n".join(f"{u},{v}" for u, v in EDGES) + "\n")
    return str(e), tmp_path


@pytest.fixture()
def with_table(files):
    e, d = files
    (d / "org.nodes.csv").write_text("id,dept,age\n" + "\n".join(f"{n},{DEPT[n]},{AGE[n]}" for n in DEPT) + "\nzz,eng,1\n")
    return e


def plan(*steps, answer=None):
    st = [{"id": i, "op": op, "args": args} for i, op, args in steps]
    return Plan.model_validate({"steps": st, "answer": {"step": answer or st[-1]["id"], "kind": "table"}})


PR_TOP3 = plan(("s1", "pagerank", {"graph": "G"}), ("s2", "top_k", {"map": "s1", "k": 3}))


def test_cache_does_not_cross_interpretations(files):
    """The pre-lineage cache keyed on (file hash, op, args) returned directed PageRank for the undirected reading."""
    e, _ = files
    d = load_graph("org", e, "", override={"directed": True})
    u = load_graph("org", e, "", override={"directed": False})
    assert d.facts.sha1 == u.facts.sha1 and graph_key(d) != graph_key(u)
    cache = {}
    execute(PR_TOP3, d, cache=cache)
    cu, tu = execute(PR_TOP3, u, cache=cache)
    cf, _ = execute(PR_TOP3, u)
    assert not any(t["cached"] for t in tu)
    assert cu.values["s2"] == cf.values["s2"]


def test_repeat_is_fully_reused_including_derived_steps(files):
    lg = load_graph("org", files[0], "", override={"directed": True})
    cache = {}
    c1, t1 = execute(PR_TOP3, lg, cache=cache)
    c2, t2 = execute(PR_TOP3, lg, cache=cache)
    assert [t["cached"] for t in t1] == [False, False] and [t["cached"] for t in t2] == [True, True]
    assert c1.values["s2"] == c2.values["s2"] and "seconds_saved" in t2[0]


def test_top10_to_top20_reuses_scores_and_recomputes_only_topk(files):
    lg = load_graph("org", files[0], "", override={"directed": True})
    cache = {}
    execute(PR_TOP3, lg, cache=cache)
    more = plan(("r", "pagerank", {}), ("t", "top_k", {"map": "r", "k": 6}))      # other step ids, graph omitted
    c, t = execute(more, lg, cache=cache)
    assert [x["cached"] for x in t] == [True, False]
    assert c.values["t"] == execute(more, lg)[0].values["t"] and len(c.values["t"]) == 6


def test_scope_change_never_reuses_whole_graph_scores(files):
    lg = load_graph("org", files[0], "", override={"directed": True})
    cache = {}
    execute(PR_TOP3, lg, cache=cache)
    sub = plan(("g1", "induced_subgraph", {"nodes": ["a", "b", "c", "j"]}), ("s1", "pagerank", {"graph": "g1"}), ("s2", "top_k", {"map": "s1", "k": 3}))
    c, t = execute(sub, lg, cache=cache)
    assert not any(x["cached"] for x in t)
    whole = execute(PR_TOP3, lg)[0].values["s1"]
    assert abs(c.values["s1"]["a"] - whole["a"]) > 1e-6
    # same scope again, written differently: reused
    again = plan(("x", "induced_subgraph", {"graph": "G", "nodes": ["a", "b", "c", "j"]}), ("y", "pagerank", {"graph": "x"}))
    assert all(x["cached"] for x in execute(again, lg, cache=cache)[1])
    # a different node set is a different scope
    other = plan(("x", "induced_subgraph", {"nodes": ["a", "b", "c"]}), ("y", "pagerank", {"graph": "x"}))
    assert not any(x["cached"] for x in execute(other, lg, cache=cache)[1])


def test_seed_and_parameters_are_part_of_the_key(files):
    lg = load_graph("org", files[0], "", override={"directed": True})
    cache = {}
    execute(PR_TOP3, lg, cache=cache, seed=1)
    assert not any(x["cached"] for x in execute(PR_TOP3, lg, cache=cache, seed=2)[1])
    damp = plan(("s1", "pagerank", {"damping": 0.5}))
    assert not execute(damp, lg, cache=cache)[1][0]["cached"]


def test_node_table_is_attached_and_profiled(with_table):
    lg = load_graph("org", with_table, "", override={"directed": True})
    t = lg.g["node_table"]
    assert t["rows"] == 12 and t["rows_matched"] == 11 and t["nodes_without_row"] == 1
    assert t["attributes"]["dept"]["type"] == "categorical" and t["attributes"]["dept"]["n_distinct"] == 3
    assert t["attributes"]["age"]["type"] == "numeric" and t["attributes"]["age"]["max"] == 52.0
    assert t["attributes"]["age"]["coverage"] == round(10 / 12, 4)
    card = profile_card(lg)
    assert set(card["node_attributes"]["attributes"]) == {"dept", "age"}


def test_node_table_changes_the_graph_key(files, with_table):
    lg = load_graph("org", with_table, "", override={"directed": True})
    k1 = graph_key(lg)
    os.remove(os.path.splitext(with_table)[0] + ".nodes.csv")
    assert graph_key(load_graph("org", with_table, "", override={"directed": True})) != k1


def test_attribute_operators(with_table):
    lg = load_graph("org", with_table, "", override={"directed": True})
    p = plan(("pr", "pagerank", {}), ("top", "top_k", {"map": "pr", "k": 3}),
             ("dept", "attribute_of", {"nodes": "top", "attribute": "dept"}),
             ("eng", "filter_by_attribute", {"attribute": "dept", "op": "==", "value": "eng"}),
             ("old", "filter_by_attribute", {"attribute": "age", "op": ">=", "value": 40}),
             ("grp", "group_by_attribute", {"attribute": "dept"}),
             ("grp2", "group_by_attribute", {"attribute": "dept", "values": "pr", "agg": "sum"}),
             ("age", "attribute_map", {"attribute": "age"}), ("oldest", "top_k", {"map": "age", "k": 1}))
    assert validate(p, lg) == []
    v = execute(p, lg)[0].values
    assert [r["node"] for r in v["dept"]] == [r["node"] for r in v["top"]]
    assert all(r["value"] == DEPT[r["node"]] for r in v["dept"])
    assert sorted(v["eng"]) == ["a", "b", "c", "j"] and sorted(v["old"]) == ["a", "d", "g"]
    assert {r["value"]: r["count"] for r in v["grp"]} == {"eng": 4, "ops": 4, "sales": 3}
    assert abs(sum(r["sum"] for r in v["grp2"]) + v["pr"]["l"] - 1.0) < 1e-9
    assert v["oldest"][0]["node"] == "d" and "k" not in v["age"] and "l" not in v["age"]


def test_two_readings_of_within_a_group_differ(with_table):
    """'Most influential within eng': filtering whole-graph scores and recomputing on the eng subgraph are different analyses."""
    lg = load_graph("org", with_table, "", override={"directed": True})
    cache = {}
    filtered = plan(("pr", "pagerank", {}), ("eng", "filter_by_attribute", {"attribute": "dept", "value": "eng"}),
                    ("r", "restrict_map", {"map": "pr", "nodes": "eng"}), ("t", "top_k", {"map": "r", "k": 4}))
    induced = plan(("eng", "filter_by_attribute", {"attribute": "dept", "value": "eng"}), ("g", "induced_subgraph", {"nodes": "eng"}),
                   ("pr", "pagerank", {"graph": "g"}), ("t", "top_k", {"map": "pr", "k": 4}),
                   ("d", "attribute_of", {"nodes": "t", "attribute": "dept", "graph": "g"}))
    a, ta = execute(filtered, lg, cache=cache)
    b, tb = execute(induced, lg, cache=cache)
    by = {x["step"]: x["cached"] for x in tb}
    assert by["eng"] is True and by["pr"] is False            # the node set is reused, the scores are not
    assert [r["value"] for r in a.values["t"]] != [r["value"] for r in b.values["t"]]
    assert {r["value"] for r in b.values["d"]} == {"eng"}      # the subgraph kept its attributes


def test_validator_checks_attributes_against_the_table(files, with_table):
    lg = load_graph("org", with_table, "", override={"directed": True})
    bad = [plan(("x", "filter_by_attribute", {"attribute": "team", "value": "eng"})),
           plan(("x", "filter_by_attribute", {"attribute": "dept", "value": "engineering"})),
           plan(("x", "attribute_map", {"attribute": "dept"}))]
    msgs = [validate(p, lg) for p in bad]
    assert all(msgs) and "available" in msgs[0][0] and "no value" in msgs[1][0] and "categorical" in msgs[2][0]
