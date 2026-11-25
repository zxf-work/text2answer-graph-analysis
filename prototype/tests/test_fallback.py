"""Checked code fallback: inputs from operators, two separately written functions, an answer only when they agree."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t2r.fallback import same_value  # noqa: E402
from t2r.llm import Reply, Usage  # noqa: E402
from t2r.session import Session  # noqa: E402
from test_new_ops import build  # noqa: E402


class Scripted:
    def __init__(self, replies):
        self.replies, self.usage, self.seen = list(replies), Usage(), []

    def chat(self, system, user, max_tokens=0, **kw):
        self.seen.append((system, user))
        x = self.replies.pop(0)
        r = Reply(text=x if isinstance(x, str) else json.dumps(x))
        self.usage.add(r)
        return r


NO = {"interpretation": {"measure": "largest clique"}, "steps": [], "answer": None, "unsupported": "the catalogue has no maximum clique operator", "intent": "new"}
PREP = {"interpretation": {"measure": "largest clique among the 8 highest-degree nodes"}, "intent": "new",
        "steps": [{"id": "d", "op": "degree", "args": {"mode": "all"}}, {"id": "t", "op": "top_k", "args": {"map": "d", "k": 8}},
                  {"id": "s", "op": "induced_subgraph", "args": {"nodes": "t"}}],
        "code_inputs": {"sub": "s"}, "code_task": "Return the size of the largest clique of inputs['sub'] as the value and its members as the witness."}
IG = "```python\ndef solve(inputs):\n    g = to_igraph(inputs['sub']).as_undirected()\n    c = g.largest_cliques()[0]\n    return {'value': len(c), 'witness': [g.vs[i]['name'] for i in c], 'method': 'igraph'}\n```"
NX = ("```python\nimport networkx as nx\ndef solve(inputs):\n    G = to_networkx(inputs['sub']).to_undirected()\n    c = max(nx.find_cliques(G), key=len)\n"
      "    return {'value': len(c), 'witness': sorted(c), 'method': 'networkx'}\n```")
WRONG = "```python\ndef solve(inputs):\n    return {'value': 99, 'witness': None, 'method': 'guess'}\n```"


def session(tmp_path):
    build(tmp_path, False)
    return Session(str(tmp_path / "e.txt"), description="test", code_fallback=True)


def test_two_functions_that_agree_give_an_answer_by_code(tmp_path):
    s = session(tmp_path)
    llm = Scripted([NO, PREP, IG, NX])
    t = s.ask("What is the largest clique among the 8 highest-degree nodes?", llm)
    assert t["outcome"] == "answer by code" and t["answer"]["value"] == t["answer_value"] >= 2
    assert [x["op"] for x in t["trace"]] == ["degree", "top_k", "induced_subgraph"] and t["code"]["agree"]
    assert {f["check"]: f["ok"] for f in t["findings"]} == {"outside_catalogue": False, "code_cross_check": True}
    assert "unsupported" in llm.seen[1][1] and "8 nodes" in llm.seen[2][1]          # the writers see the prepared input, not the file
    assert all(s.path not in u for _, u in llm.seen[2:])
    again = s.ask("And the same once more?", Scripted([NO, PREP, IG, NX]))
    assert again["steps_reused"] == 3 and again["outcome"] == "answer by code"      # the prepared inputs are reused, the code is run again


def test_two_functions_that_disagree_give_no_answer(tmp_path):
    s = session(tmp_path)
    t = s.ask("What is the largest clique among the 8 highest-degree nodes?", Scripted([NO, PREP, IG, WRONG]))
    assert t["outcome"] == "unconfirmed" and t.get("answer") is None and 99 in t["candidates"]
    assert not {f["check"]: f["ok"] for f in t["findings"]}["code_cross_check"]


def test_without_the_switch_the_turn_stays_unsupported(tmp_path):
    build(tmp_path, False)
    t = Session(str(tmp_path / "e.txt"), description="test", code_fallback=False).ask("largest clique?", Scripted([NO]))
    assert t["outcome"] == "unsupported" and "code" not in t


def test_inputs_that_cannot_be_prepared_leave_the_turn_unsupported(tmp_path):
    s = session(tmp_path)
    again = {**NO, "unsupported": "the group as it was before the refresh is no longer stored"}
    t = s.ask("Which nodes are new since the refresh?", Scripted([NO, again]))
    assert t["outcome"] == "unsupported" and t.get("answer") is None and "before the refresh" in t["unsupported"] and t["code"]["declined"]


def test_values_are_compared_by_value_not_by_layout():
    assert same_value(7, 7.0) and same_value([1, "A"], [1.0, "a "]) and same_value({"a": 1}, {"a": 1})
    assert not same_value(True, 1) and not same_value([1, 2], [2, 1]) and not same_value(7, 8) and not same_value(None, 0)


def test_rows_left_out_of_the_graph_are_named_with_every_answer(tmp_path):
    build(tmp_path, False)
    with open(tmp_path / "e.txt", "a") as f:
        f.write("3\t3\n4\t4\n")
    s = Session(str(tmp_path / "e.txt"), description="test", code_fallback=True)
    plan = {"interpretation": {"measure": "edge count"}, "intent": "new", "steps": [{"id": "m", "op": "edge_count", "args": {}}], "answer": {"step": "m"}}
    by_plan = s.ask("How many links?", Scripted([plan]))
    by_code = s.ask("What is the largest clique among the 8 highest-degree nodes?", Scripted([NO, PREP, IG, NX]))
    for t in (by_plan, by_code):
        assert len(t["conventions"]) == 1 and t["conventions"][0].startswith("2 of the ") and "left out" in t["conventions"][0]
