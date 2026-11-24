"""Session layer: reuse decision rules, the two scope readings, state record. A scripted stand-in replaces the model."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t2r.ir import execute  # noqa: E402
from t2r.llm import Reply, Usage  # noqa: E402
from t2r.session import Session, TurnPlan, other_reading, scope_patterns  # noqa: E402
from test_reuse import AGE, DEPT, EDGES  # noqa: E402,F401


class Scripted:
    """Returns the next prepared plan; records what the planner was shown."""
    def __init__(self, plans):
        self.plans, self.usage, self.seen = list(plans), Usage(), []

    def chat(self, system, user, max_tokens=0, **kw):
        self.seen.append(user)
        r = Reply(text=json.dumps(self.plans.pop(0)), input_tokens=len(user) // 4)
        self.usage.add(r)
        return r


def P(steps, answer, **extra):
    return {"interpretation": {"directed": True, "measure": "pagerank"}, "steps": [{"id": i, "op": op, "args": a} for i, op, a in steps],
            "answer": {"step": answer, "kind": "ranking"}, **extra}


PR = ("pr", "pagerank", {})
TOP = lambda k, m="pr": ("top", "top_k", {"map": m, "k": k})  # noqa: E731
ENG = ("eng", "filter_by_attribute", {"attribute": "dept", "value": "eng"})
T1 = P([PR, TOP(3)], "top", intent="new")
T2 = P([PR, TOP(3), ("a", "attribute_of", {"nodes": "top", "attribute": "dept"})], "a", intent="drill_down", based_on=1, references={"they": "the 3 nodes of turn 1"})
T3 = P([PR, TOP(5)], "top", intent="patch", based_on=1, patch={"type": "parameter", "what": "k 3 -> 5"})
T4A = P([PR, ENG, ("r", "restrict_map", {"map": "pr", "nodes": "eng"}), TOP(3, "r")], "top", intent="patch", patch={"type": "scope", "what": "dept eng"},
        scope_reading={"reading": "A", "explicit": False, "quote": ""})
T4B = P([ENG, ("g", "induced_subgraph", {"nodes": "eng"}), ("pr", "pagerank", {"graph": "g"}), TOP(3)], "top", intent="patch",
        scope_reading={"reading": "B", "explicit": False, "quote": ""})


@pytest.fixture()
def path(tmp_path):
    e = tmp_path / "org.csv"
    e.write_text("src,dst\n" + "\n".join(f"{u},{v}" for u, v in EDGES) + "\n")
    (tmp_path / "org.nodes.csv").write_text("id,dept,age\n" + "\n".join(f"{n},{DEPT[n]},{AGE[n]}" for n in DEPT) + "\n")
    return str(e)


def test_three_outcomes_over_a_session(path):
    s = Session(path)
    llm = Scripted([T1, T2, T3, T1])
    t1 = s.ask("top 3 by influence", llm)
    assert t1["outcome"] == "recompute" and t1["steps_reused"] == 0 and s.semantics == {"directed": True, "weighted": False}
    t2 = s.ask("which dept are they in", llm)
    assert t2["outcome"] == "partial reuse" and [t["cached"] for t in t2["trace"]] == [True, True, False]
    t3 = s.ask("top 5 instead", llm)
    assert t3["outcome"] == "partial reuse" and [t["cached"] for t in t3["trace"]] == [True, False] and len(t3["answer"]) == 5
    t4 = s.ask("top 3 again", llm)
    assert t4["outcome"] == "exact reuse" and t4["answer"] == t1["answer"]
    assert t4["findings"] is not None            # verified although nothing was executed


def test_planner_sees_state_not_history(path):
    s = Session(path)
    llm = Scripted([T1, T2])
    s.ask("top 3 by influence", llm); s.ask("which dept are they in", llm)
    st = json.loads(llm.seen[1].split("SESSION STATE:\n")[1].split("\n\nGraph file")[0])
    assert st["turn"] == 2 and st["accepted_semantics"]["directed"] is True
    assert st["turns"][0]["steps"][0] == {"id": "pr", "op": "pagerank", "args": {}, "returns": "NodeMap", "size": 12}
    assert st["current_selection"]["count"] == 3 and st["current_selection"]["produced_by_step"] == "top" and "value" not in json.dumps(st["turns"])


@pytest.mark.parametrize("planned,other", [(T4A, "B"), (T4B, "A")])
def test_scope_ambiguity_gives_two_contracts_whichever_the_planner_wrote(path, planned, other):
    s = Session(path)
    llm = Scripted([T1, planned])
    s.ask("top 3 by influence", llm)
    t = s.ask("who is most influential within eng", llm)
    assert t["outcome"] == "clarify" and "answer" not in t
    assert [c["reading"] for c in t["contracts"]] == [planned["scope_reading"]["reading"], other]
    assert t["contracts"][1]["source"] == "engine rewrite"
    a = next(c for c in t["contracts"] if c["reading"] == "A"); b = next(c for c in t["contracts"] if c["reading"] == "B")
    assert next(r for r in a["preview"]["steps"] if r["op"] == "pagerank")["reuse"] is True       # A reuses the whole-graph scores
    assert next(r for r in b["preview"]["steps"] if r["op"] == "pagerank")["reuse"] is False      # B must recompute
    done = s.choose(1)
    assert done["outcome"] in ("partial reuse", "recompute") and s.scope_choice == {"reading": other, "turn": 2}


def test_rewrite_matches_the_hand_written_other_reading(path):
    s = Session(path)
    lg = s._load({"directed": True})
    a, b = TurnPlan.model_validate(T4A), TurnPlan.model_validate(T4B)
    ab = other_reading(a, scope_patterns(a)[0]); ba = other_reading(b, scope_patterns(b)[0])
    val = lambda p: execute(p, lg)[0].values["top"]  # noqa: E731
    assert val(ab) == val(b) and val(ba) == val(a) and val(a) != val(b)
    assert [x["reading"] for x in scope_patterns(ab)] == ["B"] and [x["reading"] for x in scope_patterns(ba)] == ["A"]


def test_explicit_reading_needs_a_real_quote(path):
    q = "who is most influential within eng, counting only links inside eng"
    ok = {**T4B, "scope_reading": {"reading": "B", "explicit": True, "quote": "counting only links inside eng"}}
    fake = {**T4B, "scope_reading": {"reading": "B", "explicit": True, "quote": "on the induced subgraph"}}
    s = Session(path)
    t = s.ask(q, Scripted([ok]))
    assert t["outcome"] == "recompute" and "contracts" not in t
    s = Session(path)
    t = s.ask(q, Scripted([fake]))
    assert t["outcome"] == "clarify" and any(f["check"] == "scope_reading_quote" for f in t["reuse_findings"])


def test_choice_is_carried_to_later_turns(path):
    sales_a = P([PR, ("sa", "filter_by_attribute", {"attribute": "dept", "value": "sales"}), ("r", "restrict_map", {"map": "pr", "nodes": "sa"}), TOP(3, "r")], "top",
                scope_reading={"reading": "A", "explicit": False, "quote": ""})
    s = Session(path)
    llm = Scripted([T1, T4A, sales_a])
    s.ask("top 3", llm); s.ask("within eng", llm); s.choose(1)          # user picks B
    t = s.ask("and within sales", llm)                                  # planner wrote A; the engine applies B and says so
    assert t["outcome"] != "clarify" and [p["reading"] for p in scope_patterns(TurnPlan.model_validate(t["plan"]))] == ["B"]
    assert any("carried over" in f["detail"] for f in t["reuse_findings"])


def test_both_and_planner_policies(path):
    s = Session(path, on_ambiguity="both")
    llm = Scripted([T1, T4A])
    s.ask("top 3", llm)
    t = s.ask("within eng", llm)
    assert t["outcome"] == "both readings shown" and t["readings_compared"]["k"] == 3 and all("result" in c for c in t["contracts"])
    s = Session(path, on_ambiguity="planner")
    t = s.ask("within eng", Scripted([T4A]))
    assert "contracts" not in t and any("assumed by the planner" in f["detail"] for f in t["reuse_findings"])


def test_changed_semantics_reuses_nothing_and_is_reported(path):
    und = {**T1, "interpretation": {"directed": False, "measure": "pagerank"}}
    s = Session(path)
    llm = Scripted([T1, und])
    a = s.ask("top 3", llm)
    b = s.ask("top 3 ignoring direction", llm)
    assert b["steps_reused"] == 0 and any(f["check"] == "semantics_changed" for f in b["reuse_findings"]) and a["keys"]["pr"] != b["keys"]["pr"]


def test_reuse_off_executes_everything(path):
    s = Session(path, reuse=False)
    llm = Scripted([T1, T1])
    s.ask("top 3", llm)
    assert s.ask("top 3", llm)["outcome"] == "recompute"


def test_plan_with_both_readings_answers_with_the_chosen_one(path):
    """Seen live (Haiku, Pokec): the planner computed both readings in one plan and answered with A. Choosing B must give B's answer."""
    both = P([PR, ENG, ("r", "restrict_map", {"map": "pr", "nodes": "eng"}), ("top", "top_k", {"map": "r", "k": 3}),
              ("g", "induced_subgraph", {"nodes": "eng"}), ("pr2", "pagerank", {"graph": "g"}), ("top2", "top_k", {"map": "pr2", "k": 3})], "top",
             scope_reading={"reading": "A", "explicit": False, "quote": ""})
    s = Session(path)
    t = s.ask("most influential within eng", Scripted([both]))
    assert [c["reading"] for c in t["contracts"]] == ["A", "B"]
    done = s.choose(1)
    lg = s._load({"directed": True})
    want = execute(TurnPlan.model_validate(T4B), lg)[0].values["top"]
    other = execute(TurnPlan.model_validate(T4A), lg)[0].values["top"]
    assert [r["node"] for r in done["answer"]] == [r["node"] for r in want] != [r["node"] for r in other]


def test_every_restricted_measure_follows_the_chosen_reading(path):
    """Seen live (Opus, Pokec): a two-part answer restricted PageRank and a degree variant; only one was rewritten."""
    two = P([PR, ENG, ("r", "restrict_map", {"map": "pr", "nodes": "eng"}), ("top", "top_k", {"map": "r", "k": 3}),
             ("d", "degree", {"mode": "in"}), ("rd", "restrict_map", {"map": "d", "nodes": "eng"}), ("topd", "top_k", {"map": "rd", "k": 3})], "top")
    two["answer"] = {"steps": {"by_pagerank": "top", "by_degree": "topd"}, "kind": "table"}
    s = Session(path)
    t = s.ask("most influential within eng", Scripted([two]))
    assert [c["reading"] for c in t.get("contracts", [])] == ["A", "B"], t.get("error")
    done = s.choose(1)
    assert {p["reading"] for p in scope_patterns(TurnPlan.model_validate(done["plan"]))} == {"B"}
    want = execute(TurnPlan.model_validate(T4B), s._load({"directed": True}))[0].values["top"]
    assert [r["node"] for r in done["answer"]["by_pagerank"]] == [r["node"] for r in want]


def test_selection_of_a_count_is_the_set_that_was_counted(path):
    """Seen in the session pilot: after "how many users are in X", "among them" was resolved to an older ranking."""
    count = P([ENG, ("n", "set_size", {"nodes": "eng"})], "n")
    s = Session(path)
    llm = Scripted([T1, count, T1])
    s.ask("top 3", llm); s.ask("how many in eng", llm); s.ask("anything", llm)
    sel = json.loads(llm.seen[2].split("SESSION STATE:\n")[1].split("\n\nGraph file")[0])["current_selection"]
    assert sel["from_turn"] == 2 and sel["op"] == "filter_by_attribute" and sel["count"] == 4


# ------------------------------------------------------------------------------------- changes during a session
def _bump(p):
    """Make sure the modification time moves even on a coarse clock."""
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def test_edge_file_changed_between_turns_is_recomputed_and_reported(path):
    s = Session(path)
    llm = Scripted([T1, T1, T1])
    t1 = s.ask("top 3", llm)
    with open(path, "a") as f:
        f.write("".join(f"{n},{EDGES[0][0]}\n" for n in list(DEPT)[:6]))     # new links change the ranking input
    _bump(path)
    t2 = s.ask("top 3 again", llm)
    assert t2["steps_reused"] == 0 and any(f["check"] == "data_changed" for f in t2["reuse_findings"])
    assert s.data_changes[0]["changed"] == ["edge file"] and s.data_changes[0]["edges"][1] > s.data_changes[0]["edges"][0]
    assert [r["value"] for r in t2["answer"]] != [r["value"] for r in t1["answer"]]
    t3 = s.ask("and again", llm)                                              # nothing changed since: reuse is valid again
    assert t3["outcome"] == "exact reuse" and not any(f["check"] == "data_changed" for f in t3["reuse_findings"])


def test_node_table_changed_between_turns(path):
    s = Session(path)
    q = P([ENG, ("n", "set_size", {"nodes": "eng"})], "n")
    llm = Scripted([q, q])
    n1 = s.ask("how many in eng", llm)["answer"]
    t = path.replace(".csv", ".nodes.csv")
    rows = open(t).read().splitlines()
    i = next(k for k, r in enumerate(rows) if r.split(",")[1] == "eng")
    rows[i] = rows[i].replace(",eng,", ",ops,")
    open(t, "w").write("\n".join(rows) + "\n"); _bump(t)
    t2 = s.ask("how many in eng", llm)
    assert t2["answer"] == n1 - 1 and t2["steps_reused"] == 0 and s.data_changes[0]["changed"] == ["node table"]


def test_reading_change_holds_until_changed_back(path):
    und = {**T1, "interpretation": {"directed": False, "measure": "pagerank"}}
    s = Session(path)
    llm = Scripted([T1, und, und, T1])
    a = s.ask("top 3", llm)
    b = s.ask("treat links as mutual from now on: top 3", llm)
    assert b["steps_reused"] == 0 and s.semantics["directed"] is False
    c = s.ask("top 3 again", llm)
    assert c["outcome"] == "exact reuse" and c["answer"] == b["answer"]
    d = s.ask("back to directed: top 3", llm)                                 # the first result is valid again
    assert d["outcome"] == "exact reuse" and d["answer"] == a["answer"] and d["trace"][0]["from_turn"] == 1


def test_standing_setting_is_written_into_later_plans(path):
    s = Session(path)
    set9 = {**P([("pr", "pagerank", {"damping": 0.5}), TOP(3)], "top"), "set_standing": {"pagerank.damping": 0.5}}
    llm = Scripted([T1, set9, T2, P([("pr", "pagerank", {"damping": 0.85}), TOP(3)], "top")])
    a = s.ask("top 3", llm)
    b = s.ask("use damping 0.5 from now on: top 3", llm)
    assert s.standing == {"pagerank.damping": 0.5} and b["steps_reused"] == 0
    c = s.ask("which dept are they in", llm)                                  # the planner forgot the setting: the engine writes it in
    assert c["plan"]["steps"][0]["args"] == {"damping": 0.5} and [t["cached"] for t in c["trace"]] == [True, True, False]
    assert any(f["check"] == "standing_setting_applied" for f in c["reuse_findings"])
    d = s.ask("top 3", llm)                                                   # an explicit other value is kept, and flagged
    assert any(f["check"] == "standing_setting_overridden" for f in d["reuse_findings"]) and d["answer"] == a["answer"]
    assert "standing_settings" in json.loads(llm.seen[-1].split("SESSION STATE:\n")[1].split("\n\nGraph file")[0])


def test_remove_nodes_leaves_the_base_graph_alone(path):
    s = Session(path)
    cut = P([PR, ("top", "top_k", {"map": "pr", "k": 2}), ("g", "remove_nodes", {"nodes": "top"}), ("n", "node_count", {"graph": "g"})], "n")
    whole = P([("n", "node_count", {})], "n")
    llm = Scripted([whole, cut, whole])
    n = s.ask("how many nodes", llm)["answer"]
    assert s.ask("without the top 2: how many nodes", llm)["answer"] == n - 2
    assert s.ask("on the full network: how many nodes", llm)["answer"] == n
