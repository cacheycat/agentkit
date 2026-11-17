"""LLM access with one contract: a tagged call that returns schema-shaped JSON.

Providers, picked by AGENT_LLM (auto | api | cli | baseline):
  api      - Anthropic SDK (needs credentials and `pip install anthropic`)
  cli      - headless `claude -p` with every tool disabled, for local development
  baseline - no model; each call site supplies a deterministic fallback

Every call site passes a `fallback`. It is used when no provider is configured
and when a provider fails twice, so a run degrades instead of crashing, and the
same fallback doubles as the non-LLM baseline the eval harness compares against.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any, Callable

DEFAULT_MODEL = os.environ.get("AGENT_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("AGENT_EFFORT", "medium")


class LLMError(RuntimeError):
    pass


def extract_json(text: str) -> Any:
    """Pull the first JSON value out of a model reply, fenced or bare."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise LLMError("model reply contained no JSON")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[min(starts):])
    except json.JSONDecodeError as e:
        raise LLMError(f"model reply was not valid JSON: {e}") from e
    return obj


def check_shape(obj: Any, schema: dict | None) -> None:
    """Cheap structural check: required top-level keys and their basic types."""
    if not schema:
        return
    if schema.get("type") == "object":
        if not isinstance(obj, dict):
            raise LLMError("expected a JSON object")
        types = {"string": str, "array": list, "object": dict, "boolean": bool,
                 "number": (int, float), "integer": int}
        for key in schema.get("required", []):
            if key not in obj:
                raise LLMError(f"missing required key '{key}'")
            want = schema.get("properties", {}).get(key, {}).get("type")
            value = obj[key]
            # bool is an int subclass in Python, but never a valid JSON number
            if want in ("number", "integer") and isinstance(value, bool):
                raise LLMError(f"key '{key}' should be {want}")
            if want in types and not isinstance(value, types[want]):
                raise LLMError(f"key '{key}' should be {want}")


class AnthropicAPI:
    name = "anthropic-api"

    def __init__(self, model: str | None = None):
        import anthropic  # imported lazily so the CLI path needs no SDK

        self._sdk = anthropic
        self.client = anthropic.Anthropic()
        self.model = model or DEFAULT_MODEL

    def complete(self, system: str, user: str, schema: dict | None) -> str:
        sdk = self._sdk
        output_config: dict = {"effort": EFFORT}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            # Server-side fallback: if a safety classifier declines, the API
            # re-runs the request on a fallback model inside the same call.
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except sdk.RateLimitError as e:
            raise LLMError("rate limited") from e
        except sdk.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except sdk.APIConnectionError as e:
            raise LLMError("network error reaching the API") from e
        if resp.stop_reason == "refusal":
            raise LLMError("request was declined")
        if resp.stop_reason == "max_tokens":
            raise LLMError("reply hit max_tokens")
        return next((b.text for b in resp.content if b.type == "text"), "")


class ClaudeCLI:
    """Headless Claude Code as a plain completion endpoint.

    The prompt goes in on stdin and every tool is switched off (`--tools ""`),
    so text that reaches the model can never turn into a shell command or a
    file read, whatever it says. Settings, MCP servers and session files are
    excluded so the call depends on nothing in the working directory.
    """

    name = "claude-cli"

    def __init__(self, model: str | None = None, timeout: int = 240):
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout
        self._cwd = tempfile.mkdtemp(prefix="agentkit-llm-")

    @staticmethod
    def available() -> bool:
        return shutil.which("claude") is not None

    def complete(self, system: str, user: str, schema: dict | None) -> str:
        if schema:
            system = (system + "\n\nReply with one JSON value and nothing else. "
                      "It must match this JSON Schema:\n" + json.dumps(schema))
        cmd = ["claude", "-p", "--model", self.model, "--tools", "",
               "--strict-mcp-config", "--setting-sources", "",
               "--no-session-persistence", "--output-format", "json",
               "--system-prompt", system]
        try:
            proc = subprocess.run(cmd, input=user, capture_output=True, text=True,
                                  timeout=self.timeout, cwd=self._cwd)
        except subprocess.TimeoutExpired as e:
            raise LLMError("claude CLI timed out") from e
        if proc.returncode != 0:
            raise LLMError(f"claude CLI failed: {proc.stderr.strip()[:300]}")
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise LLMError("claude CLI returned non-JSON output") from e
        if envelope.get("is_error"):
            raise LLMError(f"claude CLI error: {str(envelope.get('result'))[:300]}")
        return envelope.get("result") or ""


def pick_provider():
    mode = os.environ.get("AGENT_LLM", "auto").lower()
    if mode == "baseline":
        return None
    has_creds = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if mode == "api" or (mode == "auto" and has_creds):
        try:
            return AnthropicAPI()
        except Exception:
            if mode == "api":
                raise
    if mode in ("cli", "auto") and ClaudeCLI.available():
        return ClaudeCLI()
    return None


class LLM:
    def __init__(self, provider="auto", on_call: Callable[[dict], None] | None = None):
        self.provider = pick_provider() if provider == "auto" else provider
        self.on_call = on_call
        self.calls: list[dict] = []

    @property
    def mode(self) -> str:
        return self.provider.name if self.provider else "baseline"

    @property
    def model(self) -> str | None:
        return getattr(self.provider, "model", None)

    def json(self, tag: str, system: str, user: str, schema: dict,
             fallback: Callable[[], dict], on_call: Callable[[dict], None] | None = None) -> dict:
        """Run one tagged call. Returns the parsed object; never raises."""
        started = time.time()
        source, error, out = "baseline", None, None
        if self.provider:
            for _ in range(2):
                try:
                    out = extract_json(self.provider.complete(system, user, schema))
                    check_shape(out, schema)
                    source, error = self.provider.name, None
                    break
                except LLMError as e:
                    out, error = None, str(e)
        if out is None:
            out = fallback()
        record = {"tag": tag, "source": source, "ms": int((time.time() - started) * 1000),
                  "prompt_chars": len(system) + len(user), "error": error}
        self.calls.append(record)
        for cb in (on_call, self.on_call):
            if cb:
                cb(record)
        return out
