"""An outside baseline: the LangGraph CodeAct agent (package langgraph-codeact), driven through the same session harness
as our own code agents (run_stale.py, variants codeact and codeact_warned).

What is the framework's and what is ours:
  framework  the agent loop (model writes a code block, the sandbox output goes back as the next message, until a
             reply without code), its default prompt, and the conversation memory (MemorySaver, one thread per session)
  ours       the sandbox the framework asks its user to supply: the same persistent Python process our stateful agent
             uses (Kernel: memory cap, timeout, restart), so variables live across turns as CodeAct intends; and a
             task description with the same file facts and answer format the other agents get

Needs its own environment (.venv-lg: requirements.lock.txt plus langgraph-codeact and langchain-anthropic); run with
T2A_PY pointing at it. No prompt caching (the framework default).
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE))); sys.path.insert(0, HERE)
from run_codegen_sessions import WARNED, Kernel, head  # noqa: E402
from t2r.graphs import read_facts, sidecar_node_table  # noqa: E402
from t2r.llm import LLM, Reply, parse_json  # noqa: E402
from t2r.systems import ANSWER_SCHEMA, _last_json  # noqa: E402

TASK = """You are a graph data analyst working with a user over a session of several questions about one graph file.
Available libraries: networkx 3.x, igraph 1.0 (python-igraph), numpy, pandas. Prefer igraph for expensive algorithms on large graphs.
Decide directed/weighted from the file facts and the description. A question may refer to earlier questions and their results.
{warned}
Compute with code first. Your final reply to each question, the one without code, must be only the answer object, as one JSON object:
{schema}

{files}"""


class _Counted:
    """The chat model as the framework calls it (invoke), with the tokens added to the harness's usage record."""

    def __init__(self, llm: LLM):
        from langchain_anthropic import ChatAnthropic
        self.llm = llm
        self.model = ChatAnthropic(model=llm.model, max_tokens=8000, timeout=600, max_retries=3)

    def invoke(self, messages, *a, **k):
        t0 = time.time()
        resp = self.model.invoke(messages, *a, **k)
        u = getattr(resp, "usage_metadata", None) or {}
        details = u.get("input_token_details") or {}
        cr, cw = details.get("cache_read", 0) or 0, details.get("cache_creation", 0) or 0
        fresh = max((u.get("input_tokens", 0) or 0) - cr - cw, 0)
        pin, pout = LLM._PRICES.get(self.llm.model, (4.0, 20.0))
        out = u.get("output_tokens", 0) or 0
        cost = (fresh * pin + cr * pin * LLM._CACHE_READ.get(self.llm.model, 0.1) + cw * pin * 1.25 + out * pout) / 1e6
        self.llm.usage.add(Reply(text="", input_tokens=fresh, output_tokens=out, cache_read_tokens=cr, cache_write_tokens=cw, cost_usd=cost, seconds=time.time() - t0))
        if not isinstance(resp.content, str):            # content blocks: the framework's code extraction wants text
            resp.content = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in resp.content)
        return resp


class CodeAct:
    def __init__(self, spec, live, llm, variant, timeout):
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph_codeact import create_codeact, create_default_prompt
        self.kernel = Kernel(timeout)
        self.turn_out, self.turn_secs, self.restarted = [], 0.0, False
        fx = {k: v for k, v in asdict(read_facts(live)).items() if k != "sha1"}
        table = sidecar_node_table(live)
        files = (f"File path: {os.path.abspath(live)}\nFile facts (read at the start of the session): {json.dumps(fx, default=str)}\n"
                 + (f"Node attribute table: {os.path.abspath(table)} (first rows, read at the start of the session):\n{head(table)}" if table else "Node attribute table: none.\n")
                 + f"Dataset description (from the user): {spec['description']}\n")
        prompt = create_default_prompt([], TASK.format(warned=WARNED.strip() if variant.endswith("warned") else "", schema=ANSWER_SCHEMA, files=files))
        self.agent = create_codeact(_Counted(llm), [], self._eval, prompt=prompt).compile(checkpointer=MemorySaver())
        self.config = {"configurable": {"thread_id": "session"}, "recursion_limit": int(os.environ.get("T2R_CODEACT_STEPS", "16"))}

    def _eval(self, code, _locals):
        out, err, rc, secs, restarted = self.kernel.run(code)
        self.turn_secs += secs; self.restarted |= restarted
        self.turn_out.append(out)
        shown = out[-6000:] if rc == 0 else f"{out[-3000:]}\nError (exit {rc}):\n{err[-3000:]}"
        return shown or "(no output)", {}                 # variables stay in the process, not in the checkpointed state

    def ask(self, q):
        r = self._ask(q)
        if r["asked"]:                                     # as for the other agents: a question back gets one push
            secs = r["execute_seconds"]
            r = self._ask("Use your best judgement and answer.")
            r["execute_seconds"] += secs; r["asked"] = True
        return r

    def _ask(self, q):
        self.turn_out, self.turn_secs, self.restarted = [], 0.0, False
        error = None
        fin = None
        for msg in (q, "Reply with only the JSON answer object for that question."):     # one reminder, as the other agents get one repair
            try:
                state = self.agent.invoke({"messages": [{"role": "user", "content": msg}]}, self.config)
                fin = self._answer(state["messages"][-1].content)
            except Exception as e:  # noqa: BLE001  (step limit reached, API error): score what was printed so far
                error = f"{type(e).__name__}: {str(e)[:300]}"
            fin = fin or next((j for j in (_last_json(o) for o in reversed(self.turn_out)) if isinstance(j, dict) and "answer" in j), None)
            if fin is not None:
                break
        if fin is None and error is None:
            error = "no JSON answer"
        asked = bool((fin or {}).get("clarification")) and (fin or {}).get("answer") is None
        return {"answer": (fin or {}).get("answer"), "asked": asked, "error": None if fin else error, "execute_seconds": self.turn_secs,
                "steps_reused": 0, "steps_executed": 0, "plan": "\n# ---\n".join(self.turn_out)[-4000:],
                "flags": (["restarted"] if self.restarted else []) + ([f"rounds={len(self.turn_out)}"] if len(self.turn_out) > 1 else []), "outcome": "answer"}

    @staticmethod
    def _answer(text):
        try:
            j = parse_json(text if isinstance(text, str) else str(text))
            return j if isinstance(j, dict) and "answer" in j else None
        except Exception:  # noqa: BLE001
            return None

    def close(self):
        self.kernel.stop()
