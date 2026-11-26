"""Verification without ground truth: invariants between results, cross-method agreement, approximation bounds."""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .ir import Plan
from .ops import Ctx, CATALOGUE


def overlap_at_k(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    k = min(len(a), len(b))
    return len(set(a[:k]) & set(b[:k])) / k


MEASURE_WORDS = {"betweenness": "betweenness", "pagerank": "pagerank", "page rank": "pagerank", "closeness": "closeness",
                 "eigenvector": "eigenvector_centrality", "in-degree": "degree", "indegree": "degree", "out-degree": "degree", "outdegree": "degree",
                 "degree": "degree", "triangle": "triangle_count", "clustering": "average_clustering", "communit": "communities",
                 "diameter": "diameter", "k-core": "max_core", "assortativ": "assortativity", "reciprocity": "reciprocity", "pagerank score": "pagerank"}
OP_FAMILY = {"degree": {"degree", "node_degree", "strength", "degree_stats"}, "triangle_count": {"triangle_count"},
             "average_clustering": {"average_clustering", "local_clustering", "transitivity"}, "communities": {"communities"},
             "diameter": {"diameter"}, "max_core": {"max_core", "core_number", "k_core"}, "assortativity": {"assortativity"},
             "reciprocity": {"reciprocity"}, "betweenness": {"betweenness"}, "pagerank": {"pagerank"}, "closeness": {"closeness"},
             "eigenvector_centrality": {"eigenvector_centrality"}}


def consistency(plan: Plan, ctx: Ctx, question: str | None) -> list[dict[str, Any]]:
    """Checks between the question, the stated interpretation, the inferred semantics and the plan. No ground truth used."""
    import re
    out: list[dict[str, Any]] = []
    sem = ctx.lg.semantics
    g = ctx.lg.g
    interp = plan.interpretation or {}

    def add(check, ok, detail, severity="error"):
        out.append({"check": check, "ok": bool(ok), "detail": detail, "severity": severity if not ok else "info"})

    # 1. stated interpretation vs inferred semantics (only when inference is confident)
    if isinstance(interp.get("directed"), bool) and sem.confidence.get("directed", 0) >= 0.85 and interp["directed"] != sem.directed:
        add("interpretation: directedness contradicts the data", False,
            f"plan assumes directed={interp['directed']} but the file evidence says directed={sem.directed} ({sem.evidence.get('directed')})")
    uses_w = interp.get("use_weights") is True or any(st.args.get("use_weights") is True for st in plan.steps)
    if uses_w and sem.weighted and sem.weight_semantics == "strength":
        add("interpretation: weights used as path lengths but they are strengths", False, sem.evidence.get("weight_semantics", "weights look like counts"))
    # 2. directional ops on an undirected graph
    for st in plan.steps:
        if not g.is_directed() and st.args.get("mode") in ("in", "out"):
            add(f"{st.id}: in/out mode on an undirected graph", False, "in- and out-degree are undefined here; the graph was loaded undirected", "warn")
    # 3. stated measure vs operators actually used
    ops = {st.op for st in plan.steps}

    def has(op):
        return bool(OP_FAMILY.get(op, {op}) & ops)
    m = str(interp.get("measure", "")).lower()
    for word, op in MEASURE_WORDS.items():
        if word in m and not has(op):
            add("interpretation: stated measure not computed", False, f"interpretation says '{word}' but no {op} step exists")
            break
    # 4. question mentions a measure or direction the plan ignores
    if question:
        ql = question.lower()
        for word, op in MEASURE_WORDS.items():
            if word in ql and not has(op):
                add("question: named measure not computed", False, f"question says '{word}' but the plan has no {op} step")
                break
        comp_modes = {st.args.get("mode", "weak") for st in plan.steps if st.op == "components"}
        if "strongly" in ql and comp_modes and "strong" not in comp_modes:
            add("question: asks for strongly connected components but plan uses weak", False, f"modes {comp_modes}")
        if ("weakly" in ql or ("connected components" in ql and "strongly" not in ql and not g.is_directed())) and comp_modes and "weak" not in comp_modes:
            add("question: asks for (weakly) connected components but plan uses strong", False, f"modes {comp_modes}")
        if g.is_directed():
            wants_in = any(w in ql for w in ("in-degree", "indegree", "followers", "cited by", "trusted by", "received", "bought by", "cite it", "follow 7", "follow it"))
            wants_out = any(w in ql for w in ("out-degree", "outdegree", "follows", "cites", "trusts", "sent"))
            modes = {st.args.get("mode") for st in plan.steps if st.op in ("degree", "node_degree", "strength", "neighbours", "k_hop_neighbourhood")}
            if wants_in and not wants_out and modes and modes <= {"all", None, "out"}:
                add("question: asks for incoming relations but plan uses out/all mode", False, f"modes used: {modes}", "warn")
            if wants_out and not wants_in and modes and modes <= {"all", None, "in"}:
                add("question: asks for outgoing relations but plan uses in/all mode", False, f"modes used: {modes}", "warn")
        # 5. node references not present in the question text
        toks = set(re.findall(r"[A-Za-z0-9_]+", question))
        for st in plan.steps:
            spec = CATALOGUE.get(st.op)
            if not spec:
                continue
            for p_, ty in spec.params.items():
                if ty.startswith("NodeRef") and p_ in st.args and isinstance(st.args[p_], (str, int)):
                    v = str(st.args[p_])
                    if v not in toks and v.lower() not in {t.lower() for t in toks} and not any(v.lower() in t.lower() or t.lower() in v.lower() for t in toks if len(t) > 2):
                        add(f"{st.id}: node '{v}' is not mentioned in the question", False, "possible wrong node", "warn")
    # 6. multigraph semantics
    if sem.multigraph and question:
        ql = question.lower()
        if "edge_count" in ops and any(w in ql for w in ("distinct", "different", "pairs", "unique")) and "distinct_edge_count" not in ops:
            add("multigraph: question asks for distinct pairs but edge_count counts repeated interactions", False, "use distinct_edge_count", "warn")
    return out


def verify(plan: Plan, ctx: Ctx, question: str | None = None) -> list[dict[str, Any]]:
    """Return a list of findings: {"check": str, "ok": bool, "detail": str, "severity": "error|warn|info"}."""
    g = ctx.lg.g
    n, m = g.vcount(), g.ecount()
    findings: list[dict[str, Any]] = []
    vals = ctx.values
    by_op: dict[str, list[str]] = {}
    for st in plan.steps:
        by_op.setdefault(st.op, []).append(st.id)

    def add(check, ok, detail, severity="error"):
        findings.append({"check": check, "ok": bool(ok), "detail": detail, "severity": severity if not ok else "info"})

    # partitions cover the graph
    for sid in by_op.get("components", []) + by_op.get("communities", []):
        p = vals[sid]
        tot = sum(p["sizes"]) if p["count"] <= 20 else len(p["membership"])
        gsize = len(p["membership"])
        add(f"{sid}: partition covers all nodes", tot == gsize, f"sum of block sizes {tot} vs nodes {gsize}")
        if "modularity" in p:
            add(f"{sid}: modularity in [-0.5, 1]", -0.5 <= p["modularity"] <= 1.0, f"modularity={p['modularity']:.3f}")
            if p["count"] > 1 and p["modularity"] < 0.05:
                add(f"{sid}: community structure is weak", False, f"modularity {p['modularity']:.3f} < 0.05, communities may be meaningless", "warn")

    # triangle / clustering consistency
    if by_op.get("triangle_count") and by_op.get("transitivity"):
        tri = vals[by_op["triangle_count"][0]]
        tr = vals[by_op["transitivity"][0]]
        deg = g.degree()
        triples = sum(d * (d - 1) / 2 for d in deg)
        implied = 3 * tri / triples if triples else 0
        add("transitivity consistent with triangle count", abs(implied - tr) < 1e-6 + 0.02 * max(tr, 1e-9), f"3T/triples={implied:.4f} vs transitivity={tr:.4f}")

    # diameter bounds
    for sid in by_op.get("diameter", []):
        d = vals[sid]
        st = next(s for s in plan.steps if s.id == sid)
        if st.args.get("tier") == "approx":
            add(f"{sid}: approximate diameter is a lower bound", True, f"double-sweep gives a lower bound; true diameter >= {d}", "info")
        add(f"{sid}: diameter < n", d < n, f"diameter={d}, n={n}")

    # centrality bounds and cross-method agreement on top-k
    rankings: dict[str, list[str]] = {}
    for sid in by_op.get("top_k", []):
        st = next(s for s in plan.steps if s.id == sid)
        src = st.args.get("map")
        src_op = next((s.op for s in plan.steps if s.id == src), None)
        src_graph = next((s.args.get("graph", "G") for s in plan.steps if s.id == src), "G")
        if src_op and src_graph == "G":
            rankings[src_op] = [r["node"] for r in vals[sid]]
    for sid in by_op.get("betweenness", []):
        bmax = max(vals[sid].values())
        bound = (n - 1) * (n - 2) / (1 if g.is_directed() else 2)
        add(f"{sid}: betweenness within theoretical bound", bmax <= bound * 1.000001, f"max={bmax:.1f}, bound={bound:.1f}")
    for sid in by_op.get("pagerank", []):
        s = sum(vals[sid].values())
        add(f"{sid}: pagerank sums to 1", abs(s - 1) < 1e-6, f"sum={s:.6f}")
    cents = [op for op in ("betweenness", "pagerank", "degree", "closeness", "eigenvector_centrality") if op in rankings]
    for i in range(len(cents)):
        for j in range(i + 1, len(cents)):
            ov = overlap_at_k(rankings[cents[i]], rankings[cents[j]])
            add(f"top-k agreement {cents[i]} vs {cents[j]}", ov >= 0.3, f"overlap@k={ov:.2f}; " + ("measures agree on the leaders" if ov >= 0.3 else "measures disagree: report both, the choice of measure changes the answer"), "warn")

    # approximate betweenness: sample-size note
    for sid in by_op.get("betweenness", []) + by_op.get("closeness", []):
        st = next(s for s in plan.steps if s.id == sid)
        if st.args.get("tier") == "approx":
            k = st.args.get("k", 500)
            add(f"{sid}: approximate with {k} pivots", True, f"relative error on top ranks typically < 10% with {k} pivots on graphs of this size; exact values would need O(nm)={n * m:.1e} operations", "info")

    # paths
    for sid in by_op.get("shortest_path", []):
        p = vals[sid]
        if p.get("reachable"):
            path = p["path"]
            ok = all(g.are_adjacent(ctx.node(path[i]), ctx.node(path[i + 1])) for i in range(len(path) - 1))
            add(f"{sid}: returned path is a valid walk", ok, f"{len(path) - 1} hops")
        else:
            add(f"{sid}: target unreachable", True, "no path exists in the stated direction" + ("; the reverse direction may differ in a directed graph" if g.is_directed() else ""), "warn")
    for sid in by_op.get("distance", []):
        d = vals[sid]
        if d == math.inf and g.is_directed():
            add(f"{sid}: unreachable in a directed graph", True, "distance is infinite following edge direction; reverse or undirected distance may be finite", "warn")

    # set sizes
    for sid in by_op.get("reachable_set", []) + by_op.get("k_hop_neighbourhood", []):
        add(f"{sid}: set size < n", len(vals[sid]) < n, f"{len(vals[sid])} nodes")
    # diameter on a disconnected graph without restriction
    for sid in by_op.get("diameter", []):
        st = next(s for s in plan.steps if s.id == sid)
        if st.args.get("largest_component_only") is False and not g.is_connected(mode="weak"):
            add(f"{sid}: diameter over a disconnected graph", False, "the graph is disconnected; the diameter is infinite unless restricted to the largest component", "warn")
    findings.extend(consistency(plan, ctx, question))
    return findings


# ---------------------------------------------------------------------------------------------- guards on the answer
# Each guard comes from an error found by hand in answers that had passed every other check (plan document 3.18 to
# 3.20). A guard does not change the answer: it adds a failed finding, which the interface shows, the explanation is
# written from, and the runners record in the turn's flags.
IGNORE_DIRECTION = r"ignor\w* (the )?direction|regardless of (the )?direction|in either direction|\bundirected\b|direction (is|being) ignored"
# operators whose value changes when a pair linked both ways is counted as two links
TWO_WAY_SENSITIVE = {"degree", "node_degree", "strength", "degree_stats", "neighbour_aggregate", "triangle_count", "local_clustering",
                     "average_clustering", "transitivity", "density", "edge_count", "edges_between", "edges_touching", "core_number", "max_core", "k_core",
                     "assortativity", "mixing_matrix", "communities"}
COLLAPSING = {"undirected_graph", "mutual_graph"}
# a key or a question names a share only as a whole word asked for: "shared_count", "the top 1%" and "given the share of ..." do not
SHARE_KEY = r"(?<![a-z])(share|fraction|proportion)(?![a-z])"
PERCENT_KEY = r"(?<![a-z])(percent|percentage|pct)(?![a-z])"
ASKS_SHARE = r"\b(what|which|how (large|big|small)) (is |are |was |were )?(the |a |an )?(overall |total )?(share|fraction|proportion)\b"
ASKS_PERCENT = r"\b(what|which) (is |are |was |were )?(the )?(percent|percentage|%)|\bhow many percent\b"
BINNING = {"map_bins", "map_quantile"}


def _bin_source(plan_steps: list[dict], step: dict):
    """What a binning step bins by: the operator and arguments of the step that produced its map."""
    src = next((s for s in plan_steps if s["id"] == step.get("args", {}).get("map")), None)
    if src is None:
        return None
    args = {k: v for k, v in (src.get("args") or {}).items() if k in ("attribute", "mode", "values", "agg") and isinstance(v, (str, int, float))}
    return src["op"], tuple(sorted(args.items()))


def guards(plan: Plan, ctx: Ctx, question: str | None, answer: Any, earlier_plan: dict | None = None, earlier_turn: int | None = None,
           directed: bool | None = None) -> list[dict[str, Any]]:
    """ctx may be None when directed is given (stored turns, bench/sessions/table_written.py): the comparison guard is then skipped."""
    import re
    out: list[dict[str, Any]] = []
    ql = (question or "").lower()
    steps = [st.model_dump() if hasattr(st, "model_dump") else dict(st) for st in plan.steps]

    def fail(check, detail, severity="warn"):
        out.append({"check": check, "ok": False, "detail": detail, "severity": severity})

    # 1. the question says to ignore direction, the graph is directed, and nothing in the plan collapses two-way pairs
    if ql and (ctx.lg.g.is_directed() if directed is None else directed) and re.search(IGNORE_DIRECTION, ql) and not any(s["op"] in COLLAPSING for s in steps):
        hit = [s["id"] for s in steps if s["op"] in TWO_WAY_SENSITIVE and (s.get("args") or {}).get("mode", "all") not in ("in", "out")]
        if hit:
            fail("guard_direction_ignored", f"the question says to ignore direction, but step(s) {', '.join(hit)} run on the directed graph, where a pair linked "
                 "both ways counts as two links; no undirected_graph step collapses them, so counts may be too high")

    # 2. a value the question calls a share lies outside [0, 1] (a percentage: outside [0, 100])
    def numbers(v, key=""):
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            yield key, v
        elif isinstance(v, dict):
            for k, x in v.items():
                yield from numbers(x, str(k))
        elif isinstance(v, list):
            for x in v:
                yield from numbers(x, key)
    asks_share, asks_pct = bool(re.search(ASKS_SHARE, ql)), bool(re.search(ASKS_PERCENT, ql))
    for key, x in numbers(answer):
        scalar = not isinstance(answer, (dict, list))
        is_pct = bool(re.search(PERCENT_KEY, key.lower())) or (scalar and asks_pct and not asks_share)
        is_share = bool(re.search(SHARE_KEY, key.lower())) or (scalar and asks_share)
        hi = 100 if is_pct else 1 if is_share else None
        if hi is not None and not (-1e-9 <= x <= hi + 1e-9):
            fail("guard_share_out_of_range", f"{'the answer' if scalar else repr(key)} = {x:g} is called a {'percentage' if is_pct else 'share'} but lies outside [0, {hi}]: "
                 "the numerator and the denominator are probably not counted over the same set", "error")
            break

    # 3. this turn bins by another variable than the turn it builds on, and the question does not name the new one
    if earlier_plan and earlier_plan.get("steps"):
        mine = [_bin_source(steps, s) for s in steps if s["op"] in BINNING]
        theirs = [_bin_source(earlier_plan["steps"], s) for s in earlier_plan["steps"] if s["op"] in BINNING]
        mine, theirs = [m for m in mine if m], [t for t in theirs if t]
        if mine and theirs and not set(mine) & set(theirs):
            new = mine[0]
            words = {w for w in re.split(r"[^a-z0-9]+", " ".join([new[0]] + [str(v) for _, v in new[1]]).lower()) if len(w) > 2 and w not in ("map", "node", "all", "attribute", "mean")}
            if not any(w in ql for w in words):
                show = lambda x: x[0] + ("(" + ", ".join(f"{k}={v}" for k, v in x[1]) + ")" if x[1] else "")   # noqa: E731
                fail("guard_grouping_variable", f"this turn groups by {show(new)}, but turn {earlier_turn}, which it builds on, grouped by {show(theirs[0])}, "
                     "and the question does not name a new variable: the groups are probably not the ones the user means")

    # 4. the answer is the truth value of a labelled comparison, which need not be "yes" to the question
    a = plan.answer if ctx is not None else None
    if a is not None and a.step and a.field == "a_greater" and isinstance(answer, bool):
        st = next((s for s in steps if s["id"] == a.step), None)
        v = ctx.values.get(a.step) if st and st["op"] == "compare" else None
        if isinstance(v, dict) and (st["args"].get("label_a") or st["args"].get("label_b")):
            fail("guard_boolean_from_comparison", f"the answer {str(answer).lower()} is the result of the comparison {v['a']:g} > {v['b']:g} and means "
                 f"\"{v['greater']}\"; read it as that statement, not as yes or no to the question")
    out += referent(steps, question, earlier_plan, earlier_turn, {k: len(v) for k, v in ctx.values.items() if isinstance(v, (list, set, tuple, frozenset))} if ctx is not None else None)
    return out


# ---------------------------------------------------------------------------------------------- what "them" was taken to be
# Three of the eight errors found by hand in the stable disagreements (plan document 3.21) have one cause: the question
# refers back to a group ("them", "that group"), the turn it builds on selected a group and then derived a second set
# from it for its answer, and the plan continues from the wrong one of the two. Which one the user means cannot be
# decided from the plan, so the check does not call it an error: when both sets exist and the plan continues from one
# only, it says which, and names the other.
BACK_REFERENCE = r"\b(them|they|their|those|these|that group|this group|that set|the group|the same (users|people|accounts|nodes))\b"
THROUGH_LINKS = {"reachable_set", "k_hop_neighbourhood", "edges_touching"}       # besides every operator named after neighbours
SET_LIKE = {"top_k"}                                          # a ranking is used as the set of its nodes


def _signatures(steps: list[dict]) -> dict[str, str]:
    """Step id -> a text that is the same for the same operator on the same inputs, whatever the ids are called."""
    by_id, sig = {s["id"]: s for s in steps}, {}

    def of(sid):
        if sid not in sig:
            sig[sid] = "?"                                   # a step that refers to itself stays unresolved
            st = by_id[sid]

            def canon(v):
                if isinstance(v, str):
                    head, dot, rest = v.partition(".")
                    return "<" + of(head) + ">" + dot + rest if head in by_id else v
                if isinstance(v, list):
                    return [canon(x) for x in v]
                if isinstance(v, dict):
                    return {k: canon(x) for k, x in sorted(v.items())}
                return v
            args = {k: canon(v) for k, v in sorted((st.get("args") or {}).items()) if v is not None and not (k == "graph" and v == "G")}
            sig[sid] = hashlib.md5((st["op"] + json.dumps(args, sort_keys=True, default=str)).encode()).hexdigest()[:16]   # short: a signature holds those of its inputs
        return sig[sid]
    for s in steps:
        of(s["id"])
    return sig


def _inputs(step: dict, ids) -> list[str]:
    out = []

    def walk(v):
        if isinstance(v, str) and v.partition(".")[0] in ids:
            out.append(v.partition(".")[0])
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
    walk(step.get("args") or {})
    return out


def referent(steps: list[dict], question: str | None, earlier_plan: dict | None, earlier_turn: int | None, sizes: dict | None = None) -> list[dict[str, Any]]:
    """steps: this turn's plan; earlier_plan: the plan of the turn it builds on. sizes: step id -> size, of this turn, when known."""
    import re
    from .ops import CATALOGUE
    if not question or not earlier_plan or not earlier_plan.get("steps") or not re.search(BACK_REFERENCE, question.lower()):
        return []
    is_set = lambda s: s["op"] in SET_LIKE or (s["op"] in CATALOGUE and CATALOGUE[s["op"]].returns == "NodeSet")   # noqa: E731
    old = earlier_plan["steps"]
    old_ids = {s["id"]: s for s in old}
    old_sig = _signatures(old)

    def ancestors(sid, seen=None):                           # node-set steps a step is computed from, nearest first
        seen, found = seen if seen is not None else set(), []
        for i in _inputs(old_ids[sid], old_ids):
            if i in seen:
                continue
            seen.add(i)
            found += ([i] if is_set(old_ids[i]) else []) + ancestors(i, seen)
        return found
    ans = earlier_plan.get("answer") or {}
    targets = [ans.get("step")] + list((ans.get("steps") or {}).values()) if isinstance(ans.get("steps"), dict) else [ans.get("step")]
    targets = [str(t).partition(".")[0] for t in targets if t]
    result = next((t if is_set(old_ids[t]) else (ancestors(t) or [None])[0] for t in targets if t in old_ids), None)
    if result is None:
        return []
    group = (ancestors(result) or [None])[0]                 # the set the earlier turn derived its answer set from
    if group is None or old_sig[group] == old_sig[result]:
        return []
    # a refinement ("of those, how many ...") leaves one group, narrowed; the two sets are different populations only when
    # the answer set was reached from the group through links (its neighbours, what it reaches)
    def reaches(sid, target, seen=None):
        seen = seen if seen is not None else set()
        return sid == target or any(i not in seen and not seen.add(i) and reaches(i, target, seen) for i in _inputs(old_ids[sid], old_ids))
    between = [s for s in old if s["id"] != group and reaches(result, s["id"]) and reaches(s["id"], group)]
    if not any("neighbour" in s["op"] or s["op"] in THROUGH_LINKS for s in between):
        return []
    mine = _signatures(steps)
    by_sig = {v: k for k, v in mine.items()}
    r, g = by_sig.get(old_sig[result]), by_sig.get(old_sig[group])
    known = set(old_sig.values())
    new = [s for s in steps if mine[s["id"]] not in known]   # what this turn adds to the earlier plan
    ids = {s["id"] for s in steps}
    used = {i for s in new for i in _inputs(s, ids)}
    uses_r, uses_g = r in used, g in used
    if not uses_r or uses_g:                                 # only the case found in practice: continuing from the answer set alone
        return []
    word = re.search(BACK_REFERENCE, question.lower()).group(0)
    taken, other = (r, g) if uses_r else (g, r)
    n = lambda sid: f" ({sizes[sid]:,} nodes)" if sizes and isinstance(sizes.get(sid), int) else ""   # noqa: E731
    what = (f"the set turn {earlier_turn} gave as its answer" if uses_r else f"the group turn {earlier_turn} started from")
    alt = (f"the group turn {earlier_turn} started from" if uses_r else f"the set turn {earlier_turn} gave as its answer")
    alt_step = old_ids[group if uses_r else result]
    return [{"check": "guard_referent", "ok": False, "severity": "warn",
             "detail": f"\"{word}\" is taken to be {what}: step {taken}{n(taken)}. Turn {earlier_turn} also has {alt} "
                       f"({alt_step['op']}{', step ' + other + n(other) if other else ''}); if that is the group meant, the answer is for another set"}]
