"""Sessions written by a model that knew nothing about GraphAudit (write_sessions.py), run through the same systems as
the other session workloads. Calls a model: run on a server.

  python bench/sessions/run_written.py <out dir> --written runs/written/<writer> --snap <dir with the SNAP files>
         --graph pokec|livejournal|twitch --model M --variant V [--only s03]

There are no gold plans here: every turn's answer is stored as given, with the outcome (answer, clarify, unsupported,
error). Reference answers and agreement between systems are computed afterwards (compare_written.py).
A question that says the file was refreshed gets a real change first: new rows are appended to the session's copy of
the edge file (the same event as in the practice sessions).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE))); sys.path.insert(0, HERE)
import run_stale as R  # noqa: E402
import t2r.graphs as graphs  # noqa: E402
from t2r.llm import LLM  # noqa: E402

GRAPHS = {
    "pokec": {"file": "soc-pokec-relationships.txt", "directed": True, "weighted": False,
              "description": "The Pokec social network: each row is a directed friendship, the first user lists the second as a friend (not always returned). "
                             "The node table gives each user's public flag (1 if the profile is public), completion_percentage (0-100), gender, region and age (empty when not given)."},
    "livejournal": {"file": "soc-LiveJournal1.txt", "directed": True, "weighted": False,
                    "description": "The LiveJournal blogging community: each row is a directed friendship declaration, the first user declared the second a friend."},
    "twitch": {"file": "twitch-gamers.txt", "directed": False, "weighted": False,
               "description": "Twitch gamers: each row is a pair of users who follow each other; each pair appears once and the relationship is mutual (undirected). "
                              "The node table gives each user's views, mature flag, life_time (days), created_at and updated_at dates, dead_account flag, language code and affiliate flag."},
}
REFRESH = re.compile(r"\b((was|were|has been|have been|got|is|are) (just |now )?(refreshed|updated|reloaded)|just (been )?(refreshed|updated|reloaded)|new rows (have )?(arrived|were added|came in))\b", re.I)   # an announcement, not "after the refresh"
EVENT = {"type": "append_edges", "targets": [30, 60], "n": "max"}

USER = """You are the person described below, in a conversation with an assistant that analyses a network dataset for you.
The assistant asks which of two readings of your last question you mean. Answer as that person would, from what the
question says and what the person wants. Reply with one letter only: A or B.

You are: {persona}
Your questions so far:
{history}
Your last question: {q}
The assistant: {ask}"""


class AuditWithUser(R.GraphAudit):
    """GraphAudit, with its question about the scope reading answered by a simulated user (a model that sees the persona,
    the questions so far and the two contracts, nothing else). Its fees are not charged to the system."""

    def __init__(self, spec, live, llm, reuse, persona, user_llm):
        super().__init__(spec, live, llm, reuse)
        self.persona, self.user, self.asked_before, self.choices = persona, user_llm, [], []

    def ask(self, q):
        r = self.s.ask(q, self.llm)
        asked = r["outcome"] == "clarify"
        if asked and r.get("contracts"):
            text = self.user.chat("", USER.format(persona=self.persona, history="\n".join(f"- {x}" for x in self.asked_before) or "(none)", q=q, ask=r.get("clarification")), max_tokens=2000).text
            m = re.search(r"\b([AB])\b", text.strip())
            want = m.group(1) if m else "A"
            self.choices.append(want)
            r = self.s.choose(next((k for k, c in enumerate(r["contracts"]) if c["reading"] == want), 0))
        self.asked_before.append(q)
        return {"answer": r.get("answer"), "asked": asked, "error": r.get("error"), "execute_seconds": r.get("execute_seconds") or 0,
                "steps_reused": r.get("steps_reused") or 0, "steps_executed": r.get("steps_executed") or 0, "plan": r.get("plan"),
                "flags": [f["check"] for f in (r.get("reuse_findings") or []) + (r.get("findings") or []) if not f["ok"]] + ([f"user_chose_{self.choices[-1]}"] if asked and r.get("contracts") else []),
                "outcome": r.get("outcome")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--written", required=True); ap.add_argument("--snap", required=True); ap.add_argument("--graph", required=True)
    ap.add_argument("--model", default="claude-haiku-5-5"); ap.add_argument("--variant", default="full"); ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=1200); ap.add_argument("--work", default="")
    a = ap.parse_args()
    assert a.variant in R.VARIANTS
    spec = {"name": a.graph, **GRAPHS[a.graph], "path": os.path.join(a.snap, GRAPHS[a.graph]["file"])}
    doc = json.load(open(os.path.join(a.written, f"{a.graph}.json")))
    os.makedirs(a.out, exist_ok=True)
    done = set()
    log_path = os.path.join(a.out, "turns.jsonl")
    if os.path.exists(log_path):                                   # a resubmitted job continues after the sessions already finished
        rows = [json.loads(x) for x in open(log_path)]
        n_of = {f"s{k:02d}": len(s["questions"]) for k, s in enumerate(doc["sessions"], 1)}
        done = {sid for sid in n_of if sum(r["session"] == sid for r in rows) == n_of[sid]}
        with open(log_path, "w") as f:
            f.writelines(json.dumps(r, default=str) + "\n" for r in rows if r["session"] in done)
    log = open(log_path, "a")
    llm = LLM(model=a.model)
    user_llm = LLM(model=os.environ.get("T2A_USER_MODEL", "claude-haiku-5-5"))      # answers GraphAudit's scope question; not part of the system's fees
    for k, sess in enumerate(doc["sessions"], 1):
        sid = f"s{k:02d}"
        if (a.only and a.only != sid) or sid in done:
            continue
        files = R.Files(spec, os.path.join(a.work or os.path.join(a.out, "work"), sid))
        t_setup = time.time()
        system = (AuditWithUser(spec, files.live, llm, a.variant != "full_noreuse", sess.get("persona") or "an analyst", user_llm) if a.variant.startswith("full")
                  else R.outside(spec, files.live, llm, a.variant, a.timeout) if a.variant.startswith("codeact") else R.Codegen(spec, files.live, llm, a.variant, a.timeout))
        setup = round(time.time() - t_setup, 2)
        for i, q in enumerate(sess["questions"], 1):
            ev = files.event(EVENT) if i > 1 and REFRESH.search(q) else None
            u = llm.usage
            c0, i0, o0, u0, m0, r0, w0 = u.calls, u.input_tokens, u.output_tokens, u.cost_usd, u.seconds, u.cache_read_tokens, u.cache_write_tokens
            t0, us0 = time.time(), user_llm.usage.seconds
            try:
                r = system.ask(q)
            except Exception as e:  # noqa: BLE001
                r = {"answer": None, "asked": False, "error": f"{type(e).__name__}: {e}", "execute_seconds": 0, "steps_reused": 0, "steps_executed": 0, "plan": None, "flags": [], "outcome": "error"}
            wall = time.time() - t0 - (user_llm.usage.seconds - us0)      # waiting for the simulated user is not the system's time
            last = system.s.turns[-1] if hasattr(system, "s") and system.s.turns else {}
            outcome = "error" if r["error"] else r["outcome"] if r["outcome"] in ("clarify", "unsupported", "unconfirmed") else "answer" if r["answer"] is not None else "no answer"
            row = {"writer": doc.get("writer"), "graph": a.graph, "session": sid, "persona": sess.get("persona"), "turn": i, "q": q, "event": ev, "variant": a.variant, "model": a.model,
                   "outcome": outcome, "session_outcome": r["outcome"], "asked": r["asked"], "error": r["error"], "flags": r["flags"], "unsupported": last.get("unsupported"),
                   "clarification": last.get("clarification"), "conventions": last.get("conventions"), "code": last.get("code"), "answer_value": last.get("answer_value"), "candidates": last.get("candidates"), "steps_reused": r["steps_reused"], "steps_executed": r["steps_executed"],
                   "execute_seconds": round(r["execute_seconds"], 3), "wall_seconds": round(wall, 3), "model_seconds": round(u.seconds - m0, 3),
                   "compute_seconds": round(wall - (u.seconds - m0), 3), "setup_seconds": setup if i == 1 else 0, "llm_calls": u.calls - c0, "tokens_in": u.input_tokens - i0,
                   "tokens_out": u.output_tokens - o0, "tokens_cache_read": u.cache_read_tokens - r0, "tokens_cache_write": u.cache_write_tokens - w0, "cost_usd": round(u.cost_usd - u0, 5),
                   "answer": r["answer"], "plan": r["plan"]}
            log.write(json.dumps(row, default=str) + "\n"); log.flush()
            print(f"{sid} t{i} {outcome:<11} compute {row['compute_seconds']:7.1f}s reused {r['steps_reused']}/{r['steps_reused'] + r['steps_executed']} {'EVENT ' if ev else ''}"
                  f"{','.join(r['flags'])} {r['error'] or last.get('unsupported') or ''} | {json.dumps(r['answer'], default=str)[:80]}"[:260], flush=True)
        system.close()
        graphs._GRAPH_CACHE.clear(); R.GOLD_STORE.clear()
        shutil.rmtree(files.work, ignore_errors=True)
        for f in os.listdir(R.SCRATCH_CACHE):
            os.remove(os.path.join(R.SCRATCH_CACHE, f))
    shutil.rmtree(R.SCRATCH_CACHE, ignore_errors=True)
    rows = [json.loads(x) for x in open(log_path)]
    S = {"writer": doc.get("writer"), "graph": a.graph, "variant": a.variant, "model": a.model, "sessions": len({r["session"] for r in rows}), "turns": len(rows),
         "outcomes": {o: sum(r["outcome"] == o for r in rows) for o in sorted({r["outcome"] for r in rows})}, "events": sum(bool(r["event"]) for r in rows),
         "compute_seconds": round(sum(r["compute_seconds"] for r in rows), 1), "setup_seconds": round(sum(r["setup_seconds"] for r in rows), 1),
         "llm_calls": sum(r["llm_calls"] for r in rows), "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
         "prompt_cache": os.environ.get("T2R_PROMPT_CACHE") == "1", "plan_replay": os.environ.get("T2R_PLAN_REPLAY") == "1"}
    json.dump(S, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    print(json.dumps(S, indent=1))


if __name__ == "__main__":
    main()
