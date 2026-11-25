"""Analysis sessions: follow-up questions on one graph, with reuse decided by rules over the plan.

A session keeps one result store keyed by lineage (see ir.step_key) and a compact state record. Each turn:

  1. the planner sees the profile card and the session state (never the chat history, never raw arrays) and returns
     a complete plan; to build on an earlier turn it copies that turn's steps and changes only what is needed;
  2. the plan is validated and cost-tiered as usual;
  3. rule-based reuse checks run on the plan (no model involved): a scope restriction of a scope-sensitive measure
     has two readings, and unless the user has settled which one is meant, both contracts are produced, the second
     one by a mechanical rewrite of the plan;
  4. the chosen plan is executed against the result store; every step is reported as reused or executed;
  5. the verifier runs on the complete result, whether or not anything was reused.

The outcome of a turn is one of: exact reuse, partial reuse, recompute, clarify.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

import igraph as ig
from pydantic import Field

from .graphs import LoadedGraph, append_in_place, load_graph, profile_card, sidecar_node_table
from .ir import Plan, Step, auto_tier, estimate_cost, execute, extract_answer, plan_keys, step_inputs, step_key, validate, _ref_of
from .llm import LLM, parse_json
from .ops import CATALOGUE, catalogue_text
from .systems import INTERPRETER_SYSTEM, PLANNER_SYSTEM, _jsonable
from .verify import verify


class TurnPlan(Plan):
    """A plan plus what the planner says about its relation to the session."""
    intent: Optional[str] = None                 # new | patch | drill_down | ambiguous
    based_on: Optional[int] = None               # turn the plan builds on
    patch: Optional[dict[str, Any]] = None       # {"type": parameter|scope|measure|extend, "what": "..."}
    references: dict[str, Any] = Field(default_factory=dict)   # "them" -> "the 10 users of turn 1"
    scope_reading: Optional[dict[str, Any]] = None             # {"reading": "A"|"B", "explicit": bool, "quote": "..."}
    set_standing: Optional[dict[str, Any]] = None              # {"pagerank.damping": 0.9}: a setting the user wants from now on
    unsupported: Optional[str] = None            # what the request needs that no combination of operators computes
    code_inputs: dict[str, str] = Field(default_factory=dict)   # fallback only (t2r/fallback.py): name -> step id or "G"
    code_task: Optional[str] = None              # fallback only: what the generated function computes from those inputs


SESSION_RULES = """
SESSION MODE
This is turn {turn} of an analysis session on one graph. SESSION STATE (below) lists the semantics already accepted, the earlier turns with their plans and result sizes, the current selection, and any reading the user has chosen. You do not see earlier answers in full and you do not need them.

S1. Always return a complete, self-contained plan. To build on an earlier turn, copy its steps unchanged (same op, same args) and add or change only what the new request needs. The engine recognises unchanged steps and reuses their stored results, so copying costs nothing. Never type node ids from an earlier answer into the plan when a step produces them.
S2. Keep the accepted semantics (directed, weighted, use_weights) unless the user asks to change them. When the user asks to read the graph differently ("treat links as mutual", "ignore direction", "ignore the weights", "back to directed"), set interpretation.directed / interpretation.weighted to the new reading: the engine loads the graph that way, the new reading becomes the accepted one for later turns, and nothing computed under another reading is reused. Do not emulate a reading change with operators.
S3. Resolve references ("they", "those", "among them", "instead", "the same for ...") against SESSION STATE and record each one in "references", e.g. {{"them": "the 10 users returned in turn 1"}}. A pronoun normally refers to current_selection: the nodes of the most recent answer, or, when that answer was a count or a statistic, the node set it was taken over. Obtain those nodes by copying the step named in produced_by_step (and the steps it depends on) from that turn's plan; first_nodes is only a sample.
S4. Add these fields to the plan JSON:
    "intent": "new" | "patch" | "drill_down" | "ambiguous",
    "based_on": <turn number> | null,
    "patch": null | {{"type": "parameter" | "scope" | "measure" | "extend", "what": "<one line>"}}
    - parameter: same analysis with a changed argument (top 10 -> top 20: change k on the copied top_k step; a longer ranking is always taken from the full NodeMap, never from an earlier shorter list).
    - scope: the same analysis restricted to a group of nodes.
    - measure: the same question with a different measure.
    - extend (intent drill_down): new steps that consume an earlier result.
S5. Restricting a centrality, degree or community measure to a group of nodes has two readings that give different answers:
    A: compute the measure on the whole graph, then keep the group's nodes (restrict_map, or argmax with nodes);
    B: compute the measure on the subgraph induced by the group (induced_subgraph, then the measure on it).
    Plan exactly one reading, the one you judge more plausible (never compute the other reading as a variant or as a second answer part: the engine derives it), and add "scope_reading": {{"reading": "A" | "B", "explicit": true | false, "quote": "<the exact words of the question that settle the reading, or empty>"}}.
    Wording such as "within X", "in X", "among X" does not settle it. It is explicit only when the user says which links count or which computation to use (e.g. "using the overall ranking", "counting only links inside the group"). If SESSION STATE records a chosen scope reading, follow it unless the question says otherwise. The engine shows the user both contracts when the reading is not settled: do not set "clarification" for this.
S6. Standing settings. When the user fixes an operator argument for the rest of the session ("from now on use damping 0.9", "use 1000 samples for estimates from now on"), add "set_standing": {{"<op>.<arg>": <value>, ...}} (e.g. {{"pagerank.damping": 0.9}}; null as the value removes a setting). SESSION STATE lists the standing settings in force: write them into every matching step, including steps copied from earlier turns, unless this question says otherwise.
S8. SESSION STATE may list unanswered_turns: earlier questions of this session that got no answer (the plan could not be read or was invalid). If one of them asked for something that was meant to last ("from now on ...", "treat links as mutual", "use damping 0.9"), it is not in force yet: apply it in this plan as the user asked (set_standing, or the interpretation fields of S2), in addition to answering the current question. Otherwise ignore them.
S9. If no combination of the operators in the catalogue computes exactly what is asked, do not answer a different, easier question in its place and do not approximate: return "steps": [], "answer": null and "unsupported": "<one line: what the request needs that the catalogue lacks>". This is not a clarification (the request is clear; it is outside what can be computed here). Use it only after checking that the operators cannot be combined to give the exact result.
S10. The answer must state the value that was asked for. When the question asks for a difference, a share, a complement, a ratio or a count derived from other counts, compute it with arithmetic (or map_arithmetic for per-node values) and make that step the answer; returning only the ingredients is not an answer. A follow-up that refers to a turn marked unsupported has nothing to build on: plan it from the question itself or return unsupported, never substitute the quantity of another turn.
S7. If SESSION STATE reports a data change, the file or the node table is not what earlier turns saw. Plan as usual (copy steps as in S1): the engine recomputes whatever depends on the changed data.
"""

SCOPE_NOTE = {
    "A": "Scores come from the whole graph, so links from outside the group count; the group only filters who is listed.",
    "B": "Scores are recomputed on the group's own subgraph, so only links inside the group count.",
}


# ----------------------------------------------------------------------------------------------- plan inspection
def _graph_arg(st: Step) -> Any:
    return st.args.get("graph", "G")


def _describe_set(plan: Plan, ref: Any) -> str:
    by = {s.id: s for s in plan.steps}
    if isinstance(ref, list):
        return f"{len(ref)} listed nodes"
    st = by.get(ref) if isinstance(ref, str) else None
    if st is None:
        return str(ref)
    if st.op == "filter_by_attribute":
        return f"{st.args.get('attribute')} {st.args.get('op', '==')} {json.dumps(st.args.get('value'), ensure_ascii=False)}"
    if st.op in ("block_of", "largest_block"):
        return "the community or component selected in step " + st.id
    return f"the node set of step {st.id} ({st.op})"


def scope_patterns(plan: Plan) -> list[dict[str, Any]]:
    """Places where a scope-sensitive NodeMap meets a node group.

    Reading A: restrict_map / argmax(nodes=...) applied to a scope-sensitive map computed on a wider graph.
    Reading B: a scope-sensitive map computed on induced_subgraph(wider graph, group)."""
    by = {s.id: s for s in plan.steps}
    out = []
    for st in plan.steps:
        if st.op in ("restrict_map", "argmax") and st.args.get("nodes") is not None:
            m = by.get(st.args.get("map")) if isinstance(st.args.get("map"), str) else None
            if m is not None and CATALOGUE[m.op].scope_sensitive and CATALOGUE[m.op].returns == "NodeMap":
                out.append({"reading": "A", "step": st.id, "measure": m.op, "measure_step": m.id, "nodes": st.args["nodes"],
                            "wider_graph": _graph_arg(m), "group": _describe_set(plan, st.args["nodes"])})
        spec = CATALOGUE.get(st.op)
        if spec is not None and spec.scope_sensitive and spec.returns == "NodeMap":
            g = by.get(_graph_arg(st)) if isinstance(_graph_arg(st), str) else None
            if g is not None and g.op == "induced_subgraph":
                out.append({"reading": "B", "step": st.id, "measure": st.op, "measure_step": st.id, "nodes": g.args.get("nodes"),
                            "subgraph_step": g.id, "wider_graph": _graph_arg(g), "group": _describe_set(plan, g.args.get("nodes"))})
    return out


def answer_lineage(plan: Plan) -> set[str]:
    """Steps the answer depends on. A plan may also compute variants; the reading that matters is the answer's."""
    ids = {s.id for s in plan.steps}
    by = {s.id: s for s in plan.steps}
    a = plan.answer
    todo = [str(r).split(".")[0] for r in (([a.step] if a and a.step else []) + (list((a.steps or {}).values()) if a else []))]
    seen: set[str] = set()
    while todo:
        x = todo.pop()
        if x in by and x not in seen:
            seen.add(x)
            todo.extend(step_inputs(by[x], ids))
    return seen


def _used(plan: Plan, sid: str) -> bool:
    ids = {s.id for s in plan.steps}
    if any(sid in step_inputs(s, ids) for s in plan.steps):
        return True
    a = plan.answer
    refs = ([a.step] if a and a.step else []) + (list((a.steps or {}).values()) if a else [])
    return any(str(r).split(".")[0] == sid for r in refs)


def other_reading(plan: Plan, pat: dict[str, Any]) -> Plan:
    """Rewrite one scope pattern into the other reading. Step ids that later steps read are kept."""
    new = plan.model_copy(deep=True)
    by = {s.id: s for s in new.steps}
    i = next(k for k, s in enumerate(new.steps) if s.id == pat["step"])
    st = new.steps[i]
    if pat["reading"] == "A":
        m = by[pat["measure_step"]]
        margs = {k: v for k, v in m.args.items() if k != "graph"}
        sub = Step(id=f"{st.id}_sub", op="induced_subgraph", args={"graph": pat["wider_graph"], "nodes": pat["nodes"]},
                   note="scope reading B: the group's own subgraph")
        if st.op == "restrict_map":
            new.steps[i:i + 1] = [sub, Step(id=st.id, op=m.op, args={**margs, "graph": sub.id}, note=f"{m.op} recomputed on the group's subgraph")]
        else:  # argmax with nodes
            mm = Step(id=f"{st.id}_m", op=m.op, args={**margs, "graph": sub.id}, note=f"{m.op} recomputed on the group's subgraph")
            new.steps[i:i + 1] = [sub, mm, Step(id=st.id, op="argmax", args={"map": mm.id}, note=st.note)]
        if not _used(new, m.id):
            new.steps = [s for s in new.steps if s.id != m.id]
    else:
        margs = {k: v for k, v in st.args.items() if k != "graph"}
        whole = Step(id=f"{st.id}_all", op=st.op, args={**margs, "graph": pat["wider_graph"]}, note=f"{st.op} on the wider graph")
        new.steps[i:i + 1] = [whole, Step(id=st.id, op="restrict_map", args={"map": whole.id, "nodes": pat["nodes"]},
                                         note="scope reading A: whole-graph scores, group members kept")]
        if not _used(new, pat["subgraph_step"]):
            new.steps = [s for s in new.steps if s.id != pat["subgraph_step"]]
    if isinstance(new, TurnPlan):
        other = "B" if pat["reading"] == "A" else "A"
        new.scope_reading = {"reading": other, "explicit": False, "quote": "", "source": "rewritten by the engine"}
    return new


def force_reading(plan: Plan, reading: str) -> tuple[Plan, int]:
    """Put every scope pattern the answer depends on into one reading. Returns the plan and the number of rewrites.

    A planner may restrict several measures in one plan, or compute both readings side by side; a contract has to
    hold for every part of the answer, so all of them are rewritten."""
    n = 0
    for _ in range(4 * len(plan.steps) + 4):
        lineage = answer_lineage(plan)
        todo = [p for p in scope_patterns(plan) if p["step"] in lineage and p["reading"] != reading]
        if not todo:
            break
        plan = other_reading(plan, todo[0])
        n += 1
    if n and isinstance(plan, TurnPlan):
        plan.scope_reading = {"reading": reading, "explicit": False, "quote": "", "source": "rewritten by the engine"}
        # two answer parts that became the same computation are reported once
        if plan.answer is not None and plan.answer.steps:
            keys, seen, keep = {"G": "G"}, set(), {}
            for st in plan.steps:
                keys[st.id] = step_key(st, keys, 0)
            for lab, ref in plan.answer.steps.items():
                sid, _, fld = str(ref).partition(".")
                sig = (keys.get(sid, sid), fld)
                if sig not in seen:
                    seen.add(sig); keep[lab] = ref
            plan.answer.steps = keep
    return plan, n


def contract_text(pat: dict[str, Any], reading: str) -> str:
    if reading == "A":
        return f"{pat['measure']} computed on the whole graph, then only nodes with {pat['group']} are kept. " + SCOPE_NOTE["A"]
    return f"{pat['measure']} computed on the subgraph induced by nodes with {pat['group']}. " + SCOPE_NOTE["B"]


def conventions(lg: LoadedGraph) -> list[str]:
    """How the file was read where it changes a count: printed with every answer, by plan or by code."""
    f = getattr(lg, "facts", None)
    n = getattr(f, "n_self_loops", 0) if f is not None else 0
    return [f"{n:,} of the {f.n_rows:,} rows link a node to itself; they are left out of the graph, so counts of rows, links and degrees do not include them"] if n else []


def _size(val: Any) -> Any:
    if isinstance(val, ig.Graph):
        return {"n": val.vcount(), "m": val.ecount()}
    if isinstance(val, (dict, list)):
        return len(val)
    return None


def _nodes_of(val: Any) -> Optional[list]:
    if isinstance(val, dict) and "node" in val:
        return [val["node"]]
    if isinstance(val, list) and val:
        if isinstance(val[0], dict) and "node" in val[0]:
            return [r["node"] for r in val]
        if isinstance(val[0], (str, int)):
            return list(val)
    return None


# ----------------------------------------------------------------------------------------------------- the session
class Session:
    def __init__(self, path: str, name: Optional[str] = None, description: str = "", seed: int = 1, budget_ops: float = 1e10,
                 reuse: bool = True, on_ambiguity: str = "ask", replay_plans: Optional[bool] = None, code_fallback: Optional[bool] = None):
        """on_ambiguity: "ask" returns both contracts and waits for choose(); "both" executes both and reports how far
        the answers differ; "planner" goes with the planner's reading and states it (what a system without the rule does)."""
        self.path, self.name, self.description = path, name or os.path.splitext(os.path.basename(path))[0], description
        self.seed, self.budget_ops, self.reuse, self.on_ambiguity = seed, budget_ops, reuse, on_ambiguity
        self.store: dict = {}                    # lineage key -> stored result
        self.turns: list[dict[str, Any]] = []
        self.semantics: Optional[dict[str, bool]] = None      # accepted at the first answered turn
        self.scope_choice: Optional[dict[str, Any]] = None    # {"reading": "A"|"B", "turn": k}
        self.clarifications: list[dict[str, Any]] = []
        self._lgs: dict[str, LoadedGraph] = {}
        self._ov: dict[str, bool] = {}            # load override in force (the accepted reading)
        self._ov_of: dict[int, dict] = {}
        self.standing: dict[str, Any] = {}        # "op.arg" -> value, set by the user for the rest of the session
        self.data_changes: list[dict[str, Any]] = []
        # replay_plans: a question asked before in the same words is answered from its earlier plan, with no model call
        # (see _replayable for when that is safe). Default from T2R_PLAN_REPLAY=1.
        self.replay_plans = os.environ.get("T2R_PLAN_REPLAY") == "1" if replay_plans is None else replay_plans
        self._plan_memo: dict[str, dict[str, Any]] = {}
        # code_fallback: an "unsupported" request is computed by generated code on inputs prepared by operators, and
        # answered only when two separately written functions agree (t2r/fallback.py). Default from T2R_CODE_FALLBACK=1.
        self.code_fallback = os.environ.get("T2R_CODE_FALLBACK") == "1" if code_fallback is None else code_fallback
        self._sig = self._signature()
        self.lg = self._load(None)
        self.card = profile_card(self.lg, with_inference=True)

    # ------------------------------------------------------------------ the data under the session
    def _signature(self) -> tuple:
        """Size and modification time of the edge file and the node table: a cheap test for a change between turns."""
        out = []
        for p in (self.path, sidecar_node_table(self.path)):
            if p and os.path.exists(p):
                st = os.stat(p)
                out.append((p, st.st_size, st.st_mtime_ns))
        return tuple(out)

    def _refresh(self) -> None:
        """Called at the start of every turn. If a file changed, drop the loaded graphs and profile again. Stored results
        need no clearing: their keys carry the content hashes, so results of the old data can no longer be matched."""
        sig = self._signature()
        if sig == self._sig:
            return
        old = (self.lg.facts.sha1, (self.lg.g["node_table"]["sha1"] if "node_table" in self.lg.g.attributes() else None), self.lg.g.vcount(), self.lg.g.ecount())
        edge_only = [a for a, b in zip(self._sig, sig) if a != b] == [x for x in self._sig if x[0] == self.path] and len(sig) == len(self._sig)
        self._sig = sig
        k = json.dumps(self._ov or {}, sort_keys=True)
        cur = self._lgs.get(k)
        # the file only grew at its end: add the new rows to the loaded graph (None = not safe, load again)
        grown = append_in_place(cur, self.path, self.description, self._ov or None) if (edge_only and cur is not None) else None
        self._lgs.clear(); self._ov_of.clear()
        if grown is not None:
            self._lgs[k] = grown
        self.lg = self._load(self._ov)
        self.card = profile_card(self.lg, with_inference=True)
        new = (self.lg.facts.sha1, (self.lg.g["node_table"]["sha1"] if "node_table" in self.lg.g.attributes() else None), self.lg.g.vcount(), self.lg.g.ecount())
        if new[:2] != old[:2]:
            what = [w for w, a, b in (("edge file", old[0], new[0]), ("node table", old[1], new[1])) if a != b]
            self.data_changes.append({"before_turn": len(self.turns) + 1, "changed": what, "nodes": [old[2], new[2]], "edges": [old[3], new[3]],
                                      "how": self.lg.load_info.get("source")})

    def _standing(self, plan: "TurnPlan") -> list[dict]:
        """Record settings the plan declares, then write the settings in force into every matching step (rule-based)."""
        findings = []
        for k, v in (plan.set_standing or {}).items():
            op, _, arg = str(k).partition(".")
            if op not in CATALOGUE or arg not in CATALOGUE[op].params:
                findings.append({"check": "standing_setting", "ok": False, "severity": "warn", "detail": f"unknown setting {k!r} ignored"})
            elif v is None:
                self.standing.pop(k, None)
            else:
                self.standing[k] = v
                findings.append({"check": "standing_setting", "ok": True, "severity": "info", "detail": f"{k} = {v} from this turn on"})
        declared = set(plan.set_standing or {})
        for st in plan.steps:
            for k, v in self.standing.items():
                op, _, arg = k.partition(".")
                if st.op != op:
                    continue
                if arg not in st.args:
                    st.args[arg] = v
                    findings.append({"check": "standing_setting_applied", "ok": True, "severity": "info", "detail": f"step {st.id}: {arg} = {v} (standing setting)"})
                elif st.args[arg] != v and k not in declared:
                    findings.append({"check": "standing_setting_overridden", "ok": False, "severity": "warn",
                                     "detail": f"step {st.id} uses {arg} = {st.args[arg]} although the standing setting is {v}"})
        return findings

    # ------------------------------------------------------------------ graph under a given reading
    def _load(self, override: Optional[dict]) -> LoadedGraph:
        k = json.dumps(override or {}, sort_keys=True)
        if k not in self._lgs:
            self._lgs[k] = load_graph(self.name, self.path, self.description, override=override or None)
        return self._lgs[k]

    def _graph_for(self, plan: Plan) -> tuple[LoadedGraph, list[dict]]:
        """The graph under the plan's interpretation, and findings about a change of semantics within the session."""
        base = self._load(self._ov)
        ov = dict(self._ov)
        changed = {}
        for k in ("directed", "weighted"):
            v = plan.interpretation.get(k)
            cur = base.g.is_directed() if k == "directed" else "weight" in base.g.es.attributes()
            if isinstance(v, bool) and v != cur and not (k == "weighted" and v and not base.facts.weight_column_numeric):
                ov[k] = v
                changed[k] = {"was": cur, "now": v}
        findings = []
        if changed and self.semantics is not None:
            findings.append({"check": "semantics_changed", "ok": False, "severity": "warn",
                             "detail": f"this turn reads the graph differently from the session so far ({changed}); nothing computed under the earlier reading is reused"})
        lg = self._load(ov) if changed else base
        self._ov_of[id(lg)] = ov
        return lg, findings

    # ------------------------------------------------------------------ what the planner sees
    def state(self, max_turns: int = 6) -> dict[str, Any]:
        done = [t for t in self.turns if t.get("plan")]
        turns = []
        for t in done[-max_turns:]:
            sizes = t.get("sizes", {})
            turns.append({"turn": t["turn"], "question": t["question"], "intent": t.get("intent"), "outcome": t["outcome"],
                          "measure": (t["plan"].get("interpretation") or {}).get("measure"),
                          "steps": [{"id": s["id"], "op": s["op"], "args": s["args"], "returns": CATALOGUE[s["op"]].returns, "size": sizes.get(s["id"])}
                                    for s in t["plan"]["steps"]],
                          "answer": t["plan"].get("answer"), "scope_reading": (t["plan"].get("scope_reading") or {}).get("reading")})
        sel = next((t for t in reversed(done) if t.get("selection_info")), None)
        failed = [{"turn": t["turn"], "question": t["question"]} for t in self.turns[-max_turns:] if t.get("outcome") == "error"]
        return {"turn": len(self.turns) + 1, "graph": self.name, "accepted_semantics": self.semantics, **({"unanswered_turns": failed} if failed else {}),
                "standing_settings": self.standing, "data_changes": self.data_changes[-3:],
                "chosen_scope_reading": self.scope_choice,
                "current_selection": None if sel is None else {"from_turn": sel["turn"], "produced_by_step": sel["selection_info"]["step"], "op": sel["selection_info"]["op"],
                                                               "args": sel["selection_info"]["args"], "count": sel["selection_info"]["count"], "first_nodes": sel["selection_info"]["nodes"]},
                "earlier_turns_omitted": max(0, len(done) - max_turns), "turns": turns, "clarifications": self.clarifications[-5:]}

    # ------------------------------------------------------------------ reuse preview and decision
    def preview(self, plan: Plan, lg: LoadedGraph) -> dict[str, Any]:
        """Which steps a plan would reuse, without executing it."""
        keys = plan_keys(plan, lg, self.seed)
        n, m = lg.g.vcount(), lg.g.ecount()
        rows = []
        for st in plan.steps:
            hit = self.store.get(keys[st.id]) if self.reuse else None
            rows.append({"step": st.id, "op": st.op, "key": keys[st.id][:12], "reuse": hit is not None,
                         "seconds_saved": round(hit["seconds"], 3) if hit else None,
                         "estimated_ops": None if hit else estimate_cost(st.op, st.args, n, m)})
        return {"steps": rows, "reused": sum(r["reuse"] for r in rows), "to_execute": sum(not r["reuse"] for r in rows)}

    def reuse_checks(self, plan: TurnPlan, question: str) -> tuple[list[dict], Optional[dict]]:
        """Rule-based checks. Returns (findings, the scope pattern that is not settled, or None)."""
        findings: list[dict] = []
        lineage = answer_lineage(plan)
        pats = [p for p in scope_patterns(plan) if p["step"] in lineage]     # the reading of the answer, not of a variant
        if not pats:
            return findings, None
        readings = sorted({p["reading"] for p in pats})
        measures = sorted({p["measure"] for p in pats})
        pat = {**pats[0], "measure": " and ".join(measures), "reading": readings[0] if len(readings) == 1 else "mixed"}
        sr = plan.scope_reading or {}
        quote = str(sr.get("quote") or "").strip()
        explicit = bool(sr.get("explicit")) and len(quote) >= 4 and quote.lower() in question.lower() and len(readings) == 1
        if sr.get("explicit") and not explicit:
            findings.append({"check": "scope_reading_quote", "ok": False, "severity": "warn",
                             "detail": "the planner called the scope reading explicit but did not quote words of the question that settle it (or mixed both readings); treated as not settled"})
        if explicit:
            findings.append({"check": "scope_reading", "ok": True, "severity": "info",
                             "detail": f"reading {pat['reading']} settled by the question: \"{quote}\""})
            return findings, None
        if self.scope_choice is not None:
            findings.append({"check": "scope_reading", "ok": True, "severity": "info",
                             "detail": f"reading {self.scope_choice['reading']} carried over from the user's choice in turn {self.scope_choice['turn']}"})
            return findings, ({**pat, "apply_choice": True} if readings != [self.scope_choice["reading"]] else None)
        findings.append({"check": "scope_ambiguity", "ok": False, "severity": "warn",
                         "detail": f"{pat['measure']} restricted to {pat['group']} has two readings that give different answers; reusing or recomputing depends on which is meant"})
        return findings, pat

    # ------------------------------------------------------------------ running one plan
    def _run(self, plan: TurnPlan, lg: LoadedGraph, question: str, turn_no: Optional[int] = None) -> dict[str, Any]:
        t0 = time.time()
        ctx, trace = execute(plan, lg, seed=self.seed, cache=self.store if self.reuse else None)
        dt = time.time() - t0
        findings = verify(plan, ctx, question=question)       # a reused result is verified like a fresh one
        reused = sum(t["cached"] for t in trace)
        outcome = "exact reuse" if reused == len(trace) and trace else ("partial reuse" if reused else "recompute")
        turn_no = turn_no or len(self.turns)                   # the turn being run is already in the list
        for t in trace:                                        # where each reused result was first computed
            entry = self.store.get(ctx.keys[t["step"]]) if self.reuse else None
            if entry is not None:
                if t["cached"]:
                    t["from_turn"] = entry.get("turn")
                else:
                    entry["turn"] = turn_no
        lineage = answer_lineage(plan)
        readings = sorted({p["reading"] for p in scope_patterns(plan) if p["step"] in lineage})
        ans_step = plan.answer.step if plan.answer and plan.answer.step else None
        # the current selection: the nodes of the answer, or, for an answer that is a count or a statistic, the node set it was taken over
        sel, sel_step = (_nodes_of(ctx.values.get(ans_step)) if ans_step else None), ans_step
        if sel is None:
            for st in reversed(plan.steps):
                if st.id in lineage and CATALOGUE[st.op].returns == "NodeSet" and isinstance(ctx.values.get(st.id), list):
                    sel, sel_step = list(ctx.values[st.id]), st.id
                    break
        by = {s.id: s for s in plan.steps}
        sel_info = None if sel is None else {"step": sel_step, "op": by[sel_step].op, "args": by[sel_step].args, "count": len(sel), "nodes": sel[:20]}
        return {"plan": plan.model_dump(), "trace": trace, "findings": findings, "answer": _jsonable(extract_answer(plan, ctx)),
                "outcome": outcome, "steps_reused": reused, "steps_executed": len(trace) - reused, "execute_seconds": round(dt, 3),
                "seconds_saved": round(sum(t.get("seconds_saved", 0) for t in trace), 3),
                "sizes": {t["step"]: _size(ctx.values[t["step"]]) for t in trace},
                "selection": None if sel is None else sel[:200], "selection_info": sel_info,
                "reading": readings[0] if len(readings) == 1 else None,
                "conventions": conventions(lg),
                "keys": {s: k[:12] for s, k in ctx.keys.items()}}

    def _prompt(self, question: str) -> tuple[str, str, str, str]:
        """(fixed system, fixed user, system, user) of the planner call for the next turn."""
        # the catalogue and the session rules are the same on every turn, so they go first as the fixed part (cacheable);
        # the turn number, which the rules mention, is then given in the message instead
        cached = os.environ.get("T2R_PROMPT_CACHE") == "1"
        n = len(self.turns) + 1
        fixed_sys = PLANNER_SYSTEM.format(catalogue=catalogue_text()) + SESSION_RULES.format(turn="N (given in the message)" if cached else n)
        system = ""
        d = f"Dataset description (from the user): {self.description}\n" if self.description else ""
        lost = [t for t in self.turns[-6:] if t.get("outcome") == "error"]
        pending = ("Earlier requests of this session that got no answer (rule S8: if one asked for a lasting change, apply it in this plan):\n"
                   + "".join(f"- turn {t['turn']}: {t['question']}\n" for t in lost)) if lost else ""
        fixed_user = f"PROFILE CARD:\n{json.dumps(self.card, default=str, ensure_ascii=False)}\n\n"   # changes only when the data does
        user = ((f"Turn: {n}\n" if cached else "") + f"SESSION STATE:\n"
                f"{json.dumps(self.state(), default=str, ensure_ascii=False)}\n\nGraph file: {os.path.basename(self.path)}\n{d}{pending}Question: {question}")
        return fixed_sys, fixed_user, system, user

    def _plan(self, question: str, llm: LLM, lg_hint: LoadedGraph) -> tuple[TurnPlan, list[str]]:
        fixed_sys, fixed_user, system, user = self._prompt(question)
        reply = llm.chat(system, user, fixed_system=fixed_sys, fixed_user=fixed_user).text
        try:
            plan = TurnPlan.model_validate(parse_json(reply))
        except Exception as e:  # noqa: BLE001  a reply that is not a plan: ask once more, saying what was wrong
            reply = llm.chat(system, user + f"\n\nYour previous reply could not be read as a plan ({type(e).__name__}: {str(e)[:300]}). "
                             "Return only the plan as one JSON object.", max_tokens=16000, fixed_system=fixed_sys, fixed_user=fixed_user).text
            plan = TurnPlan.model_validate(parse_json(reply))
        lg, _ = self._graph_for(plan)
        problems = validate(plan, lg, self.budget_ops)
        if problems:
            fix = llm.chat(system, user + "\n\nYour previous plan had these problems, return a corrected full plan:\n" + "\n".join(problems)
                           + f"\n\nPrevious plan:\n{plan.model_dump_json()}", fixed_system=fixed_sys, fixed_user=fixed_user)
            plan = TurnPlan.model_validate(parse_json(fix.text))
            lg, _ = self._graph_for(plan)
            problems = validate(plan, lg, self.budget_ops)
        return plan, problems

    # ------------------------------------------------------------------ plan replay (no model call for a repeated question)
    def _context(self) -> str:
        """What a plan's meaning depends on besides the question: the settings, the chosen reading, how the graph is read."""
        return json.dumps([self.standing, (self.scope_choice or {}).get("reading"), self._ov, self.description], sort_keys=True, default=str)

    def _replayable(self, plan: TurnPlan, turn: dict) -> bool:
        """A plan may be replayed for the same words only if the planner declared that it stands on its own: a new
        question, no reference to an earlier turn or to the current selection, no setting declared, no open reading.
        The data may change in between: a replayed plan is validated and executed on the data as it is then."""
        return (plan.intent == "new" and plan.based_on is None and not plan.references and not plan.set_standing and not plan.clarification
                and not turn.get("contracts") and turn.get("outcome") in ("exact reuse", "partial reuse", "recompute"))

    def _replay(self, question: str) -> Optional[TurnPlan]:
        memo = self._plan_memo.get(" ".join(question.lower().split()))
        if not self.replay_plans or memo is None or memo["context"] != self._context():
            return None
        plan = TurnPlan.model_validate(json.loads(memo["plan"]))
        lg, _ = self._graph_for(plan)
        if validate(plan, lg, self.budget_ops):                   # no longer valid on the data as it is now: ask the planner
            return None
        self._replayed_from = memo["turn"]
        return plan

    def ask(self, question: str, llm: LLM, explain: bool = False) -> dict[str, Any]:
        t0 = time.time()
        c0, i0, o0, u0 = llm.usage.calls, llm.usage.input_tokens, llm.usage.output_tokens, llm.usage.cost_usd
        turn: dict[str, Any] = {"turn": len(self.turns) + 1, "question": question, "outcome": "error"}
        try:
            self._refresh()
            plan, problems = self._replay(question), []
            if plan is not None:
                turn["plan_replayed_from"] = self._replayed_from
            else:
                plan, problems = self._plan(question, llm, self.lg)
            as_planned, context = plan.model_dump_json(), self._context()
            turn.update(self.submit(plan, question, problems=problems, _turn=turn))
            if turn.get("outcome") == "unsupported" and self.code_fallback:
                from .fallback import run_fallback
                run_fallback(self, turn, question, llm)
            if "plan_replayed_from" in turn:
                turn.setdefault("reuse_findings", []).append({"check": "plan_replayed", "ok": True, "severity": "info",
                                                              "detail": f"same question as turn {turn['plan_replayed_from']}: its plan was run again without asking the model"})
            elif self.replay_plans and not problems and context == self._context() and self._replayable(plan, turn):
                self._plan_memo[" ".join(question.lower().split())] = {"plan": as_planned, "context": context, "turn": turn["turn"]}
            if explain:
                self.explain(turn, llm)
        except Exception as e:  # noqa: BLE001
            turn["error"] = f"{type(e).__name__}: {e}"
        turn.update({"llm_calls": llm.usage.calls - c0, "tokens_in": llm.usage.input_tokens - i0, "tokens_out": llm.usage.output_tokens - o0,
                     "cost_usd": round(llm.usage.cost_usd - u0, 5), "seconds": round(time.time() - t0, 3)})
        if turn not in self.turns:
            self.turns.append(turn)
        return turn

    def explain(self, turn: dict, llm: LLM) -> dict:
        """Prose for an answered turn, written from the executed trace (also after a reading is chosen or a plan is edited)."""
        if turn.get("trace"):
            p = turn["plan"]
            c0, i0, o0, u0 = llm.usage.calls, llm.usage.input_tokens, llm.usage.output_tokens, llm.usage.cost_usd
            reading = f"Scope reading in force: {turn['reading']} ({SCOPE_NOTE[turn['reading']]})\n" if turn.get("reading") else ""
            turn["explanation"] = llm.chat(INTERPRETER_SYSTEM, f"Question: {turn['question']}\nPlan rationale: {p.get('rationale')}\nInterpretation: {json.dumps(p.get('interpretation'), default=str)}\n{reading}"
                                           f"Trace: {json.dumps(turn['trace'], default=str)[:6000]}\nFindings: {json.dumps(turn['findings'])[:3000]}\n"
                                           f"Extracted answer: {json.dumps(turn['answer'], default=str)[:2000]}").text.strip()
            for k, v in (("llm_calls", llm.usage.calls - c0), ("tokens_in", llm.usage.input_tokens - i0), ("tokens_out", llm.usage.output_tokens - o0)):
                turn[k] = (turn.get(k) or 0) + v
            turn["cost_usd"] = round((turn.get("cost_usd") or 0) + llm.usage.cost_usd - u0, 5)
        return turn

    def submit(self, plan: TurnPlan | dict, question: str, problems: Optional[list[str]] = None, _turn: Optional[dict] = None) -> dict[str, Any]:
        """Decide and run a plan: from the planner, or edited by the user in the interface (plan mutation)."""
        if isinstance(plan, dict):
            plan = TurnPlan.model_validate(plan)
        turn = _turn if _turn is not None else {"turn": len(self.turns) + 1, "question": question}
        if turn not in self.turns:
            self._refresh()
            self.turns.append(turn)
        std_findings = self._standing(plan)
        lg, sem_findings = self._graph_for(plan)
        problems = validate(plan, lg, self.budget_ops) if problems is None else problems
        turn.update({"intent": plan.intent, "based_on": plan.based_on, "patch": plan.patch, "references": plan.references,
                     "clarification": plan.clarification, "plan": plan.model_dump()})
        if problems:
            turn.update({"outcome": "error", "error": "invalid plan: " + "; ".join(problems)})
            return turn
        if plan.unsupported and not plan.steps:
            turn.update({"outcome": "unsupported", "unsupported": plan.unsupported})
            return turn
        if plan.clarification and not plan.steps:
            self.clarifications.append({"turn": turn["turn"], "asked": plan.clarification})
            turn["outcome"] = "clarify"
            return turn
        turn["tier_notes"] = auto_tier(plan, lg, self.budget_ops)
        checks, pat = self.reuse_checks(plan, question)
        data = [{"check": "data_changed", "ok": False, "severity": "warn",
                 "detail": f"the {' and '.join(c['changed'])} changed before this turn; results of the earlier data are not reused"}
                for c in self.data_changes if c["before_turn"] == turn["turn"]]
        lost = [t["turn"] for t in self.turns[-7:-1] if t.get("outcome") == "error"]
        unanswered = [{"check": "earlier_turn_unanswered", "ok": False, "severity": "warn",
                       "detail": f"turn{'s' if len(lost) > 1 else ''} {', '.join(map(str, lost))} got no answer; if it asked for a lasting change, check that this answer reflects it"}] if lost else []
        turn["reuse_findings"] = data + unanswered + std_findings + sem_findings + checks
        if pat is not None and pat.get("apply_choice"):          # the user already chose a reading: rewrite to it, say so
            alt, _ = force_reading(plan, self.scope_choice["reading"])
            if not validate(alt, lg, self.budget_ops):
                auto_tier(alt, lg, self.budget_ops)
                plan = alt
            pat = None
        if pat is not None and self.on_ambiguity != "planner":
            contracts = []
            for r in ([pat["reading"], "B" if pat["reading"] == "A" else "A"] if pat["reading"] != "mixed" else ["A", "B"]):
                alt, n = force_reading(plan, r)
                if n and validate(alt, lg, self.budget_ops):
                    continue
                auto_tier(alt, lg, self.budget_ops)
                contracts.append({"reading": r, "source": "engine rewrite" if n else "planner", "contract": contract_text(pat, r), "plan": alt.model_dump(), "preview": self.preview(alt, lg)})
            turn["contracts"] = contracts
            turn["_pending"] = {"lg": lg, "question": question}
            if self.on_ambiguity == "ask" and len(contracts) == 2:
                turn["outcome"] = "clarify"
                turn["clarification"] = f"Two readings of this request give different answers. (A) {contract_text(pat, 'A')} (B) {contract_text(pat, 'B')} Which one do you mean?"
                self.clarifications.append({"turn": turn["turn"], "asked": "scope reading A or B", "group": pat["group"], "measure": pat["measure"]})
                return turn
            for c in contracts:                                   # "both": run each and compare
                c["result"] = self._run(TurnPlan.model_validate(c["plan"]), lg, question)
            if len(contracts) == 2:
                a, b = (c["result"].get("selection") or [] for c in contracts)
                k = min(len(a), len(b))
                turn["readings_compared"] = {"k": k, "shared": len(set(a[:k]) & set(b[:k])), "same_order": a[:k] == b[:k]}
            self._accept(turn, contracts[0]["result"], lg)
            turn["outcome"] = "both readings shown"
            return turn
        if pat is not None:                                        # on_ambiguity == "planner": proceed, state the reading
            turn["reuse_findings"].append({"check": "scope_reading", "ok": True, "severity": "info", "detail": f"reading {pat['reading']} assumed by the planner; the other reading was not shown"})
        self._accept(turn, self._run(plan, lg, question), lg)
        return turn

    def choose(self, index: int, turn_no: Optional[int] = None) -> dict[str, Any]:
        """The user picks one of the contracts of a pending turn. The choice is remembered for later turns."""
        turn = self.turns[(turn_no or len(self.turns)) - 1]
        c = turn["contracts"][index]
        pend = turn["_pending"]
        self.scope_choice = {"reading": c["reading"], "turn": turn["turn"]}
        self.clarifications.append({"turn": turn["turn"], "answered": f"scope reading {c['reading']}", "contract": c["contract"]})
        turn["reuse_findings"].append({"check": "scope_reading", "ok": True, "severity": "info", "detail": f"reading {c['reading']} chosen by the user"})
        self._accept(turn, c.get("result") or self._run(TurnPlan.model_validate(c["plan"]), pend["lg"], pend["question"], turn["turn"]), pend["lg"])
        turn["clarification"] = None
        return turn

    def use_reading(self, reading: str, turn_no: int) -> dict[str, Any]:
        """The user asks for an answered turn under the other scope reading. Runs as a new turn; the choice is remembered."""
        src = self.turns[turn_no - 1]
        plan, _ = force_reading(TurnPlan.model_validate(src["plan"]), reading)
        self.scope_choice = {"reading": reading, "turn": len(self.turns) + 1}
        self.clarifications.append({"turn": len(self.turns) + 1, "answered": f"scope reading {reading}", "for_turn": turn_no})
        plan.intent, plan.based_on, plan.patch = "patch", turn_no, {"type": "scope", "what": f"turn {turn_no} under scope reading {reading}"}
        return self.submit(plan, f"{src['question']} (reading {reading})")

    def ledger(self) -> dict[str, Any]:
        """Running totals of the session, for the interface and the audit record."""
        done = [t for t in self.turns if t.get("trace")]
        tot = lambda k: round(sum(t.get(k) or 0 for t in self.turns), 4)  # noqa: E731
        return {"turns": len(self.turns), "answered": len(done), "steps_reused": tot("steps_reused"), "steps_executed": tot("steps_executed"),
                "execute_seconds": tot("execute_seconds"), "seconds_saved": tot("seconds_saved"), "llm_calls": tot("llm_calls"),
                "tokens_in": tot("tokens_in"), "tokens_out": tot("tokens_out"), "cost_usd": tot("cost_usd"), "stored_results": len(self.store),
                "accepted_semantics": self.semantics, "scope_choice": self.scope_choice, "reuse": self.reuse,
                "standing_settings": self.standing, "data_changes": self.data_changes,
                "outcomes": {o: sum(t.get("outcome") == o for t in self.turns) for o in ("exact reuse", "partial reuse", "recompute", "clarify", "unsupported", "answer by code", "unconfirmed", "error")}}

    def _accept(self, turn: dict, result: dict, lg: LoadedGraph) -> None:
        turn.update(result)
        self._ov = self._ov_of.get(id(lg), self._ov)
        self.semantics = {"directed": lg.g.is_directed(), "weighted": "weight" in lg.g.es.attributes()}

    def public(self, turn: dict) -> dict:
        """A turn without internal handles, safe to serialise."""
        return json.loads(json.dumps({k: v for k, v in turn.items() if not k.startswith("_")}, default=str))
