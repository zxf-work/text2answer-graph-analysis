"""E2 baselines: code-generation agents on the session workload. Calls a model: run on a server.

Usage: python bench/sessions/run_codegen_sessions.py <out dir> --model M --variant V <attributed graph>...
Variants:
  codegen_stateful     a notebook-style agent: one Python process per session, each turn is a cell run in that process,
                       so variables from earlier turns stay available. Reuse is whatever the model chooses to reuse.
  codegen_independent  each turn is a complete script run in a fresh process. Nothing computed earlier is available.
Both see the same conversation so far (questions, their own code, the printed output), the file facts and the head of
the node table. Both get one repair attempt after a failing cell. Turns are scored exactly as in run_sessions.py.
A simulated user answers a clarification question on an ambiguous turn by stating the annotated reading in words.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
os.environ["T2R_GRAPH_CACHE"] = "1"
from reuse_fault import run as run_plan  # noqa: E402
from run_sessions import specs, summarise  # noqa: E402
from workload import alternative_golds, gold_value, matches, sessions  # noqa: E402
from t2r.graphs import load_graph, read_facts, sidecar_node_table  # noqa: E402
from t2r.ir import validate  # noqa: E402
from t2r.llm import LLM  # noqa: E402
from t2r.systems import ANSWER_SCHEMA, _extract_code, _last_json  # noqa: E402

COMMON = """You are a graph data analyst working with a user over a session of several questions about one graph file.
Available libraries: networkx 3.x, igraph 1.0 (python-igraph), numpy, pandas. Prefer igraph for expensive algorithms on large graphs.
The file path, file facts and the node attribute table (if any) are given in the message. Decide directed/weighted from the file facts and the description.
A question may refer to earlier questions and their results ("them", "instead", "again", "within ..."); the conversation so far is given.
{mode}
The last line printed for the turn must be one line of JSON, the answer object:
{schema}
Reply with only the code inside a ```python fence."""

STATEFUL = """You work in a notebook: every reply is one cell, run in the same Python process as your earlier cells of this session, so every variable you defined earlier still exists. Reuse earlier variables when they are the right thing to reuse; recompute when they are not. If the note says the process was restarted, earlier variables are gone."""

INDEPENDENT = """Every reply is one complete Python 3 script, run in a new process: nothing from your earlier scripts exists any more, so read the file and compute everything the answer needs."""

WARNED = """ Take care with what you reuse: the files may have been changed since you read them, and an earlier variable may have been computed under another reading of the graph, for another group, or with other parameters than the current question needs. Check before reusing, and recompute when in doubt."""

SAY = {"A": "I mean: compute the measure over the whole network, then report it only for the members of that group.",
       "B": "I mean: consider only the members of that group and the links among them, and compute the measure on that part of the network."}

WORKER = r'''
import contextlib, io, json, sys, time, traceback
real = sys.stdout
ns = {"__name__": "__main__"}
for line in sys.stdin:
    code = json.loads(line)["code"]
    buf = io.StringIO(); rc = 0; err = ""; t0 = time.time()
    try:
        with contextlib.redirect_stdout(buf):
            exec(compile(code, "<cell>", "exec"), ns)
    except SystemExit:
        pass
    except BaseException:
        rc = 1; err = traceback.format_exc()
    real.write(json.dumps({"out": buf.getvalue()[-20000:], "err": err[-6000:], "rc": rc, "seconds": time.time() - t0}) + "\n"); real.flush()
'''


class Kernel:
    """One Python process that runs cells in a shared namespace. Restarted (state lost) after a timeout or a crash."""

    def __init__(self, timeout):
        self.timeout = timeout; self.dir = tempfile.mkdtemp(); self.p = None; self.restarts = -1
        with open(os.path.join(self.dir, "worker.py"), "w") as f:
            f.write(WORKER)
        self.start()

    def start(self):
        self.stop()
        mem_kb = int(os.environ.get("T2R_SCRIPT_MEM_MB", "24000")) * 1024
        self.p = subprocess.Popen(["bash", "-c", f"ulimit -v {mem_kb}; exec {sys.executable} -I {self.dir}/worker.py"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=self.dir, bufsize=1)
        self.restarts += 1

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.kill(); self.p.wait()

    def run(self, code):
        """-> out, err, rc, seconds, restarted"""
        t0 = time.time()
        try:
            self.p.stdin.write(json.dumps({"code": code}) + "\n"); self.p.stdin.flush()
            ready, _, _ = select.select([self.p.stdout], [], [], self.timeout)
            line = self.p.stdout.readline() if ready else ""
        except (BrokenPipeError, OSError):
            line = ""
        if not line:
            why = f"timeout after {self.timeout}s" if time.time() - t0 >= self.timeout - 1 else "the process died (out of memory or a crash)"
            self.start()
            return "", why + "; the process was restarted and earlier variables are gone", 124, time.time() - t0, True
        d = json.loads(line)
        return d["out"], d["err"], d["rc"], d["seconds"], False


def run_script(code, timeout):
    t0 = time.time()
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "script.py")
        with open(p, "w") as f:
            f.write(code)
        mem_kb = int(os.environ.get("T2R_SCRIPT_MEM_MB", "24000")) * 1024
        try:
            r = subprocess.run(["bash", "-c", f"ulimit -v {mem_kb}; exec {sys.executable} -I {p}"], capture_output=True, text=True, timeout=timeout, cwd=d)
            return r.stdout[-20000:], r.stderr[-6000:], r.returncode, time.time() - t0, False
        except subprocess.TimeoutExpired:
            return "", f"timeout after {timeout}s", 124, time.time() - t0, False


def head(path, n=4):
    with open(path) as f:
        return "".join(next(f, "") for _ in range(n))


class Agent:
    def __init__(self, spec, llm, stateful, timeout, warned=False):
        self.llm, self.stateful, self.timeout = llm, stateful, timeout
        self.kernel = Kernel(timeout) if stateful else None
        self.system = COMMON.format(mode=(STATEFUL if stateful else INDEPENDENT) + (WARNED if warned else ""), schema=ANSWER_SCHEMA)
        fx = {k: v for k, v in asdict(read_facts(spec["path"])).items() if k != "sha1"}
        table = sidecar_node_table(spec["path"])
        self.preamble = (f"File path: {os.path.abspath(spec['path'])}\nFile facts (read at the start of the session): {json.dumps(fx, default=str)}\n"
                         + (f"Node attribute table: {os.path.abspath(table)} (first rows, read at the start of the session):\n{head(table)}" if table else "Node attribute table: none.\n")
                         + f"Dataset description (from the user): {spec['description']}\n")
        self.history = []   # (question, code, printed output)

    def close(self):
        if self.kernel:
            self.kernel.stop()

    def _exec(self, code):
        return self.kernel.run(code) if self.stateful else run_script(code, self.timeout)

    def ask(self, question):
        past = "".join(f"--- turn {i} ---\nUser: {q}\nYour code:\n```python\n{c}\n```\nPrinted output (tail):\n{o[-1500:]}\n" for i, (q, c, o) in enumerate(self.history, 1))
        user = self.preamble + ("\nConversation so far:\n" + past if past else "") + f"\n--- turn {len(self.history) + 1} ---\nUser: {question}"
        r = {"execute_seconds": 0.0, "restarted": False, "repaired": False, "error": None}
        code = _extract_code(self.llm.chat(self.system, user).text)
        out, err, rc, secs, restarted = self._exec(code)
        r["execute_seconds"] += secs; r["restarted"] |= restarted
        if rc != 0 or not _last_json(out):
            r["repaired"] = True
            code = _extract_code(self.llm.chat(self.system, user + f"\n\nYour code for this turn failed (exit {rc}).\n```python\n{code}\n```\nError:\n{err[-3000:]}\nPrinted output:\n{out[-1500:]}\n"
                                                                    + ("Return a corrected cell." if self.stateful else "Return a corrected full script.")).text)
            out, err, rc, secs, restarted = self._exec(code)
            r["execute_seconds"] += secs; r["restarted"] |= restarted
        fin = _last_json(out)
        self.history.append((question, code, out if fin else f"{out}\n[failed: {err[-600:]}]"))
        if fin is None:
            r["error"] = f"no JSON answer (rc={rc}): {err[-300:]}"
        r.update(answer=(fin or {}).get("answer"), clarification=(fin or {}).get("clarification"), assumptions=(fin or {}).get("assumptions"), code=code)
        return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("graphs", nargs="*")
    ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--variant", default="codegen_stateful"); ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    assert a.variant in ("codegen_stateful", "codegen_independent")
    os.makedirs(a.out, exist_ok=True)
    llm = LLM(model=a.model)
    rows = []
    log = open(os.path.join(a.out, "turns.jsonl"), "w")
    for spec in specs(a.graphs):
        gold_lg = load_graph(spec["name"], spec["path"], spec["description"], override={"directed": spec["directed"], "weighted": spec["weighted"]})
        for sess in sessions(spec):
            if a.only and a.only not in sess["id"]:
                continue
            agent = Agent(spec, llm, a.variant == "codegen_stateful", a.timeout)
            for i, t in enumerate(sess["turns"], 1):
                golds = {}
                for reading, plan in t["gold"].items():
                    assert not validate(plan, gold_lg, 1e13), (sess["id"], i)
                    vals, _ = run_plan(plan, gold_lg, 1, None, {})
                    golds[reading] = gold_value(t["expect"], vals[plan.steps[-1].id], t)
                ambiguous = "user" in t
                want = golds[t["user"]] if ambiguous else golds["-"]
                c0, i0, o0, u0 = llm.usage.calls, llm.usage.input_tokens, llm.usage.output_tokens, llm.usage.cost_usd
                t0 = time.time()
                r = agent.ask(t["q"])
                asked = bool(r.get("clarification"))
                secs, restarted = r["execute_seconds"], r["restarted"]
                if asked and (ambiguous or r.get("answer") is None):
                    first = r
                    r = agent.ask(SAY[t["user"]] if ambiguous else "Use your best judgement and answer.")
                    secs += r["execute_seconds"]; restarted |= r["restarted"]; r["clarification"] = first["clarification"]
                wall = time.time() - t0
                ok = any(matches(t["expect"], w, r.get("answer")) for w in [want] + alternative_golds(t, gold_lg, spec["path"]))
                other = [k for k in golds if ambiguous and k != t["user"]]
                row = {"session": sess["id"], "graph": spec["name"], "turn": i, "q": t["q"], "kind": t["kind"], "expect": t["expect"], "variant": a.variant, "model": a.model,
                       "ambiguous": ambiguous, "carried": bool(t.get("carried")), "asked": asked, "asked_contracts": False,
                       # an ambiguous turn is handled correctly if the agent asks, or if the user already chose earlier and the agent follows that choice
                       "decision_ok": (asked or bool(t.get("carried")) and ok) if ambiguous else not asked,
                       "correct": ok, "other_reading": bool(other) and matches(t["expect"], golds[other[0]], r.get("answer")) and not ok,
                       "outcome": "clarify" if asked else "answer", "reading": None, "intent": None, "error": r.get("error"),
                       "steps_reused": 0, "steps_executed": 0, "execute_seconds": round(secs, 3), "seconds_saved": 0, "wall_seconds": round(wall, 3),
                       "llm_calls": llm.usage.calls - c0, "tokens_in": llm.usage.input_tokens - i0, "tokens_out": llm.usage.output_tokens - o0,
                       "cost_usd": round(llm.usage.cost_usd - u0, 5), "repaired": r["repaired"], "restarted": restarted, "verifier_flags": [], "rule_flags": []}
                rows.append(row)
                log.write(json.dumps({**row, "answer": r.get("answer"), "gold": want, "plan": r.get("code"), "clarification": r.get("clarification"),
                                      "assumptions": r.get("assumptions")}, default=str) + "\n"); log.flush()
                print(f"{sess['id']:<28} t{i} {t['kind']:<8} {'OK ' if ok else 'BAD'} exec {secs:6.1f}s{' asked' if asked else ''}{' repaired' if r['repaired'] else ''}"
                      f"{' RESTARTED' if restarted else ''}{' OTHER-READING' if row['other_reading'] else ''} {r.get('error') or ''}"[:230], flush=True)
            agent.close()
    S = summarise(rows, llm, a.variant, a.model, a.out)
    S.update(repaired_turns=sum(r["repaired"] for r in rows), restarted_turns=sum(r["restarted"] for r in rows),
             follow_up_execute_seconds=round(sum(r["execute_seconds"] for r in rows if r["kind"] != "new"), 2))
    json.dump(S, open(os.path.join(a.out, "summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
