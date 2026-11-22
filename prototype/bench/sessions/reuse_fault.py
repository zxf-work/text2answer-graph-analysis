"""E1: fault injection for reuse decisions. No model calls.

Each scenario is a short history of plans followed by a target plan, built so that a careless result store could
hand the target a value computed under other conditions (another reading of the graph, another scope, another
seed, an older file, a changed input upstream). Every scenario is run under several cache-key schemes: the full
lineage key, the lineage key with one ingredient removed, and the prototype's original cache. For each we record

  admitted   a stored value was used for a target step although a fresh computation gives a different value
  harmful    the target's final answer differs from the fresh answer
  crashed    the wrong value made a later step fail (visible, so not silent)

"Valid" scenarios are the other side: reuse is correct there, and we count how many of the reusable steps each
scheme actually reuses. A second part checks the scope-reading rule: how often the two readings of a group
restriction give different answers, whether the rule flags them, and whether it flags plans it should not.

Usage: python bench/sessions/reuse_fault.py <out dir> <attributed graph>... [--small]
       attributed graphs are edge files with a node table next to them (see prep_pokec_parts.py)
"""
from __future__ import annotations

import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
from collections import defaultdict

import igraph as ig

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from t2r.graphs import load_graph, profile_card  # noqa: E402
from t2r.ir import Plan, Step, _canon, _h, execute, full_args, graph_key, resolve_ref, step_inputs, validate  # noqa: E402
from t2r.ops import CATALOGUE, Ctx  # noqa: E402
from t2r.session import TurnPlan, scope_patterns  # noqa: E402

# ------------------------------------------------------------------------------------------------- key schemes
SCHEMES = {
    "full lineage key": {},
    "without input lineage": {"lineage": False},          # arguments as written: a step name stands for whatever it held
    "without graph reading": {"root": "content"},          # root = file contents, not how they were read
    "without content hash": {"root": "name"},              # root = dataset name and reading
    "without node table": {"root": "no_table"},
    "without seed": {"seed": False},
    "original cache": {"root": "file", "lineage": False, "seed": False, "root_only": True},   # (file hash, operator, arguments), graph-level steps only
}


def root_key(lg, kind: str) -> str:
    g = lg.g
    nt = g["node_table"]["sha1"] if "node_table" in g.attributes() else None
    reading = [g.is_directed(), "weight" in g.es.attributes(), lg.semantics.multigraph, lg.semantics.weight_semantics, bool(lg.strict)]
    if kind == "full":
        return graph_key(lg)
    if kind == "content":
        return _h(["graph", lg.facts.sha1, nt])
    if kind == "name":
        return _h(["graph", lg.name, *reading])
    if kind == "no_table":
        return _h(["graph", lg.facts.sha1, *reading])
    if kind == "file":
        return _h(["graph", lg.facts.sha1])
    raise ValueError(kind)


def run(plan: Plan, lg, seed: int, store: dict | None, sch: dict):
    """Execute a plan against a store under one key scheme. Returns (values, ids of steps served from the store)."""
    ctx = Ctx(lg, seed=seed)
    keys = {"G": root_key(lg, sch.get("root", "full"))}
    ids = {s.id for s in plan.steps}
    hits = []
    for st in plan.steps:
        args = full_args(st)
        sd = seed if sch.get("seed", True) else 0
        if sch.get("lineage", True):
            key = _h([st.op, {k: _canon(v, keys) for k, v in sorted(args.items())}, sd])
        else:
            key = _h([keys["G"], st.op, {k: v for k, v in sorted(args.items())}, sd])
        keys[st.id] = key
        cacheable = store is not None and not (sch.get("root_only") and step_inputs(st, ids))
        if cacheable and key in store:
            val = store[key]; hits.append(st.id)
        else:
            a = {k: ([resolve_ref(ctx, x) for x in v] if isinstance(v, list) else resolve_ref(ctx, v)) for k, v in st.args.items()}
            val = CATALOGUE[st.op].fn(ctx, **a)
            if cacheable:
                store[key] = val
        ctx.values[st.id] = val
    return ctx.values, hits


def same(a, b) -> bool:
    if isinstance(a, ig.Graph) or isinstance(b, ig.Graph):
        return (isinstance(a, ig.Graph) and isinstance(b, ig.Graph) and a.vcount() == b.vcount() and a.ecount() == b.ecount()
                and a.is_directed() == b.is_directed() and (("name" not in a.vs.attributes()) or a.vs["name"] == b.vs["name"]))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return (math.isnan(a) and math.isnan(b)) or math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-12)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        if a and all(isinstance(x, dict) and "node" in x and "value" in x for x in a + b):     # a ranking: equal up to the order of ties
            return all(same(x["value"], y["value"]) for x, y in zip(a, b)) and sorted(str(x["node"]) for x in a) == sorted(str(y["node"]) for y in b)
        return all(same(x, y) for x, y in zip(a, b))
    return a == b


# --------------------------------------------------------------------------------------------------- scenarios
def P(steps, ids=None) -> Plan:
    """steps: [(op, args)], '@k' in args refers to step k (1-based). ids default to s1, s2, ... as a planner writes them."""
    ids = ids or [f"s{i + 1}" for i in range(len(steps))]

    def sub(v):
        if isinstance(v, str) and v.startswith("@"):
            return ids[int(v[1:]) - 1]
        return v
    return Plan.model_validate({"steps": [{"id": ids[i], "op": op, "args": {k: sub(v) for k, v in a.items()}} for i, (op, a) in enumerate(steps)],
                                "answer": {"step": ids[-1], "kind": "table"}})


def scenarios(spec):
    """Yield scenario dicts for one graph. A run is (plan, variant, seed); variants are named loads of the graph."""
    d = spec["directed"]
    M = [("pagerank", {}), ("degree", {"mode": "in" if d else "all"}), ("core_number", {}), ("closeness", {"tier": "approx", "k": 30})]
    RANDOM = [("betweenness", {"tier": "approx", "k": 30}), ("closeness", {"tier": "approx", "k": 30})]
    tail = [("induced_subgraph", {"nodes": "@2"}), ("edge_count", {"graph": "@3"})]
    S = lambda cls, valid, hist, target, reusable=None, note="": {"class": cls, "valid": valid, "history": hist, "target": target, "reusable": reusable, "note": note}  # noqa: E731
    base, a = "base", spec.get("attr")
    vals = spec.get("values", [])
    group = lambda m, v: P([("filter_by_attribute", {"attribute": a, "value": v}), ("induced_subgraph", {"nodes": "@1"}), (m[0], {**m[1], "graph": "@2"}), ("top_k", {"map": "@3", "k": 10})])  # noqa: E731

    for m in M:
        top = P([m, ("top_k", {"map": "@1", "k": 10})])
        # ---- faults
        yield S("other reading of the graph", False, [(top, base, 1)], (top, "flipped", 1), note=m[0])
        yield S("different subgraph under the same step name", False,
                [(P([("largest_component", {}), (m[0], {**m[1], "graph": "@1"}), ("top_k", {"map": "@2", "k": 10})]), base, 1)],
                (P([("k_core", {"k": 2}), (m[0], {**m[1], "graph": "@1"}), ("top_k", {"map": "@2", "k": 10})]), base, 1), note=m[0])
        yield S("input changed upstream (short list extended)", False, [(P([m, ("top_k", {"map": "@1", "k": 10}), *tail]), base, 1)],
                (P([m, ("top_k", {"map": "@1", "k": 20}), *tail]), base, 1), note=m[0])
        yield S("graph file changed", False, [(top, base, 1)], (top, "stale_file", 1), note=m[0])
        if a:
            for v1, v2 in ((vals[0], vals[1]), (vals[1], vals[2]), (vals[2], vals[0])):
                yield S("different group under the same step name", False, [(group(m, v1), base, 1)], (group(m, v2), base, 1), note=f"{m[0]} {v1} -> {v2}")
            yield S("node attributes changed", False, [(group(m, vals[0]), base, 1)], (group(m, vals[0]), "stale_table", 1), note=m[0])
        # ---- valid reuse
        yield S("repeat", True, [(top, base, 1)], (top, base, 1), 2, m[0])
        yield S("parameter changed downstream", True, [(top, base, 1)], (P([m, ("top_k", {"map": "@1", "k": 20})]), base, 1), 1, m[0])
        yield S("extended with new steps", True, [(top, base, 1)], (P([m, ("top_k", {"map": "@1", "k": 10}), *tail]), base, 1), 2, m[0])
        yield S("same steps, other names", True, [(top, base, 1)], (P([m, ("top_k", {"map": "@1", "k": 10})], ids=["scores", "best"]), base, 1), 2, m[0])
        other = M[(M.index(m) + 1) % len(M)]
        yield S("same steps, other order", True, [(P([m, other, ("top_k", {"map": "@1", "k": 10})]), base, 1)],
                (P([other, m, ("top_k", {"map": "@1", "k": 10})]), base, 1), 2, f"{m[0]} / {other[0]}")
        if a:
            yield S("same group rebuilt in a longer plan", True, [(group(m, vals[0]), base, 1)],
                    (P([m, ("top_k", {"map": "@1", "k": 10}), ("filter_by_attribute", {"attribute": a, "value": vals[0]}), ("induced_subgraph", {"nodes": "@3"}),
                        (m[0], {**m[1], "graph": "@4"}), ("top_k", {"map": "@5", "k": 10})]), base, 1), 4, m[0])
    yield S("defaults written out", True, [(P([("pagerank", {}), ("top_k", {"map": "@1", "k": 10})]), base, 1)],
            (P([("pagerank", {"graph": "G", "damping": 0.85}), ("top_k", {"map": "@1", "k": 10, "ascending": False})]), base, 1), 2, "pagerank")
    if d:
        yield S("input changed upstream (short list extended)", False, [(P([("degree", {"mode": "in"}), ("top_k", {"map": "@1", "k": 10}), *tail]), base, 1)],
                (P([("degree", {"mode": "out"}), ("top_k", {"map": "@1", "k": 10}), *tail]), base, 1), note="degree in -> out")
    if spec.get("weighted"):
        st = P([("strength", {"mode": "all"}), ("top_k", {"map": "@1", "k": 10})])
        yield S("other reading of the graph", False, [(st, base, 1)], (st, "unweighted", 1), note="strength, weights dropped")
    for r in RANDOM:
        rp = P([r, ("top_k", {"map": "@1", "k": 10})])
        yield S("different random seed", False, [(rp, base, 1)], (rp, base, 2), note=r[0])
        yield S("approximation changed upstream", False, [(P([r, ("top_k", {"map": "@1", "k": 10}), *tail]), base, 1)],
                (P([(r[0], {**r[1], "k": 120}), ("top_k", {"map": "@1", "k": 10}), *tail]), base, 1), note=r[0])
    cp = P([("communities", {"method": "leiden"}), ("largest_block", {"partition": "@1"}), ("set_size", {"nodes": "@2"})])
    yield S("different random seed", False, [(cp, base, 1)], (cp, base, 2), note="communities")


# ------------------------------------------------------------------------------------------------------ graphs
class Graphs:
    """Named loads of one graph: base, flipped direction, unweighted, a file with edges removed, a changed node table."""
    def __init__(self, spec, tmp):
        self.spec, self.tmp, self.lgs = spec, tmp, {}

    def get(self, variant):
        if variant in self.lgs:
            return self.lgs[variant]
        s = self.spec; path = s["path"]; ov = {"directed": s["directed"], "weighted": bool(s.get("weighted"))}
        fn = os.path.basename(path); table = next((os.path.splitext(path)[0] + x for x in (".nodes.csv", ".nodes.tsv", ".nodes.txt") if os.path.exists(os.path.splitext(path)[0] + x)), None)
        rng = random.Random(7)
        if variant == "flipped":
            ov["directed"] = not ov["directed"]
        elif variant == "unweighted":
            ov["weighted"] = False
        elif variant in ("stale_file", "stale_table"):
            d = os.path.join(self.tmp, s["name"] + "_" + variant); os.makedirs(d, exist_ok=True)
            lines = open(path, errors="replace").read().splitlines()
            if variant == "stale_file":                       # an older version of the file: 2% of the rows missing
                head, body = (lines[:1], lines[1:]) if s.get("header") else ([], lines)
                lines = head + [x for x in body if rng.random() >= 0.02]
            open(os.path.join(d, fn), "w").write("\n".join(lines) + "\n")
            if table:
                rows = open(table, errors="replace").read().splitlines()
                if variant == "stale_table":                  # the attribute column reassigned for 10% of the nodes
                    sep = "\t" if "\t" in rows[0] else ","
                    cols = rows[0].split(sep); j = cols.index(s["attr"])
                    body = [r.split(sep) for r in rows[1:]]
                    pick = [i for i in range(len(body)) if rng.random() < 0.10]
                    shuffled = [body[i][j] for i in pick]; rng.shuffle(shuffled)
                    for i, v in zip(pick, shuffled):
                        body[i][j] = v
                    rows = [rows[0]] + [sep.join(r) for r in body]
                open(os.path.join(d, os.path.basename(table)), "w").write("\n".join(rows) + "\n")
            path = os.path.join(d, fn)
        lg = load_graph(s["name"], path, "", override=ov)
        self.lgs[variant] = lg
        return lg


def main():
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    out, attributed = args[0], args[1:]
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="reusefault_")
    os.environ["T2R_CACHE_DIR"] = os.path.join(tmp, "cache")
    hard = json.load(open(os.path.join(ROOT, "bench", "datasets_hard.json")))
    base = json.load(open(os.path.join(ROOT, "bench", "datasets.json")))
    specs = []
    for name, src in (("trust", hard), ("follows", hard), ("citations", hard), ("roads", hard), ("facebook", base), ("epinions", base)):
        d = src[name]; p = os.path.join(ROOT, d["path"])
        specs.append({"name": name, "path": p, "directed": d["directed"], "weighted": d.get("weighted", False), "header": p.endswith(".csv")})
    for p in attributed:
        lg = load_graph("probe", p, "", override={"directed": True})
        card = profile_card(lg)
        attr = "district" if "district" in card["node_attributes"]["attributes"] else next(k for k, v in card["node_attributes"]["attributes"].items() if v["type"] == "categorical" and v["n_distinct"] > 3)
        vals = [t["value"] for t in card["node_attributes"]["attributes"][attr]["top_values"][:5]]
        specs.append({"name": os.path.splitext(os.path.basename(p))[0], "path": p, "directed": True, "weighted": False, "header": False, "attr": attr, "values": vals})
    rows, rule_rows, t_start = [], [], time.time()
    for spec in specs:
        G = Graphs(spec, tmp)
        n_s = 0
        for sc in scenarios(spec):
            n_s += 1
            plan, variant, seed = sc["target"]
            lg_t = G.get(variant)
            assert not validate(plan, lg_t, 1e13), (spec["name"], sc["class"], validate(plan, lg_t, 1e13))
            fresh, _ = run(plan, lg_t, seed, None, {})
            if not sc["valid"] and same(fresh[plan.steps[-1].id], run(sc["history"][-1][0], G.get(sc["history"][-1][1]), sc["history"][-1][2], None, {})[0][sc["history"][-1][0].steps[-1].id]):
                differs = False            # the fault does not change this answer on this graph: reuse would be harmless here
            else:
                differs = True
            for sname, sch in SCHEMES.items():
                store: dict = {}
                r = {"graph": spec["name"], "class": sc["class"], "valid": sc["valid"], "scheme": sname, "note": sc["note"], "answers_differ": differs,
                     "steps": len(plan.steps), "reusable": sc["reusable"], "hits": 0, "wrong_hits": 0, "admitted": False, "harmful": False, "crashed": False}
                try:
                    for hp, hv, hs in sc["history"]:
                        run(hp, G.get(hv), hs, store, sch)
                    vals, hits = run(plan, lg_t, seed, store, sch)
                    wrong = [h for h in hits if not same(vals[h], fresh[h])]
                    r.update(hits=len(hits), wrong_hits=len(wrong), admitted=bool(wrong), harmful=not same(vals[plan.steps[-1].id], fresh[plan.steps[-1].id]))
                except Exception as e:  # noqa: BLE001
                    r.update(crashed=True, admitted=True, error=f"{type(e).__name__}: {e}"[:200])
                rows.append(r)
            # the scope rule must not flag plans that restrict no measure to a group
            if not scope_patterns(TurnPlan.model_validate(plan.model_dump())):
                rule_rows.append({"graph": spec["name"], "kind": "no group restriction", "flagged": False})
            elif sc["class"] not in ("different group under the same step name", "node attributes changed", "same group rebuilt in a longer plan"):
                rule_rows.append({"graph": spec["name"], "kind": "no group restriction", "flagged": True, "class": sc["class"]})
        # scope readings: whole-graph scores filtered (A) against recomputed on the group's subgraph (B)
        if spec.get("attr"):
            lg = G.get("base"); a = spec["attr"]
            for m in (("pagerank", {}), ("degree", {"mode": "in"}), ("core_number", {}), ("closeness", {"tier": "approx", "k": 30})):
                for v in spec["values"]:
                    pa = P([m, ("filter_by_attribute", {"attribute": a, "value": v}), ("restrict_map", {"map": "@1", "nodes": "@2"}), ("top_k", {"map": "@3", "k": 10})])
                    pb = P([("filter_by_attribute", {"attribute": a, "value": v}), ("induced_subgraph", {"nodes": "@1"}), (m[0], {**m[1], "graph": "@2"}), ("top_k", {"map": "@3", "k": 10})])
                    ra = [x["node"] for x in run(pa, lg, 1, None, {})[0]["s4"]]; rb = [x["node"] for x in run(pb, lg, 1, None, {})[0]["s4"]]
                    fa = [p["reading"] for p in scope_patterns(TurnPlan.model_validate(pa.model_dump()))]; fb = [p["reading"] for p in scope_patterns(TurnPlan.model_validate(pb.model_dump()))]
                    rule_rows.append({"graph": spec["name"], "kind": "group restriction", "measure": m[0], "value": v, "shared_top10": len(set(ra) & set(rb)),
                                      "same_set": set(ra) == set(rb), "same_order": ra == rb, "flagged": fa == ["A"] and fb == ["B"]})
        print(f"{spec['name']}: {n_s} scenarios, {time.time() - t_start:.0f}s elapsed", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    json.dump({"rows": rows, "rule": rule_rows}, open(os.path.join(out, "reuse_fault.json"), "w"))

    # ------------------------------------------------------------------------------------------------ report
    md = ["# Reuse fault injection (E1)", "", f"{len(specs)} graphs ({', '.join(s['name'] for s in specs)}); "
          f"{sum(1 for r in rows if r['scheme'] == 'full lineage key' and not r['valid'])} fault scenarios and "
          f"{sum(1 for r in rows if r['scheme'] == 'full lineage key' and r['valid'])} valid-reuse scenarios, each run under {len(SCHEMES)} key schemes. No model calls.", ""]
    faults = [r for r in rows if not r["valid"]]
    classes = sorted({r["class"] for r in faults})
    md += ["## Faults: scenarios where a wrong value was served (and where the final answer changed)", "",
           "| key scheme | " + " | ".join(classes) + " | all | answer changed | crashed |", "|---|" + "---|" * (len(classes) + 3)]
    summary = {}
    for sname in SCHEMES:
        mine = [r for r in faults if r["scheme"] == sname]
        cells = []
        for c in classes:
            k = [r for r in mine if r["class"] == c]
            cells.append(f"{sum(r['admitted'] for r in k)}/{len(k)}")
        summary[sname] = {"faults": len(mine), "admitted": sum(r["admitted"] for r in mine), "harmful": sum(r["harmful"] for r in mine), "crashed": sum(r["crashed"] for r in mine)}
        md.append(f"| {sname} | " + " | ".join(cells) + f" | {summary[sname]['admitted']}/{len(mine)} | {summary[sname]['harmful']} | {summary[sname]['crashed']} |")
    n_diff = sum(1 for r in faults if r["scheme"] == "full lineage key" and r["answers_differ"])
    md += ["", f"In {n_diff} of {summary['full lineage key']['faults']} fault scenarios the history's answer and the target's fresh answer differ; in the rest the fault happens not to change the final answer on that graph.", ""]
    valid = [r for r in rows if r["valid"]]
    vclasses = sorted({r["class"] for r in valid})
    md += ["## Valid reuse: steps reused out of steps that could be reused (and scenarios with a wrong answer)", "",
           "| key scheme | " + " | ".join(vclasses) + " | all | wrong answers |", "|---|" + "---|" * (len(vclasses) + 2)]
    for sname in SCHEMES:
        mine = [r for r in valid if r["scheme"] == sname]
        cells = []
        for c in vclasses:
            k = [r for r in mine if r["class"] == c]
            cells.append(f"{sum(r['hits'] - r['wrong_hits'] for r in k)}/{sum(r['reusable'] for r in k)}")
        good, poss = sum(r["hits"] - r["wrong_hits"] for r in mine), sum(r["reusable"] for r in mine)
        summary[sname].update(valid_reused=good, valid_reusable=poss, valid_harmful=sum(r["harmful"] or r["crashed"] for r in mine))
        md.append(f"| {sname} | " + " | ".join(cells) + f" | {good}/{poss} | {summary[sname]['valid_harmful']} |")
    gr = [r for r in rule_rows if r["kind"] == "group restriction"]; ng = [r for r in rule_rows if r["kind"] == "no group restriction"]
    md += ["", "## Scope-reading rule", ""]
    if gr:
        md += [f"- Group restrictions tested: {len(gr)} (measure x group x graph). The two readings give a different top-10 set in "
               f"{sum(not r['same_set'] for r in gr)} and a different order in {sum(not r['same_order'] for r in gr)}; mean overlap {sum(r['shared_top10'] for r in gr) / len(gr):.1f} of 10.",
               f"- The rule identifies the reading of both plans in {sum(r['flagged'] for r in gr)} of {len(gr)}.", "",
               "| measure | cases | different top-10 set | mean shared of 10 |", "|---|---|---|---|"]
        for m in sorted({r["measure"] for r in gr}):
            k = [r for r in gr if r["measure"] == m]
            md.append(f"| {m} | {len(k)} | {sum(not r['same_set'] for r in k)} | {sum(r['shared_top10'] for r in k) / len(k):.1f} |")
    md += ["", f"- Plans with no group restriction: {len(ng)}; flagged by the rule: {sum(r['flagged'] for r in ng)}."]
    open(os.path.join(out, "reuse_fault.md"), "w").write("\n".join(md) + "\n")
    json.dump(summary, open(os.path.join(out, "reuse_fault_summary.json"), "w"), indent=1)
    print("\n".join(md))


if __name__ == "__main__":
    main()
