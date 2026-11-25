"""Appending in place: when the edge file only grew, the updated graph must equal the one a full load gives, and
whenever that cannot be guaranteed the loader must decline (return None) so the file is loaded again."""
import dataclasses
import json
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import t2r.graphs as G  # noqa: E402
from t2r.llm import Reply, Usage  # noqa: E402
from t2r.session import Session  # noqa: E402


@pytest.fixture(autouse=True)
def big_path(monkeypatch, tmp_path):
    monkeypatch.setattr(G, "BIG_FILE_BYTES", 0)            # send small files through the large-file reader
    monkeypatch.setenv("T2R_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("T2R_GRAPH_CACHE", raising=False)
    monkeypatch.delenv("T2R_APPEND", raising=False)


def write(path, rows, mode="w"):
    with open(path, mode) as f:
        f.write("".join(f"{u}\t{v}\n" for u, v in rows))
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000_000))


def base_rows(n=400, m=3000, seed=0, ids=None):
    rng = np.random.default_rng(seed)
    ids = np.arange(n) if ids is None else np.asarray(ids)
    r = rng.integers(0, len(ids), size=(m, 2))
    r = r[r[:, 0] != r[:, 1]]
    return [(int(ids[a]), int(ids[b])) for a, b in r]


def same_as_full_load(grown, path, override=None):
    full = G._load_graph_uncached("g", path, "", override)
    assert grown.labels == full.labels and grown.g.vcount() == full.g.vcount() and grown.g.is_directed() == full.g.is_directed()
    assert sorted(grown.g.get_edgelist()) == sorted(full.g.get_edgelist())
    a, b = dataclasses.asdict(grown.facts), dataclasses.asdict(full.facts)
    a.pop("reciprocity"); b.pop("reciprocity")            # a sampled estimate; only its side of the thresholds matters
    assert a == b
    s, t = grown.semantics, full.semantics
    assert (s.directed, s.weighted, s.multigraph, s.weight_semantics) == (t.directed, t.weighted, t.multigraph, t.weight_semantics)
    assert [str(i) in grown.index and grown.index[str(i)] == full.index[str(i)] for i in full.labels[-5:]]


def test_directed_append_with_repeats_and_new_nodes(tmp_path):
    p = str(tmp_path / "e.txt")
    rows = base_rows()
    rows += [(b, a) for a, b in rows[:1500]]               # partial reciprocity: clearly directed
    write(p, rows)
    lg = G.load_graph("g", p)
    assert lg.g.is_directed() and isinstance(lg.index, G._RangeIndex)
    extra = [(7, 8), (8, 7), rows[0], rows[0], (400, 3), (3, 401), (401, 400), (5, 399), (5, 399)]
    write(p, extra, "a")
    grown = G.append_in_place(lg, p)
    assert grown is not None and grown.load_info["source"] == "append" and grown.g is lg.g
    same_as_full_load(grown, p)
    # and once more on the grown graph
    write(p, [(402, 0), (9, 10)], "a")
    again = G.append_in_place(grown, p)
    assert again is not None
    same_as_full_load(again, p)


def test_non_contiguous_ids_and_undirected_reading(tmp_path):
    p = str(tmp_path / "e.txt")
    ids = np.arange(40000) * 7 + 3                         # sparse: almost no row has its reverse, far from the 2% threshold
    rows = base_rows(ids=ids, m=30000)                     # and large enough that 42 new rows cannot move it there
    write(p, rows)
    ov = {"directed": False}
    lg = G.load_graph("g", p, override=ov)
    assert not lg.g.is_directed() and not isinstance(lg.index, G._RangeIndex)
    have = {(min(a, b), max(a, b)) for a, b in rows}
    seen = sorted({x for r in rows for x in r})            # only ids that are already nodes: a new id between old ones is declined
    fresh = [(int(a), int(b)) for a, b in base_rows(ids=seen, seed=5, m=200) if (min(a, b), max(a, b)) not in have][:40]
    write(p, fresh + [(500000, int(seen[0])), (500001, 500000)], "a")
    grown = G.append_in_place(lg, p, override=ov)
    assert grown is not None, G.APPEND_DECLINED
    same_as_full_load(grown, p, ov)


@pytest.mark.parametrize("case", ["edited_prefix", "self_loop_twice", "id_in_the_middle", "known_pair_undirected", "gap_in_contiguous_ids",
                                  "no_trailing_newline", "switched_off", "other_holder_already_grew_it"])
def test_declines_when_a_full_load_could_differ(tmp_path, monkeypatch, case):
    p = str(tmp_path / "e.txt")
    ids = np.arange(400) * 7 + 3 if case == "id_in_the_middle" else None
    rows = base_rows(ids=ids)
    rows += [(b, a) for a, b in rows[:1500]]
    if case == "self_loop_twice":
        rows.append((4, 4))
    write(p, rows)
    ov = {"directed": False} if case == "known_pair_undirected" else None
    lg = G.load_graph("g", p, override=ov)
    extra = [(1, 2), (3, 9)]
    if case == "edited_prefix":
        text = open(p).read()
        open(p, "w").write(text.replace(f"{rows[0][0]}\t{rows[0][1]}\n", f"{rows[0][1]}\t{rows[0][0]}\n", 1))
    elif case == "self_loop_twice":
        extra = [(4, 4)]
    elif case == "id_in_the_middle":
        extra = [(4, 10)]                                  # 4 is a new id that sorts before existing ones
    elif case == "known_pair_undirected":
        extra = [(rows[0][1], rows[0][0])]
    elif case == "gap_in_contiguous_ids":
        extra = [(405, 1)]
    elif case == "no_trailing_newline":
        open(p, "w").write(open(p).read().rstrip("\n"))
        lg = G.load_graph("g", p, override=ov)
    elif case == "switched_off":
        monkeypatch.setenv("T2R_APPEND", "0")
    elif case == "other_holder_already_grew_it":
        write(p, [(11, 12)], "a")
        assert G.append_in_place(dataclasses.replace(lg), p) is not None      # someone sharing the graph object got there first
    before = (lg.g.vcount(), lg.g.ecount())
    if case == "no_trailing_newline":
        with open(p, "a") as f:
            f.write("\n1\t2\n")
    else:
        write(p, extra, "a")
    assert G.append_in_place(lg, p, override=ov) is None
    if case != "other_holder_already_grew_it":
        assert (lg.g.vcount(), lg.g.ecount()) == before    # declining leaves the graph untouched


class Scripted:
    def __init__(self, plans):
        self.plans, self.usage = list(plans), Usage()

    def chat(self, system, user, max_tokens=0, **kw):
        r = Reply(text=json.dumps(self.plans.pop(0)), input_tokens=1)
        self.usage.add(r)
        return r


def test_session_appends_and_answers_like_a_fresh_session(tmp_path):
    p = str(tmp_path / "e.txt")
    rows = base_rows()
    rows += [(b, a) for a, b in rows[:1500]]
    write(p, rows)
    plan = {"interpretation": {"directed": True, "measure": "in-degree"}, "intent": "new",
            "steps": [{"id": "d", "op": "degree", "args": {"mode": "in"}}, {"id": "top", "op": "top_k", "args": {"map": "d", "k": 3}}],
            "answer": {"step": "top", "kind": "ranking"}}
    s = Session(p)
    t1 = s.ask("top 3 by incoming links", Scripted([plan]))
    write(p, [(i, 399) for i in range(300)], "a")          # node 399 becomes the most linked
    t2 = s.ask("again", Scripted([plan]))
    assert s.lg.load_info["source"] == "append" and s.data_changes[0]["how"] == "append"
    assert t2["steps_reused"] == 0 and any(f["check"] == "data_changed" for f in t2["reuse_findings"])
    assert t2["answer"][0]["node"] == "399" and t2["answer"] != t1["answer"]
    fresh = Session(p).ask("top 3 by incoming links", Scripted([plan]))
    assert t2["answer"] == fresh["answer"]
    t3 = s.ask("and again", Scripted([plan]))
    assert t3["outcome"] == "exact reuse"


def test_repeated_question_replays_its_plan_without_the_model(tmp_path):
    p = str(tmp_path / "e.txt")
    rows = base_rows()
    rows += [(b, a) for a, b in rows[:1500]]
    write(p, rows)
    plan = {"interpretation": {"directed": True, "measure": "in-degree"}, "intent": "new",
            "steps": [{"id": "d", "op": "degree", "args": {"mode": "in"}}, {"id": "top", "op": "top_k", "args": {"map": "d", "k": 3}}],
            "answer": {"step": "top", "kind": "ranking"}}
    follow = {**plan, "intent": "patch", "based_on": 1, "references": {"them": "the users of turn 1"}}
    s, llm = Session(p, replay_plans=True), Scripted([plan, follow, follow])
    t1 = s.ask("Top 3 by incoming links?", llm)
    t2 = s.ask("top 3 by  incoming links?", llm)                 # same words: no model call, stored results reused
    assert t2["llm_calls"] == 0 and t2["plan_replayed_from"] == 1 and t2["outcome"] == "exact reuse" and t2["answer"] == t1["answer"]
    write(p, [(i, 399) for i in range(300)], "a")
    t3 = s.ask("Top 3 by incoming links?", llm)                  # the data changed: the plan is replayed, the results are not
    assert t3["llm_calls"] == 0 and t3["steps_reused"] == 0 and t3["answer"][0]["node"] == "399"
    s.ask("and for them?", llm)                                  # a plan that leans on the session is never replayed
    t5 = s.ask("and for them?", llm)
    assert t5["llm_calls"] == 1 and "plan_replayed_from" not in t5 and not llm.plans
    s.standing["degree.mode"] = "out"                            # another setting in force: the model is asked again
    assert s._replay("Top 3 by incoming links?") is None
    assert Session(p).replay_plans is False


def test_unreadable_reply_is_asked_again_and_a_failed_turn_stays_visible(tmp_path):
    p = str(tmp_path / "e.txt")
    rows = base_rows()
    rows += [(b, a) for a, b in rows[:1500]]
    write(p, rows)
    plan = {"interpretation": {"directed": True, "measure": "in-degree"}, "intent": "new",
            "steps": [{"id": "d", "op": "degree", "args": {"mode": "in"}}, {"id": "top", "op": "top_k", "args": {"map": "d", "k": 3}}],
            "answer": {"step": "top", "kind": "ranking"}}

    class Raw(Scripted):
        def chat(self, system, user, max_tokens=0, **kw):
            self.seen = getattr(self, "seen", []) + [user]
            r = Reply(text=self.plans.pop(0), input_tokens=1)
            self.usage.add(r)
            return r

    s, llm = Session(p), Raw(["not json at all", json.dumps(plan), "still not", "no", json.dumps(plan)])
    t1 = s.ask("top 3 by incoming links", llm)                   # second reply is read
    assert t1["llm_calls"] == 2 and t1["outcome"] == "recompute"
    t2 = s.ask("from now on count outgoing links", llm)          # both replies unreadable: the turn fails
    assert t2["outcome"] == "error"
    t3 = s.ask("top 3 again", llm)
    assert '"unanswered_turns": [{"turn": 2, "question": "from now on count outgoing links"}]' in llm.seen[-1]
    assert any(f["check"] == "earlier_turn_unanswered" for f in t3["reuse_findings"])
    assert "- turn 2: from now on count outgoing links\nQuestion: top 3 again" in llm.seen[-1]


def test_a_request_outside_the_catalogue_is_reported_as_unsupported(tmp_path):
    p = str(tmp_path / "e.txt")
    write(p, base_rows())
    out = {"interpretation": {"directed": True}, "intent": "new", "steps": [], "answer": None, "unsupported": "a travelling-salesman tour: no operator computes one"}
    plan = {"interpretation": {"directed": True}, "intent": "new", "steps": [{"id": "n", "op": "node_count", "args": {}}], "answer": {"step": "n", "kind": "scalar"}}
    s, llm = Session(p), Scripted([out, plan])
    t1 = s.ask("shortest tour through all users", llm)
    assert t1["outcome"] == "unsupported" and "tour" in t1["unsupported"] and t1.get("answer") is None and not t1.get("error")
    t2 = s.ask("how many users", llm)                            # not an error turn: nothing is carried as unanswered
    assert t2["outcome"] == "recompute" and not any(f["check"] == "earlier_turn_unanswered" for f in t2["reuse_findings"])
