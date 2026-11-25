"""E2b: sessions in which reusing an earlier result is wrong. Calls a model: run on a server.

Usage: python bench/sessions/run_stale.py <out dir> --model M --variant V [--only S] <attributed graph>...
Variants:
  full                      GraphAudit session (lineage reuse, file check, standing settings, scope rule)
  codegen_stateful          notebook agent, one Python process per session
  codegen_stateful_warned   the same, told that files may change and earlier variables may be out of date
  codegen_independent       a complete script per turn in a new process
Every session runs on its own copy of the files; events rewrite that copy between turns. Each answer is scored as
correct, stale (it is what an outdated state gives) or otherwise wrong. `--dry` runs no system: it only computes gold
and stale answers and reports trap turns where the two coincide (those are void and excluded from the trap counts).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ["T2R_GRAPH_CACHE"] = "1"
# every session works on throwaway copies of the files: keep their binary graph caches on node-local scratch, and empty it per session
import tempfile  # noqa: E402
SCRATCH_CACHE = tempfile.mkdtemp(prefix="t2a-stale-cache-", dir=os.environ.get("TMPDIR") or "/tmp")
os.environ["T2R_CACHE_DIR"] = SCRATCH_CACHE
from reuse_fault import P, run as run_plan  # noqa: E402
from run_sessions import specs  # noqa: E402
from workload import alternative_golds, gold_value, matches  # noqa: E402
from workload_stale import sessions  # noqa: E402
import t2r.graphs as graphs  # noqa: E402
from t2r.graphs import load_graph, sidecar_node_table  # noqa: E402
from t2r.ir import validate  # noqa: E402
from t2r.llm import LLM  # noqa: E402

VARIANTS = ("full", "full_noreuse", "codegen_stateful", "codegen_stateful_warned", "codegen_independent", "codeact", "codeact_warned")


# ------------------------------------------------------------------------------------------------ files and events
def _touch(p):
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, max(time.time_ns(), st.st_mtime_ns + 2_000_000_000)))


def _delim(path):
    with open(path) as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                return "\t" if "\t" in line else ("," if "," in line else " ")
    return "\t"


def apply_event(ev, live, lg):
    """Rewrite the live files. `lg` is the graph as it is before the event (directed reading)."""
    g = lg.g
    indeg = g.degree(mode="in")
    order = sorted(range(g.vcount()), key=lambda i: (-indeg[i], lg.labels[i]))
    if ev["type"] == "append_edges":          # users at the given in-degree ranks each gain n new incoming links
        d = _delim(live)
        lines = []
        for rank in ev["targets"]:
            t = order[rank - 1]
            have = set(g.neighbors(t, mode="in")) | {t}
            n = indeg[order[0]] if ev["n"] == "max" else ev["n"]
            src = [i for i in sorted(range(g.vcount()), key=lambda i: lg.labels[i]) if i not in have][:n]
            lines += [f"{lg.labels[s]}{d}{lg.labels[t]}\n" for s in src]
        with open(live, "rb+") as f:
            f.seek(-1, os.SEEK_END)
            nl = f.read(1) == b"\n"
        with open(live, "a") as f:
            f.write(("" if nl else "\n") + "".join(lines))
        _touch(live)
        return {"type": ev["type"], "edges_added": len(lines), "targets": [lg.labels[order[r - 1]] for r in ev["targets"]]}
    if ev["type"] == "edit_table":            # the n best-connected users of one group are moved to another group
        table = sidecar_node_table(live)
        d = "\t" if table.endswith((".tsv", ".txt")) else ","
        rows = list(csv.reader(open(table), delimiter=d))
        head, col = rows[0], rows[0].index(ev["attribute"])
        at = {r[0]: r for r in rows[1:]}
        moved = []
        for i in order:
            r = at.get(lg.labels[i])
            if r is not None and r[col] == ev["from"]:
                r[col] = ev["to"]; moved.append(lg.labels[i])
                if len(moved) == ev["n"]:
                    break
        with open(table, "w", newline="") as f:
            csv.writer(f, delimiter=d, lineterminator="\n").writerows([head] + rows[1:])
        _touch(table)
        return {"type": ev["type"], "moved": len(moved), "from": ev["from"], "to": ev["to"]}
    raise ValueError(ev["type"])


class Files:
    """The live copy a system works on, and a snapshot of every version for computing gold and stale answers."""

    def __init__(self, spec, work):
        self.spec, self.work, self.version = spec, work, 0
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(os.path.join(work, "live"))
        self.live = self._copy(spec["path"], os.path.join(work, "live"))
        self._snap()

    @staticmethod
    def _copy(edge, to):
        os.makedirs(to, exist_ok=True)
        for p in (edge, sidecar_node_table(edge)):
            if p:
                shutil.copy(p, os.path.join(to, os.path.basename(p)))
        return os.path.join(to, os.path.basename(edge))

    def _snap(self):
        self._copy(self.live, os.path.join(self.work, f"v{self.version}"))

    def path(self, version=None):
        v = self.version if version is None else (self.version + version if version < 0 else version)
        return os.path.join(self.work, f"v{v}", os.path.basename(self.live))

    def graph(self, version=None, reading=None):
        ov = {"directed": self.spec["directed"], "weighted": self.spec["weighted"], **(reading or {})}
        return load_graph(self.spec["name"], self.path(version), self.spec["description"], override=ov)

    def event(self, ev):
        info = apply_event(ev, self.live, self.graph())
        self.version += 1
        self._snap()
        return info


# ------------------------------------------------------------------------------------------------ gold and stale
GOLD_STORE: dict = {}


def evaluate(t, steps, files, version, reading):
    """All correct answers of a plan on one state of the session: the gold plan's, plus accepted conventions."""
    lg, path = files.graph(version, reading), files.path(version)
    plan = P(steps)
    bad = validate(plan, lg, 1e13)
    assert not bad, (t["q"], bad)
    vals, _ = run_plan(plan, lg, 1, GOLD_STORE, {})
    tt = {**t, "gold": {"-": plan}}
    gold = gold_value(t["expect"], vals[plan.steps[-1].id], t)
    extra = []
    table = sidecar_node_table(path)
    if table and t["expect"] == "scalar" and plan.steps[-1].op in ("node_count", "components"):
        # the node table also lists users with no links: counting them as nodes (each its own component) is accepted
        with open(table) as f:
            ids = [line.split("\t" if table.endswith((".tsv", ".txt")) else ",")[0] for line in f][1:]
        extra = [gold + sum(i not in lg.index for i in ids)]
    if lg.facts.n_self_loops:
        # the loader drops self-loops; an answer that keeps the ones in the file is also accepted
        lg2 = _with_loops(lg, path)
        v2, _ = run_plan(plan, lg2, 1, None, {})
        extra.append(gold_value(t["expect"], v2[plan.steps[-1].id], t))
    return [gold] + extra + alternative_golds(tt, lg, path)


_LOOPS: dict = {}


def _with_loops(lg, path):
    import dataclasses
    import pandas as pd
    key = (path, os.stat(path).st_mtime_ns)
    if key not in _LOOPS:
        f = lg.facts
        si, ti = f.columns_used[0], f.columns_used[1]
        d = _delim(path)
        df = pd.read_csv(path, sep=r"\s+" if d == " " else d, comment="#", header=None, skiprows=1 if f.header else 0,
                         usecols=[si, ti], dtype=str if not f.ids_numeric else "int64", engine="c")
        loops = df[df[si] == df[ti]][si].astype(str).unique().tolist()
        _LOOPS.clear(); _LOOPS[key] = loops
    g = lg.g.copy()
    ids = [lg.index[x] for x in _LOOPS[key] if x in lg.index]
    g.add_edges([(i, i) for i in ids])
    return dataclasses.replace(lg, g=g)


def as_answer(expect, gold):
    """A gold value in the shape an answer has, to test whether a stale answer would also count as correct."""
    if expect in ("ranking", "node"):
        return [{"node": n, "value": v} for n, v in zip(gold["nodes"], gold["values"])]
    if expect == "map":
        return [{"node": n, "value": v} for n, v in gold.items()]
    return gold


def golds_for(t, files, reading):
    good = evaluate(t, t["steps"], files, None, reading)
    stale = []
    for s in t.get("stale") or []:
        stale += evaluate(t, s.get("plan", t["steps"]), files, s.get("version"), {**reading, **s.get("reading", {})})
    void = bool(stale) and any(matches(t["expect"], g, as_answer(t["expect"], s)) for g in good for s in stale)
    return good, stale, void


# ------------------------------------------------------------------------------------------------ systems
class GraphAudit:
    def __init__(self, spec, live, llm, reuse=True):
        from t2r.session import Session
        self.llm, self.s = llm, Session(live, name=spec["name"], description=spec["description"], on_ambiguity="ask", reuse=reuse, budget_ops=float(os.environ.get("T2A_BUDGET_OPS", "1e10")))

    def ask(self, q):
        r = self.s.ask(q, self.llm)
        asked = r["outcome"] == "clarify"
        if asked and r.get("contracts"):
            r = self.s.choose(next((k for k, c in enumerate(r["contracts"]) if c["reading"] == "B"), 0))
        return {"answer": r.get("answer"), "asked": asked, "error": r.get("error"), "execute_seconds": r.get("execute_seconds") or 0,
                "steps_reused": r.get("steps_reused") or 0, "steps_executed": r.get("steps_executed") or 0, "plan": r.get("plan"),
                "flags": [f["check"] for f in (r.get("reuse_findings") or []) + (r.get("findings") or []) if not f["ok"]], "outcome": r.get("outcome")}

    def close(self):
        pass


def outside(spec, live, llm, variant, timeout):
    from run_langgraph import CodeAct                      # LangGraph CodeAct: needs the .venv-lg environment
    return CodeAct(spec, live, llm, variant, timeout)


class Codegen:
    def __init__(self, spec, live, llm, variant, timeout):
        from run_codegen_sessions import Agent
        self.a = Agent({**spec, "path": live}, llm, variant != "codegen_independent", timeout, warned=variant.endswith("warned"))

    def ask(self, q):
        r = self.a.ask(q)
        asked, secs = bool(r.get("clarification")), r["execute_seconds"]
        if asked and r.get("answer") is None:
            r = self.a.ask("Use your best judgement and answer.")
            secs += r["execute_seconds"]
        return {"answer": r.get("answer"), "asked": asked, "error": r.get("error"), "execute_seconds": secs, "steps_reused": 0, "steps_executed": 0,
                "plan": r.get("code"), "flags": (["repaired"] if r["repaired"] else []) + (["restarted"] if r["restarted"] else []), "outcome": "answer"}

    def close(self):
        self.a.close()


# ------------------------------------------------------------------------------------------------ main
def summarise(rows, llm, variant, model, out):
    traps = [r for r in rows if r["trap"] and not r["void"]]
    valid = [r for r in rows if r["valid"]]
    per = {}
    for c in sorted({r["trap"] for r in traps}):
        rs = [r for r in traps if r["trap"] == c]
        per[c] = {"turns": len(rs), "correct": sum(r["correct"] for r in rs), "stale": sum(r["stale"] for r in rs),
                  "other_wrong": sum(not r["correct"] and not r["stale"] for r in rs)}
    steps = sum(r["steps_reused"] + r["steps_executed"] for r in valid) or 1
    S = {"variant": variant, "model": model, "sessions": len({r["session"] for r in rows}), "turns": len(rows),
         "answer_accuracy": round(sum(r["correct"] for r in rows) / (len(rows) or 1), 4),
         "trap_turns": len(traps), "trap_correct": sum(r["correct"] for r in traps), "trap_stale": sum(r["stale"] for r in traps),
         "trap_other_wrong": sum(not r["correct"] and not r["stale"] for r in traps), "void_trap_turns": sum(bool(r["trap"]) and r["void"] for r in rows),
         "by_class": per, "valid_turns": len(valid), "valid_correct": sum(r["correct"] for r in valid),
         "valid_execute_seconds": round(sum(r["execute_seconds"] for r in valid), 2), "valid_share_steps_reused": round(sum(r["steps_reused"] for r in valid) / steps, 4),
         "execute_seconds": round(sum(r["execute_seconds"] for r in rows), 2),
         "compute_seconds": round(sum(r.get("compute_seconds") or 0 for r in rows), 1), "setup_seconds": round(sum(r.get("setup_seconds") or 0 for r in rows), 1),
         "model_seconds": round(sum(r.get("model_seconds") or 0 for r in rows), 1),
         "compute_seconds_by_graph": {g: {"setup": round(sum(r.get("setup_seconds") or 0 for r in rows if r["graph"] == g), 1),
                                          "turns": [round(r.get("compute_seconds") or 0, 1) for r in rows if r["graph"] == g]} for g in sorted({r["graph"] for r in rows})},
         "wall_seconds": round(sum(r["wall_seconds"] for r in rows), 1),
         "errors": sum(bool(r["error"]) for r in rows), "llm_calls": sum(r.get("llm_calls") or 0 for r in rows), "tokens_in": sum(r.get("tokens_in") or 0 for r in rows),
         "tokens_out": sum(r.get("tokens_out") or 0 for r in rows), "tokens_cache_read": sum(r.get("tokens_cache_read") or 0 for r in rows),
         "tokens_cache_write": sum(r.get("tokens_cache_write") or 0 for r in rows), "prompt_cache": os.environ.get("T2R_PROMPT_CACHE") == "1", "plan_replay": os.environ.get("T2R_PLAN_REPLAY") == "1", "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 4),
         "stale_turns": [f"{r['session']} t{r['turn']} ({r['trap']})" for r in traps if r["stale"]],
         "wrong_turns": [f"{r['session']} t{r['turn']} ({r['trap'] or ('valid' if r['valid'] else r['kind'])})" for r in rows if not r["correct"] and not r["stale"]]}
    json.dump(S, open(os.path.join(out, "summary.json"), "w"), indent=1)
    print(json.dumps(S, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("graphs", nargs="*")
    ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--variant", default="full"); ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--practice", default="", help="directory with the SNAP graphs: run the practice sessions (workload_practice.py)")
    ap.add_argument("--large", default="", help="directory with the SNAP graphs: run the large-graph sessions (workload_large.py) instead")
    ap.add_argument("--work", default="", help="where the per-session copies of the files go (default: <out>/work; use node scratch for large graphs)"); ap.add_argument("--dry", action="store_true")
    ap.add_argument("--rescore", action="store_true", help="score the answers already in <out>/turns.jsonl again; no system is run")
    a = ap.parse_args()
    assert a.dry or a.variant in VARIANTS
    os.makedirs(a.out, exist_ok=True)
    llm = None if a.dry or a.rescore else LLM(model=a.model)
    rows = []
    old = {}
    if a.rescore:
        old = {(d["session"], d["turn"]): d for d in map(json.loads, open(os.path.join(a.out, "turns.jsonl")))}
        if not os.path.exists(os.path.join(a.out, "summary.before_rescore.json")):
            shutil.copy(os.path.join(a.out, "summary.json"), os.path.join(a.out, "summary.before_rescore.json"))
        a.variant, a.model = next(iter(old.values()))["variant"], next(iter(old.values()))["model"]
    log = open(os.path.join(a.out, "turns.rescored.jsonl" if a.rescore else "turns.jsonl"), "w")
    if a.practice:
        import workload_practice
        all_specs, sessions_of = workload_practice.specs(a.practice), workload_practice.sessions
    elif a.large:
        import workload_large
        all_specs, sessions_of = workload_large.specs(a.large), workload_large.sessions
    else:
        all_specs, sessions_of = specs(a.graphs), sessions
    for spec in all_specs:
        for sess in sessions_of(spec):
            if a.only and a.only not in sess["id"]:
                continue
            files = Files(spec, os.path.join(a.work or os.path.join(a.out, "work"), sess["id"].replace("/", "_")))
            t_setup = time.time()
            system = None if a.dry or a.rescore else (GraphAudit(spec, files.live, llm, reuse=a.variant != "full_noreuse") if a.variant.startswith("full") else outside(spec, files.live, llm, a.variant, a.timeout) if a.variant.startswith("codeact") else Codegen(spec, files.live, llm, a.variant, a.timeout))
            setup = round(time.time() - t_setup, 2)       # GraphAudit: load and profile; agents: file facts
            reading = {}
            for i, t in enumerate(sess["turns"], 1):
                ev = files.event(t["event"]) if t.get("event") else None
                reading = {**reading, **t.get("reading", {})}
                good, stale, void = golds_for(t, files, reading)
                base = {"session": sess["id"], "graph": spec["name"], "class": sess["class"], "turn": i, "q": t["q"], "kind": t["kind"], "expect": t["expect"],
                        "trap": t.get("trap"), "valid": bool(t.get("valid")), "void": void, "event": ev, "variant": a.variant, "model": a.model}
                if a.dry:
                    rows.append({**base, "correct": True, "stale": False, "error": None, "steps_reused": 0, "steps_executed": 0, "execute_seconds": 0, "wall_seconds": 0})
                    print(f"{sess['id']:<28} t{i} {t.get('trap') or ('valid' if t.get('valid') else '-'):<5} {'VOID ' if void else ''}{json.dumps(ev) if ev else ''} gold {json.dumps(good[0], default=str)[:90]}", flush=True)
                    continue
                if a.rescore:
                    d = old[(sess["id"], i)]
                    ok = any(matches(t["expect"], g, d["answer"]) for g in good)
                    row = {**d, **base, "correct": ok, "stale": not ok and any(matches(t["expect"], g, d["answer"]) for g in stale), "gold": good, "stale_gold": stale}
                    rows.append(row); log.write(json.dumps(row, default=str) + "\n")
                    continue
                c0, i0, o0, u0, m0, r0, w0 = llm.usage.calls, llm.usage.input_tokens, llm.usage.output_tokens, llm.usage.cost_usd, llm.usage.seconds, llm.usage.cache_read_tokens, llm.usage.cache_write_tokens
                t0 = time.time()
                try:
                    r = system.ask(t["q"])
                except Exception as e:  # noqa: BLE001
                    r = {"answer": None, "asked": False, "error": f"{type(e).__name__}: {e}", "execute_seconds": 0, "steps_reused": 0, "steps_executed": 0, "plan": None, "flags": [], "outcome": "error"}
                wall = time.time() - t0
                ok = any(matches(t["expect"], g, r["answer"]) for g in good)
                is_stale = not ok and any(matches(t["expect"], g, r["answer"]) for g in stale)
                row = {**base, "correct": ok, "stale": is_stale, "asked": r["asked"], "error": r["error"], "outcome": r["outcome"], "flags": r["flags"],
                       "steps_reused": r["steps_reused"], "steps_executed": r["steps_executed"], "execute_seconds": round(r["execute_seconds"], 3), "wall_seconds": round(wall, 3),
                       # everything that is not waiting for the model: loading, hashing, executing, verifying
                       "model_seconds": round(llm.usage.seconds - m0, 3), "compute_seconds": round(wall - (llm.usage.seconds - m0), 3), "setup_seconds": setup if i == 1 else 0,
                       "llm_calls": llm.usage.calls - c0, "tokens_in": llm.usage.input_tokens - i0, "tokens_out": llm.usage.output_tokens - o0, "cost_usd": round(llm.usage.cost_usd - u0, 5),
                       "tokens_cache_read": llm.usage.cache_read_tokens - r0, "tokens_cache_write": llm.usage.cache_write_tokens - w0}
                rows.append(row)
                log.write(json.dumps({**row, "answer": r["answer"], "gold": good, "stale_gold": stale, "plan": r["plan"]}, default=str) + "\n"); log.flush()
                tag = t.get("trap") or ("valid" if t.get("valid") else "-")
                print(f"{sess['id']:<28} t{i} {tag:<5} {'OK   ' if ok else ('STALE' if is_stale else 'BAD  ')} compute {row['compute_seconds']:7.1f}s exec {r['execute_seconds']:6.1f}s reused {r['steps_reused']}/{r['steps_reused'] + r['steps_executed']}"
                      f"{' asked' if r['asked'] else ''}{' void' if void else ''} {','.join(r['flags'])} {r['error'] or ''}"[:230], flush=True)
            if system:
                system.close()
            graphs._GRAPH_CACHE.clear(); GOLD_STORE.clear()
            shutil.rmtree(files.work, ignore_errors=True)
            for f in os.listdir(SCRATCH_CACHE):
                os.remove(os.path.join(SCRATCH_CACHE, f))
    shutil.rmtree(SCRATCH_CACHE, ignore_errors=True)
    summarise(rows, llm, a.variant if not a.dry else "dry", a.model, a.out)


if __name__ == "__main__":
    main()
