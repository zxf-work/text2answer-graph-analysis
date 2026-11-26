"""Guards on the answer: each one flags an error that had passed every other check (plan document, guards section).
A guard adds a failed finding and leaves the answer as it is; a plan without the error gets no such finding."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t2r.ir import Plan, execute, extract_answer, validate  # noqa: E402
from t2r.verify import guards  # noqa: E402
from test_new_ops import build  # noqa: E402


def check(lg, steps, question, answer=None, earlier=None):
    doc = {"steps": [{"id": i, "op": op, "args": a} for i, op, a in steps], "answer": answer or {"step": steps[-1][0]}}
    plan = Plan.model_validate(doc)
    assert validate(plan, lg, 1e12) == []
    ctx, _ = execute(plan, lg)
    fs = guards(plan, ctx, question, extract_answer(plan, ctx), earlier, 1 if earlier else None)
    return {f["check"] for f in fs}, doc


def test_direction_ignored(tmp_path):
    lg, _, _ = build(tmp_path, True)
    q = "How many triangles are there, ignoring the direction of links?"
    assert check(lg, [("t", "triangle_count", {})], q)[0] == {"guard_direction_ignored"}
    assert check(lg, [("u", "undirected_graph", {}), ("t", "triangle_count", {"graph": "u"})], q)[0] == set()
    assert check(lg, [("t", "triangle_count", {})], "How many triangles are there?")[0] == set()
    assert check(lg, [("d", "degree", {"mode": "in"}), ("k", "top_k", {"map": "d", "k": 3})], "Top 3 by in-degree, in either direction?")[0] == set()
    und, _, _ = build(tmp_path, False)
    assert check(und, [("t", "triangle_count", {})], q)[0] == set()


def test_share_out_of_range(tmp_path):
    lg, _, _ = build(tmp_path, True)
    ratio = [("n", "node_count", {}), ("m", "edge_count", {}), ("r", "arithmetic", {"a": "m", "op": "/", "b": "n"})]
    assert check(lg, ratio, "What share of users have a link?")[0] == {"guard_share_out_of_range"}
    assert check(lg, ratio, "How many links per user are there?")[0] == set()
    ok = [("n", "node_count", {}), ("m", "edge_count", {}), ("r", "arithmetic", {"a": "n", "op": "/", "b": "m"})]
    assert check(lg, ok, "What share of users have a link?")[0] == set()
    assert check(lg, ratio, "What percentage is that?")[0] == set()                       # about 7: inside [0, 100]
    for q in ("How many friends do users in the top 1% have?", "Given the share of mature users, how many pairs would we expect?", "What is the 99th percentile?"):
        assert check(lg, ratio, q)[0] == set()                                            # a percentage or share is mentioned, not asked for
    assert check(lg, ratio, "Any overlap?", answer={"steps": {"shared_count": "r"}})[0] == set()
    assert check(lg, ratio, "And the two numbers?", answer={"steps": {"share_linked": "r", "users": "n"}})[0] == {"guard_share_out_of_range"}


def test_grouping_variable(tmp_path):
    lg, _, _ = build(tmp_path, False)
    by_views = [("v", "attribute_map", {"attribute": "views"}), ("b", "map_bins", {"map": "v", "bins": 10})]
    by_degree = [("d", "degree", {}), ("b", "map_bins", {"map": "d", "bins": 10})]
    _, earlier = check(lg, by_views, "Split the users into deciles by views.")
    assert check(lg, by_degree, "How many users are in the top decile?", earlier=earlier)[0] == {"guard_grouping_variable"}
    assert check(lg, by_degree, "Now deciles by degree: how many in the top one?", earlier=earlier)[0] == set()
    assert check(lg, by_views, "How many users are in the top decile?", earlier=earlier)[0] == set()
    assert check(lg, by_degree, "How many users are in the top decile?")[0] == set()


def test_boolean_from_comparison(tmp_path):
    lg, _, _ = build(tmp_path, True)
    steps = [("n", "node_count", {}), ("c", "components", {"mode": "strong"}),
             ("x", "compare", {"a": "n", "b": "c.count", "label_a": "a directed cycle exists", "label_b": "no directed cycle"})]
    q = "Can the users be put in an order in which every link points from an earlier user to a later one?"
    assert check(lg, steps, q, answer={"step": "x", "field": "a_greater"})[0] == {"guard_boolean_from_comparison"}
    assert check(lg, steps, q, answer={"step": "x", "field": "greater"})[0] == set()
    plain = steps[:2] + [("x", "compare", {"a": "n", "b": "c.count"})]
    assert check(lg, plain, "Are there more users than strongly connected components?", answer={"step": "x", "field": "a_greater"})[0] == set()


def test_referent(tmp_path):
    lg, _, _ = build(tmp_path, True)
    top = ("t", "top_k", {"map": "d", "k": 3})
    fans = [("d", "degree", {"mode": "in"}), top, ("m", "neighbours_in_set", {"nodes": "t", "mode": "out"}),
            ("f", "filter_nodes", {"map": "m", "op": ">=", "threshold": 1}), ("n", "set_size", {"nodes": "f"})]
    _, earlier = check(lg, fans, "Of the top 3, how many users link to at least one of them?")
    q = "And how many users are within two hops of them?"
    from_answer = fans[:4] + [("h", "neighbourhood_of_set", {"nodes": "f", "k": 2, "mode": "in"}), ("z", "set_size", {"nodes": "h"})]
    from_group = fans[:2] + [("h", "neighbourhood_of_set", {"nodes": "t", "k": 2, "mode": "in"}), ("z", "set_size", {"nodes": "h"})]
    assert check(lg, from_answer, q, earlier=earlier)[0] == {"guard_referent"}
    assert check(lg, from_group, q, earlier=earlier)[0] == set()
    assert check(lg, from_answer, "How many users are within two hops of the users who link to the top 3?", earlier=earlier)[0] == set()   # no back-reference
    # a refinement is one group, narrowed: continuing from it is not flagged
    narrowed = [("d", "degree", {"mode": "in"}), top, ("o", "degree", {"mode": "out"}), ("f", "filter_nodes", {"map": "o", "op": ">=", "threshold": 1, "nodes": "t"}), ("n", "set_size", {"nodes": "f"})]
    _, earlier2 = check(lg, narrowed, "Of the top 3, how many link to anyone?")
    cont = narrowed[:4] + [("h", "neighbourhood_of_set", {"nodes": "f", "k": 2, "mode": "in"}), ("z", "set_size", {"nodes": "h"})]
    assert check(lg, cont, "How many users are within two hops of them?", earlier=earlier2)[0] == set()
