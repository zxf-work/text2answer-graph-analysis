"""LLM client with two backends.

- "sdk": the official Anthropic Python SDK (used when ANTHROPIC_API_KEY or an `ant auth` profile exists).
- "cli": `claude -p` headless mode, which is the only authenticated path inside a Claude Code cloud session.

Both return the same Reply record so the rest of the prototype does not care which backend ran.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Optional

DEFAULT_MODEL = os.environ.get("T2R_MODEL", "claude-haiku-5-5")   # 122 of 122 on the E2b sessions at about 3% of the Opus bill


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    backend: str = ""
    raw: Any = None


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0

    def add(self, r: Reply) -> None:
        self.calls += 1
        self.input_tokens += r.input_tokens + r.cache_read_tokens + r.cache_write_tokens      # everything the model read
        self.cache_read_tokens += r.cache_read_tokens
        self.cache_write_tokens += r.cache_write_tokens
        self.output_tokens += r.output_tokens
        self.cost_usd += r.cost_usd
        self.seconds += r.seconds


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, backend: Optional[str] = None, effort: str = "medium"):
        self.model = model
        self.effort = effort
        self.backend = backend or self._detect()
        self.usage = Usage()
        self._sdk = None
        if self.backend == "sdk":
            import anthropic  # type: ignore
            self._sdk = anthropic.Anthropic()

    @staticmethod
    def _detect() -> str:
        if os.environ.get("T2R_BASE_URL"):
            return "openai"          # a locally served open model behind an OpenAI-compatible endpoint (Ollama, vLLM)
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # noqa: F401
                return "sdk"
            except ImportError:
                pass
        return "cli"

    def chat(self, system: str, user: str, max_tokens: int = 8000, fixed_system: str = "", fixed_user: Any = "") -> Reply:
        """fixed_system / fixed_user are the parts that stay the same from turn to turn (the operator catalogue, the profile
        card). They are sent first; with T2R_PROMPT_CACHE=1 the API path marks them as cache breakpoints, so later turns
        read them at the cache-read price. Without the switch, or on other backends, they are simply prepended.
        fixed_user may be a list of strings for a prefix that grows by one piece per turn (a conversation history): each
        piece is its own block and the breakpoint sits on the last, so the next turn reads everything up to it from cache."""
        t0 = time.time()
        parts = [x for x in ([fixed_user] if isinstance(fixed_user, str) else list(fixed_user)) if x]
        fixed_user = "".join(parts)
        if self.backend == "sdk" and os.environ.get("T2R_PROMPT_CACHE") == "1" and (fixed_system or fixed_user):
            r = self._chat_sdk(system, user, max_tokens, fixed_system, parts)
        elif self.backend == "sdk":
            r = self._chat_sdk(fixed_system + system, fixed_user + user, max_tokens)
        elif fixed_system or fixed_user:
            return self.chat(fixed_system + system, fixed_user + user, max_tokens)
        elif self.backend == "openai":
            r = self._chat_openai(system, user, max_tokens)
        else:
            r = self._chat_cli(system, user)
        r.seconds = time.time() - t0
        r.backend = self.backend
        self.usage.add(r)
        return r

    # price table for the CLI path, which does not always report cost: $/MTok input, output
    _PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}

    # cache read price as a share of the input price; a 5-minute cache write costs 1.25x the input price
    _CACHE_READ = {"claude-opus-5-5": 0.05, "claude-sonnet-5-5": 0.05}

    def _chat_sdk(self, system: str, user: str, max_tokens: int, fixed_system: str = "", fixed_user: Any = ()) -> Reply:
        mark = {"cache_control": {"type": "ephemeral"}}
        sys_blocks = ([{"type": "text", "text": fixed_system, **mark}] if fixed_system else []) + ([{"type": "text", "text": system}] if system else [])
        usr_blocks = [{"type": "text", "text": x} for x in fixed_user]
        if usr_blocks:
            usr_blocks[-1].update(mark)
        usr_blocks.append({"type": "text", "text": user})
        resp = self._sdk.messages.create(
            model=self.model, max_tokens=max_tokens, system=sys_blocks if fixed_system else system,
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": usr_blocks if fixed_user else user}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        u = resp.usage
        pin, pout = self._PRICES.get(self.model, (4.0, 20.0))
        cr = getattr(u, "cache_read_input_tokens", 0) or 0
        cw = getattr(u, "cache_creation_input_tokens", 0) or 0
        cost = (u.input_tokens * pin + cr * pin * self._CACHE_READ.get(self.model, 0.1) + cw * pin * 1.25 + u.output_tokens * pout) / 1e6
        return Reply(text=text, input_tokens=u.input_tokens, output_tokens=u.output_tokens, cache_read_tokens=cr, cache_write_tokens=cw, cost_usd=cost, raw=resp.model_dump() if hasattr(resp, "model_dump") else None)

    def _chat_openai(self, system: str, user: str, max_tokens: int) -> Reply:
        """POST <T2R_BASE_URL>/v1/chat/completions. No price: the model runs on our own hardware. Reasoning that a model
        writes inside <think> tags is dropped from the text (its tokens still count as output)."""
        import urllib.request
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": float(os.environ.get("T2R_TEMPERATURE", "0")),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if os.environ.get("T2R_SEED"):
            body["seed"] = int(os.environ["T2R_SEED"])              # for repetitions at a temperature above 0
        if os.environ.get("T2R_JSON_MODE") == "1":
            body["response_format"] = {"type": "json_object"}       # constrained decoding where the server supports it
        req = urllib.request.Request(os.environ["T2R_BASE_URL"].rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("T2R_API_KEY", "none")})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=float(os.environ.get("T2R_LLM_TIMEOUT", "1800"))) as f:
                    d = json.loads(f.read())
                break
            except Exception:  # noqa: BLE001
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        text = d["choices"][0]["message"].get("content") or ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        u = d.get("usage") or {}
        return Reply(text=text, input_tokens=int(u.get("prompt_tokens", 0)), output_tokens=int(u.get("completion_tokens", 0)), raw=d)

    def _chat_cli(self, system: str, user: str) -> Reply:
        cmd = ["claude", "-p", "--output-format", "json", "--model", self.model, "--system-prompt", system,
               "--tools", "", "--max-turns", "1", "--no-session-persistence"]
        env = dict(os.environ)
        env.pop("CLAUDECODE", None)  # allow nesting
        for attempt in range(3):
            p = subprocess.run(cmd, input=user, capture_output=True, text=True, env=env, timeout=600)
            try:
                d = json.loads(p.stdout)
                break
            except json.JSONDecodeError:
                if attempt == 2:
                    raise RuntimeError(f"claude cli failed: rc={p.returncode} stderr={p.stderr[-500:]} stdout={p.stdout[-500:]}")
                time.sleep(2 * (attempt + 1))
        u = d.get("usage", {})
        return Reply(text=d.get("result", ""), input_tokens=u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0),
                     output_tokens=u.get("output_tokens", 0), cache_read_tokens=u.get("cache_read_input_tokens", 0),
                     cost_usd=float(d.get("total_cost_usd", 0.0)), raw=d)


def parse_json(text: str) -> Any:
    """Extract the first JSON object from a model reply (tolerates ```json fences and prose)."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        i = text.find("{")
        if i >= 0:
            # find matching brace
            depth = 0
            for j in range(i, len(text)):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        text = text[i:j + 1]
                        break
    return json.loads(text)
