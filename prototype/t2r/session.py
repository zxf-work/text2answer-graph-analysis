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

from .graphs import LoadedGraph, load_graph, profile_card
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


SESSION_RULES = """
SESSION MODE
This is turn {turn} of an analysis session on one graph. SESSION STATE (below) lists the semantics already accepted, the earlier turns with their plans and result sizes, the current selection, and any reading the user has chosen. You do not see earlier answers in full and you do not need them.

S1. Always return a complete, self-contained plan. To build on an earlier turn, copy its steps unchanged (same op, same args) and add or change only what the new request needs. The engine recognises unchanged steps and reuses their stored results, so copying costs nothing. Never type node ids from an earlier answer into the plan when a step produces them.
S2. Keep the accepted semantics (directed, weighted, use_weights) unless the user asks to change them.
S3. Resolve references ("they", "those", "instead", "the same for ...") against SESSION STATE and record each one in "references", e.g. {{"them": "the 10 users returned in turn 1"}}.
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
                 reuse: bool = True, on_ambiguity: str = "ask"):
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
        self.lg = self._load(None)
        self.card = profile_card(self.lg, with_inference=True)

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
        sel = next((t for t in reversed(done) if t.get("selection")), None)
        return {"turn": len(self.turns) + 1, "graph": self.name, "accepted_semantics": self.semantics,
                "chosen_scope_reading": self.scope_choice,
                "current_selection": None if sel is None else {"from_turn": sel["turn"], "count": len(sel["selection"]), "nodes": sel["selection"][:20]},
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
    def _run(self, plan: TurnPlan, lg: LoadedGraph, question: str) -> dict[str, Any]:
        t0 = time.time()
        ctx, trace = execute(plan, lg, seed=self.seed, cache=self.store if self.reuse else None)
        dt = time.time() - t0
        findings = verify(plan, ctx, question=question)       # a reused result is verified like a fresh one
        reused = sum(t["cached"] for t in trace)
        outcome = "exact reuse" if reused == len(trace) and trace else ("partial reuse" if reused else "recompute")
        ans_step = plan.answer.step if plan.answer and plan.answer.step else None
        return {"plan": plan.model_dump(), "trace": trace, "findings": findings, "answer": _jsonable(extract_answer(plan, ctx)),
                "outcome": outcome, "steps_reused": reused, "steps_executed": len(trace) - reused, "execute_seconds": round(dt, 3),
                "seconds_saved": round(sum(t.get("seconds_saved", 0) for t in trace), 3),
                "sizes": {t["step"]: _size(ctx.values[t["step"]]) for t in trace},
                "selection": _nodes_of(ctx.values.get(ans_step)) if ans_step else None,
                "keys": {s: k[:12] for s, k in ctx.keys.items()}}

    def _plan(self, question: str, llm: LLM, lg_hint: LoadedGraph) -> tuple[TurnPlan, list[str]]:
        system = PLANNER_SYSTEM.format(catalogue=catalogue_text()) + SESSION_RULES.format(turn=len(self.turns) + 1)
        d = f"Dataset description (from the user): {self.description}\n" if self.description else ""
        user = (f"PROFILE CARD:\n{json.dumps(self.card, default=str, ensure_ascii=False)}\n\nSESSION STATE:\n"
                f"{json.dumps(self.state(), default=str, ensure_ascii=False)}\n\nGraph file: {os.path.basename(self.path)}\n{d}Question: {question}")
        plan = TurnPlan.model_validate(parse_json(llm.chat(system, user).text))
        lg, _ = self._graph_for(plan)
        problems = validate(plan, lg, self.budget_ops)
        if problems:
            fix = llm.chat(system, user + "\n\nYour previous plan had these problems, return a corrected full plan:\n" + "\n".join(problems)
                           + f"\n\nPrevious plan:\n{plan.model_dump_json()}")
            plan = TurnPlan.model_validate(parse_json(fix.text))
            lg, _ = self._graph_for(plan)
            problems = validate(plan, lg, self.budget_ops)
        return plan, problems

    def ask(self, question: str, llm: LLM, explain: bool = False) -> dict[str, Any]:
        t0 = time.time()
        c0, i0, o0, u0 = llm.usage.calls, llm.usage.input_tokens, llm.usage.output_tokens, llm.usage.cost_usd
        turn: dict[str, Any] = {"turn": len(self.turns) + 1, "question": question, "outcome": "error"}
        try:
            plan, problems = self._plan(question, llm, self.lg)
            turn.update(self.submit(plan, question, problems=problems, _turn=turn))
            if explain and turn.get("trace"):
                tr = json.dumps(turn["trace"], default=str)[:6000]
                turn["explanation"] = llm.chat(INTERPRETER_SYSTEM, f"Question: {question}\nPlan rationale: {plan.rationale}\nInterpretation: {json.dumps(plan.interpretation, default=str)}\n"
                                               f"Trace: {tr}\nFindings: {json.dumps(turn['findings'])[:3000]}\nExtracted answer: {json.dumps(turn['answer'], default=str)[:2000]}").text.strip()
        except Exception as e:  # noqa: BLE001
            turn["error"] = f"{type(e).__name__}: {e}"
        turn.update({"llm_calls": llm.usage.calls - c0, "tokens_in": llm.usage.input_tokens - i0, "tokens_out": llm.usage.output_tokens - o0,
                     "cost_usd": round(llm.usage.cost_usd - u0, 5), "seconds": round(time.time() - t0, 3)})
        if turn not in self.turns:
            self.turns.append(turn)
        return turn

    def submit(self, plan: TurnPlan | dict, question: str, problems: Optional[list[str]] = None, _turn: Optional[dict] = None) -> dict[str, Any]:
        """Decide and run a plan: from the planner, or edited by the user in the interface (plan mutation)."""
        if isinstance(plan, dict):
            plan = TurnPlan.model_validate(plan)
        turn = _turn if _turn is not None else {"turn": len(self.turns) + 1, "question": question}
        if turn not in self.turns:
            self.turns.append(turn)
        lg, sem_findings = self._graph_for(plan)
        problems = validate(plan, lg, self.budget_ops) if problems is None else problems
        turn.update({"intent": plan.intent, "based_on": plan.based_on, "patch": plan.patch, "references": plan.references,
                     "clarification": plan.clarification, "plan": plan.model_dump()})
        if problems:
            turn.update({"outcome": "error", "error": "invalid plan: " + "; ".join(problems)})
            return turn
        if plan.clarification and not plan.steps:
            self.clarifications.append({"turn": turn["turn"], "asked": plan.clarification})
            turn["outcome"] = "clarify"
            return turn
        turn["tier_notes"] = auto_tier(plan, lg, self.budget_ops)
        checks, pat = self.reuse_checks(plan, question)
        turn["reuse_findings"] = sem_findings + checks
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
        self._accept(turn, c.get("result") or self._run(TurnPlan.model_validate(c["plan"]), pend["lg"], pend["question"]), pend["lg"])
        turn["clarification"] = None
        return turn

    def _accept(self, turn: dict, result: dict, lg: LoadedGraph) -> None:
        turn.update(result)
        self._ov = self._ov_of.get(id(lg), self._ov)
        self.semantics = {"directed": lg.g.is_directed(), "weighted": "weight" in lg.g.es.attributes()}

    def public(self, turn: dict) -> dict:
        """A turn without internal handles, safe to serialise."""
        return json.loads(json.dumps({k: v for k, v in turn.items() if not k.startswith("_")}, default=str))
