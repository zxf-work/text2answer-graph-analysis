"""An outside baseline: GraphTeam (BUPT-GAMMA, arXiv 2410.18032), driven through the same session harness as our own
agents (run_stale.py, variants graphteam and graphteam_nosearch).

What is the system's and what is ours:
  GraphTeam's  the six phases and their prompts as published (question analysis, search, coding, execution with up to
               three repairs, reasoning without code when execution fails, output correction), its knowledge base
               (NetworkX documentation) and its experience base. Its files are imported as they are; nothing in its
               repository is edited.
  ours         three things its code takes from outside and that we cannot supply as published:
               - the chat model: it calls the OpenAI client with a fixed list of OpenAI models; here every call goes to
                 the model under test (Anthropic SDK), with the same messages. Its temperature of 0.2 is not passed:
                 the SDK takes none for these models;
               - the sandbox: it runs code inside a Docker container (`docker exec graphteam ...`, a script that is in
                 the image, not in the repository); the cluster has no Docker, so the code runs as a script in our
                 Python environment with its 600 s limit, and the result carries the "Success: " / "Error: " prefix
                 its execution agent tests for;
               - the embeddings behind search: its stored indexes hold OpenAI embeddings; we rebuild both indexes from
                 its own documents with an open embedding model (T2A_GT_EMBED). Its similarity threshold for the
                 experience base (0.85) was set for the OpenAI model and is kept as it is.
               Variant graphteam_nosearch skips the search phase (the paper's own ablation) and needs no embeddings.

GraphTeam answers single questions and keeps nothing between them. A session is given to it turn by turn: each
question carries the file facts the other agents get, the earlier questions of the session with the answers it gave,
and the answer format.

Needs its own environment (.venv-gt: GraphTeam's requirements plus anthropic and, for search, an embedding package) and
T2A_GRAPHTEAM pointing at <clone>/multi-agents-4-graph-analysis/GraphTeam.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import types
from dataclasses import asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE))); sys.path.insert(0, HERE)
from run_codegen_sessions import head, run_script  # noqa: E402
from t2r.graphs import read_facts, sidecar_node_table  # noqa: E402
from t2r.llm import LLM, Reply, parse_json  # noqa: E402
from t2r.systems import ANSWER_SCHEMA  # noqa: E402

EXEC_TIMEOUT = 600          # GraphTeam's own limit for one execution (camel/agents.py)
_STATE = {"llm": None, "secs": 0.0, "runs": 0}


class _Backend:
    """What GraphTeam's agents call: run(messages=[...], response_format=...) -> an object read as
    .choices[0].message.content. The messages go to the model under test; tokens are added to the harness's record."""

    def __init__(self, model_name, config):
        pass

    def run(self, messages, response_format=None, **_):
        import anthropic
        llm: LLM = _STATE["llm"]
        system, turns = [], []
        for m in messages:
            role, text = m["role"], str(m["content"])
            if role == "system" and not turns:
                system.append(text); continue
            role = "assistant" if role == "assistant" else "user"          # a later system message is an instruction
            if turns and turns[-1]["role"] == role:
                turns[-1]["content"] += "\n\n" + text
            else:
                turns.append({"role": role, "content": text})
        if not turns or turns[0]["role"] != "user":
            turns.insert(0, {"role": "user", "content": "(start)"})
        if turns[-1]["role"] != "user":
            turns.append({"role": "user", "content": "Continue."})
        if response_format:
            turns[-1]["content"] += "\n\nReply with one JSON object only."
        client = _STATE.setdefault("client", anthropic.Anthropic(max_retries=3, timeout=600))
        kw = dict(model=llm.model, max_tokens=8000, system="\n\n".join(system) or anthropic.NOT_GIVEN, messages=turns)
        t0 = time.time()
        resp = client.messages.create(**kw)                # no temperature: this SDK version takes none, so GraphTeam's 0.2 is not applied
        u = resp.usage
        cr, cw = getattr(u, "cache_read_input_tokens", 0) or 0, getattr(u, "cache_creation_input_tokens", 0) or 0
        pin, pout = LLM._PRICES.get(llm.model, (4.0, 20.0))
        cost = (u.input_tokens * pin + cr * pin * LLM._CACHE_READ.get(llm.model, 0.1) + cw * pin * 1.25 + u.output_tokens * pout) / 1e6
        llm.usage.add(Reply(text="", input_tokens=u.input_tokens, output_tokens=u.output_tokens, cache_read_tokens=cr, cache_write_tokens=cw, cost_usd=cost, seconds=time.time() - t0))
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=text))])


def _execute(self, code, lock):
    """In place of `docker exec graphteam python /root/execute_code.py`: the code as a script, same time limit."""
    out, err, rc, secs, _ = run_script(code, EXEC_TIMEOUT)
    _STATE["secs"] += secs; _STATE["runs"] += 1
    if rc == 124:
        return "Execution timed out"
    return "Success: " + out if rc == 0 else "Error: " + (err or out)[-3000:]


def _load(variant, store):
    """Import GraphTeam and put our three parts in place. Done once per process."""
    if _STATE.get("loaded"):
        return _STATE["loaded"]
    root = os.environ["T2A_GRAPHTEAM"]
    os.environ.setdefault("OPENAI_API_KEY", "unused")      # read at import; no call is made with it
    sys.path.insert(0, root)
    import camel.agents as agents
    import camel.model_backend as mb
    import graphteam.chat_chain as cc
    from camel.log import TaskLogger
    from camel.memory_configs import MemoryConfig
    from camel.rag_configs import RAGConfig
    mb.ModelFactory.create = staticmethod(lambda model_name, cfg: _Backend(model_name, cfg))
    agents.ExecuteAgent.execute_code = _execute
    if variant.endswith("nosearch"):
        agents.SearchAgent.generate_response = lambda self, messages, phase_env: ({"source": "none", "result": None}, phase_env)
    else:
        from llama_index.core import Settings
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        Settings.embed_model = HuggingFaceEmbedding(model_name=os.environ["T2A_GT_EMBED"])
        os.makedirs(store, exist_ok=True)                  # the two indexes are built here on first use, then loaded
        cc.RAGConfig = lambda: RAGConfig(persist_dir=os.path.join(store, "storage_docs"))
        agents.MemoryConfig = lambda: MemoryConfig(persist_dir=os.path.join(store, "storage_memory"))
    data = lambda *p: json.load(open(os.path.join(root, *p), encoding="utf-8"))  # noqa: E731
    cfg = os.path.join(root, "Config", "Default")
    _STATE["loaded"] = {"ChatChain": cc.ChatChain, "TaskLogger": TaskLogger,
                        "paths": [os.path.join(cfg, f) for f in ("ChatChainConfig.json", "PhaseConfig.json", "RoleConfig.json")],
                        "rag": data("data", "filtered_networkx_reference_edition.json"),
                        "memory_index": data("memory", "memory_index.json"), "memory": data("memory", "memory_info.json")}
    return _STATE["loaded"]


TASK = """{files}
{history}Question: {q}

Available libraries: networkx 3.x, igraph 1.0 (python-igraph), numpy, pandas. Prefer igraph for expensive algorithms on large graphs. Read the graph from the file path above.
Output format: print one JSON object and nothing else.{schema}"""


class GraphTeam:
    def __init__(self, spec, live, llm, variant, timeout):
        self.llm, self.variant, self.history, self.n = llm, variant, [], 0
        _STATE["llm"] = llm
        self.work = os.path.join(os.path.dirname(os.path.abspath(live)), "graphteam")
        self.gt = _load(variant, os.environ.get("T2A_GT_STORE") or os.path.join(self.work, "store"))
        fx = {k: v for k, v in asdict(read_facts(live)).items() if k != "sha1"}
        table = sidecar_node_table(live)
        self.files = (f"Graph file path: {os.path.abspath(live)}\nFile facts (read at the start of the session): {json.dumps(fx, default=str)}\n"
                      + (f"Node attribute table: {os.path.abspath(table)} (first rows, read at the start of the session):\n{head(table)}" if table else "Node attribute table: none.\n")
                      + f"Dataset description (from the user): {spec['description']}\n")
        self.lock = threading.Lock()

    def ask(self, q):
        self.n += 1
        _STATE["secs"], _STATE["runs"] = 0.0, 0
        history = "".join(f"Earlier question {i}: {hq}\nYour answer to it: {ha}\n" for i, (hq, ha) in enumerate(self.history, 1))
        question = TASK.format(files=self.files, history=("Earlier in this session:\n" + history + "\n") if history else "", q=q, schema=ANSWER_SCHEMA)
        gt, error, env = self.gt, None, {}
        logger = gt["TaskLogger"](f"turn{self.n}_{int(time.time())}", log_dir=os.path.join(self.work, "logs"))
        try:
            chain = gt["ChatChain"](config_path=gt["paths"][0], config_phase_path=gt["paths"][1], config_role_path=gt["paths"][2], question=question,
                                    model_name=self.llm.model, rag_data=gt["rag"], memory_index=gt["memory_index"], memory_data=gt["memory"], library=None)
            env = chain.chat_env.env_dict
            chain.make_recruitment()
            chain.execute_chain(self.lock, logger=logger)
        except Exception as e:  # noqa: BLE001  (a phase that could not read the model's reply, an API error): score what there is
            error = f"{type(e).__name__}: {str(e)[:300]}"
        finally:
            logger.close()
        out = env.get("Output")
        fin = None
        if out is not None:
            try:
                j = out if isinstance(out, dict) else parse_json(str(out))
                fin = j if isinstance(j, dict) and "answer" in j else {"answer": j}
            except Exception:  # noqa: BLE001  (free text): scored as it is
                fin = {"answer": str(out).strip()}
        answer = (fin or {}).get("answer")
        self.history.append((q, json.dumps(answer, default=str)[:1500]))
        search = env.get("Search_Result")
        flags = ([] if env.get("run") else ["not_from_code"]) + ([f"executions={_STATE['runs']}"] if _STATE["runs"] > 1 else []) + (["search_hit"] if search else [])
        return {"answer": answer, "asked": False, "error": None if fin else (error or "no output"), "execute_seconds": _STATE["secs"],
                "steps_reused": 0, "steps_executed": 0, "plan": str(env.get("Codes") or "")[-4000:], "flags": flags, "outcome": "answer"}

    def close(self):
        if os.path.exists("output.json"):                  # the coding phase writes its prompt to the working directory
            os.remove("output.json")
