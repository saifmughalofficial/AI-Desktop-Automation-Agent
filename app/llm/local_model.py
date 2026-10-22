"""Optional local language-model backends: Ollama and llama.cpp (llama-server).

Only localhost endpoints are accepted, so no request ever leaves the machine and
no API key is needed. The model may only *propose* steps in the strict JSON
schema; every step is re-validated and then checked by the policy engine."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from app.config.settings import LLMSettings
from app.core.action_schema import parse_step_payload

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LocalModelError(Exception):
    pass


class ModelUnavailable(LocalModelError):
    pass


class ModelOutputError(LocalModelError):
    pass


def check_local_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a URL like http://127.0.0.1:11434")
    if parsed.hostname.lower() not in LOCAL_HOSTS:
        raise ValueError("Only local model servers (localhost / 127.0.0.1) are allowed — no external API calls.")
    return url.rstrip("/")


_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never route localhost via a proxy


def _http(url: str, payload: dict | None, timeout: float) -> dict:
    check_local_url(url)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if data else "GET")
    try:
        with _NO_PROXY.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except TimeoutError as exc:
        raise ModelUnavailable(f"timed out after {timeout:.0f}s") from exc
    except urllib.error.HTTPError as exc:
        raise ModelUnavailable(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ModelUnavailable(f"not reachable at {url}") from exc
    except json.JSONDecodeError as exc:
        raise ModelUnavailable("server returned non-JSON") from exc


class ModelProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")
    clarification: str | None = None
    dry_run: bool = False
    assumptions: list[str] = Field(default_factory=list, max_length=20)
    steps: list[dict] = Field(default_factory=list, max_length=100)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of model text (tolerates ``` fences and chatter)."""
    if not text or not text.strip():
        raise ModelOutputError("the model returned an empty response")
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    if start < 0:
        raise ModelOutputError("the model response contained no JSON object")
    depth = 0
    in_str = esc = False
    for i, ch in enumerate(cleaned[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(cleaned[start:i + 1])
                except json.JSONDecodeError as exc:
                    raise ModelOutputError(f"malformed JSON from the model: {exc.msg}") from exc
                if not isinstance(obj, dict):
                    raise ModelOutputError("the model JSON must be an object")
                return obj
    raise ModelOutputError("the model JSON object was not closed")


def validate_proposal(obj: dict) -> tuple[ModelProposal, list]:
    try:
        proposal = ModelProposal.model_validate(obj)
    except ValueError as exc:
        raise ModelOutputError(f"the model plan does not match the schema: {exc}") from exc
    items = []
    for i, step in enumerate(proposal.steps, 1):
        try:
            items.append(parse_step_payload(step))
        except ValueError as exc:
            msg = str(exc).splitlines()[0][:200]
            raise ModelOutputError(f"step {i} from the model was rejected: {msg}") from exc
    if not items and not proposal.clarification:
        raise ModelOutputError("the model produced no steps and no clarifying question")
    return proposal, items


SYSTEM_PROMPT = """You translate a user's request into JSON for a SAFE desktop automation agent.
Reply with ONE JSON object and nothing else:
{"clarification": null or "short question", "dry_run": false, "assumptions": ["..."], "steps": [STEP, ...]}

Every path is {"root": ALIAS, "path": "relative/path"} — relative to an approved folder. Never use absolute paths or "..".
Allowed STEP shapes (no other keys, no other actions):
{"action":"list_files","target":PATH,"extensions":["pdf"],"name_pattern":null,"recursive":false}
{"action":"find_duplicates","target":PATH,"recursive":true}
{"action":"create_folder","target":PATH}
{"action":"copy_file","source":PATH,"destination":FOLDER_PATH,"new_name":null}
{"action":"move_file","source":PATH,"destination":FOLDER_PATH,"new_name":null}
{"action":"rename_file","source":PATH,"new_name":"new.txt"}
{"action":"delete_file","target":PATH}
{"action":"write_text_file","target":PATH_ENDING_.txt,"content":"..."}
{"action":"archive_folder","target":FOLDER_PATH,"destination":PATH_ENDING_.zip}
{"action":"launch_app","app":"Notepad"}
{"action":"open_file","target":PATH}
{"action":"open_folder","target":FOLDER_PATH}
{"action":"inspect_ui","app":"Notepad"}
{"action":"type_text","app":"Notepad","text":"..."}   (always put launch_app for that app first)
{"macro":"organize_by_type","target":FOLDER_PATH}
{"macro":"bulk_rename","target":FOLDER_PATH,"extensions":["jpg"],"prefix":"Event_","suffix":"","base_name":null}
{"macro":"bulk_transfer","operation":"copy","source":FOLDER_PATH,"extensions":["pdf"],"destination":FOLDER_PATH}
Rules: if the request is ambiguous, ask via "clarification" and return no steps. If the user wants a preview or
says not to change anything yet, set "dry_run": true. Never invent actions, apps or folders that are not listed."""


class LocalModelClient:
    def __init__(self, cfg: LLMSettings):
        self.cfg = cfg
        self._status_cache: tuple[float, dict] | None = None

    def backends(self) -> list[str]:
        return {"auto": ["ollama", "llamacpp"], "ollama": ["ollama"], "llamacpp": ["llamacpp"]}.get(self.cfg.mode, [])

    def _probe(self, backend: str) -> dict:
        try:
            if backend == "ollama":
                data = _http(f"{check_local_url(self.cfg.ollama_url)}/api/tags", None, 1.5)
                models = [m.get("name", "") for m in data.get("models", [])]
                wanted = self.cfg.ollama_model
                has = any(m == wanted or m.split(":")[0] == wanted.split(":")[0] for m in models)
                if not has:
                    return {"backend": backend, "available": False, "models": models,
                            "detail": f"Ollama is running but model '{wanted}' is not pulled "
                                      f"(run: ollama pull {wanted})."}
                return {"backend": backend, "available": True, "models": models, "model": wanted,
                        "detail": f"Ollama online · {wanted}"}
            base = check_local_url(self.cfg.llamacpp_url)
            data = _http(f"{base}/v1/models", None, 1.5)
            models = [m.get("id", "") for m in data.get("data", [])]
            return {"backend": backend, "available": True, "models": models, "model": (models or ["local"])[0],
                    "detail": f"llama.cpp server online · {(models or ['model'])[0]}"}
        except (ModelUnavailable, ValueError) as exc:
            name = "Ollama" if backend == "ollama" else "llama.cpp server"
            return {"backend": backend, "available": False, "models": [], "detail": f"{name} {exc}"}

    def status(self, max_age: float = 20.0) -> dict:
        if self.cfg.mode == "rules":
            return {"backend": None, "available": False, "models": [], "detail": "Rules-only mode (no model)."}
        if self._status_cache and time.monotonic() - self._status_cache[0] < max_age:
            return self._status_cache[1]
        result = None
        for backend in self.backends():
            result = self._probe(backend)
            if result["available"]:
                break
        if result and not result["available"] and self.cfg.mode == "auto":
            result = dict(result, detail="Ollama / llama.cpp not detected")
        self._status_cache = (time.monotonic(), result)
        return result

    def _complete(self, backend: str, user_prompt: str) -> str:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
        if backend == "ollama":
            data = _http(f"{check_local_url(self.cfg.ollama_url)}/api/chat",
                         {"model": self.cfg.ollama_model, "messages": messages, "stream": False, "format": "json",
                          "options": {"temperature": 0}}, self.cfg.timeout_s)
            return (data.get("message") or {}).get("content", "")
        data = _http(f"{check_local_url(self.cfg.llamacpp_url)}/v1/chat/completions",
                     {"messages": messages, "temperature": 0, "response_format": {"type": "json_object"}},
                     self.cfg.timeout_s)
        return ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")

    def propose(self, request: str, context: str) -> tuple[ModelProposal, list, str]:
        st = self.status()
        if not st or not st.get("available"):
            raise ModelUnavailable((st or {}).get("detail", "no local model configured"))
        prompt = f"{context}\n\nUser request: {request}"
        raw = self._complete(st["backend"], prompt)
        proposal, items = validate_proposal(extract_json(raw))
        return proposal, items, f"{st['backend']}:{st.get('model', '')}"
