"""Lets Claude Code subagents answer the model calls, through files, instead of the Claude API.
Replay: a call with no answer file yet writes a request file and stops the run; rerun after the answers exist."""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)

MAX_ATTEMPTS = 3

_lock = threading.RLock()
_run_dir: Path | None = None
_pending: dict[str, dict] = {}


class NeedsAnswer(Exception):
    """Some model calls have no answer yet. Their requests are in pending()."""


def start(run_dir: Path) -> None:
    """Begin one replay round in `run_dir`. Answers already there are reused; new requests are collected."""
    global _run_dir
    with _lock:
        _run_dir = run_dir
        _pending.clear()
    (run_dir / "requests").mkdir(parents=True, exist_ok=True)
    (run_dir / "answers").mkdir(parents=True, exist_ok=True)


def pending() -> list[dict]:
    with _lock:
        return sorted(_pending.values(), key=lambda r: r["id"])


def agent_model(model: str) -> str:
    """The Claude Code model name closest to an API model id (what the Agent tool's `model` accepts)."""
    for name in ("opus", "sonnet", "haiku", "fable"):
        if name in model:
            return name
    return "sonnet"


def _key(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _loads(text: str) -> Any:
    start_at, end_at = text.find("{"), text.rfind("}")
    if start_at < 0 or end_at <= start_at:
        raise ValueError("no JSON object found in the answer")
    return json.loads(text[start_at : end_at + 1])


def _ask(*, key: str, kind: str, model: str, effort: str, system: str, user: str, schema: type[BaseModel] | None, searches: int, error: str, attempts: int) -> None:
    """Write the request for one call and stop the run."""
    assert _run_dir is not None, "subagent_runner.start() was not called"
    answer = _run_dir / "answers" / f"{key}.{'json' if schema else 'txt'}"
    if schema:
        how = (
            "Write ONE JSON object, with no code fence and no commentary, that follows this JSON Schema:\n\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
    else:
        how = "Write the full answer as plain text, exactly in the format the SYSTEM section asks for."
        if searches:
            how += f" You may search the web (at most {searches} searches)."
    prompt = "\n".join(
        [
            "# One step of a pipeline",
            "",
            "Do what the SYSTEM section says, using only the USER section as your input.",
            "Do not read any other file and do not look at other steps. Your answer is judged on its own.",
            f"Write your answer, and nothing else, to this file: {answer}",
            "",
            how,
            *(["", f"Your previous answer was rejected. Fix this and answer again: {error}"] if error else []),
            "",
            "## SYSTEM",
            "",
            system,
            "",
            "## USER",
            "",
            user,
            "",
        ]
    )
    prompt_file = _run_dir / "requests" / f"{key}.md"
    prompt_file.write_text(prompt, "utf8")
    request = {
        "id": key,
        "kind": kind,
        "schema": schema.__name__ if schema else None,
        "agentModel": agent_model(model),
        "model": model,
        "effort": effort,
        "promptFile": str(prompt_file),
        "answerFile": str(answer),
        "attempts": attempts,
        "error": error,
    }
    (_run_dir / "requests" / f"{key}.json").write_text(json.dumps(request, ensure_ascii=False, indent=1), "utf8")
    with _lock:
        _pending[key] = request
    raise NeedsAnswer(key)


def _attempts_so_far(key: str) -> int:
    assert _run_dir is not None
    return len(list((_run_dir / "answers").glob(f"{key}.bad-*")))


def _read(key: str, schema: type[T] | None) -> Any:
    """The answer for `key` if a valid one exists, else None. A bad answer is set aside, with its reason."""
    assert _run_dir is not None
    path = _run_dir / "answers" / f"{key}.{'json' if schema else 'txt'}"
    if not path.exists():
        return None, ""
    raw = path.read_text("utf8")
    if schema is None:
        return (raw, "") if raw.strip() else (None, "the answer file is empty")
    try:
        return schema.model_validate(_loads(raw)), ""
    except (ValueError, ValidationError) as err:
        path.rename(path.with_name(f"{key}.bad-{_attempts_so_far(key) + 1}.json"))
        return None, str(err)[:600]


def run_json(*, schema: type[T], model: str, system: str, user: str, effort: str) -> T:
    key = _key("json", model, effort, schema.__name__, system, user)
    value, error = _read(key, schema)
    if value is not None:
        return value
    attempts = _attempts_so_far(key)
    if attempts >= MAX_ATTEMPTS:
        from .model_client import AgentError  # here, not at the top: model_client imports this module

        raise AgentError(f"Subagent answer {key} failed validation {attempts} times: {error}")
    _ask(key=key, kind="json", model=model, effort=effort, system=system, user=user, schema=schema, searches=0, error=error, attempts=attempts)


def run_text(*, system: str, user: str, max_searches: int) -> str:
    from .config import MAIN_MODEL

    key = _key("text", MAIN_MODEL, max_searches, system, user)
    value, error = _read(key, None)
    if value is not None:
        return value
    _ask(key=key, kind="text", model=MAIN_MODEL, effort="medium", system=system, user=user, schema=None, searches=max_searches, error=error, attempts=0)
