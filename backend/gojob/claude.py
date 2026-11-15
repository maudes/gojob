"""The only module that talks to the Claude API."""
from __future__ import annotations

from typing import Literal, TypeVar

import anthropic
from pydantic import BaseModel

from .config import MAIN_MODEL, has_credentials

__all__ = ["AgentError", "has_credentials", "run_json", "run_with_search"]

Effort = Literal["low", "medium", "high"]
T = TypeVar("T", bound=BaseModel)


class AgentError(Exception):
    """A problem the user can act on. The API layer shows the message as is."""


_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _explain(err: Exception) -> AgentError:
    if isinstance(err, AgentError):
        return err
    if isinstance(err, anthropic.AuthenticationError):
        return AgentError("The API key was rejected. Check ANTHROPIC_API_KEY in .env.local.")
    if isinstance(err, anthropic.RateLimitError):
        return AgentError("Rate limited by the Claude API. Wait a minute and retry.")
    if isinstance(err, anthropic.APIConnectionError):
        return AgentError("Could not reach the Claude API. Check your connection.")
    if isinstance(err, anthropic.APIStatusError):
        return AgentError(f"Claude API error {err.status_code}: {err.message}")
    raise err


def run_json(*, schema: type[T], model: str, system: str, user: str, effort: Effort) -> T:
    """One structured call. Current Claude models reject a `temperature` parameter, so
    determinism for reviewers comes from low effort plus a strict schema instead."""
    try:
        response = _get_client().messages.parse(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": effort},
        )
    except Exception as err:  # noqa: BLE001 - translated for the user below
        raise _explain(err) from err
    if response.stop_reason == "refusal":
        raise AgentError("The model declined this request.")
    if response.stop_reason == "max_tokens":
        raise AgentError("The answer was cut off before it finished. Retry.")
    if response.parsed_output is None:
        raise AgentError("The model returned output that did not match the expected structure.")
    return response.parsed_output


def run_with_search(*, system: str, user: str, max_searches: int, max_tokens: int) -> str:
    """A long free-text call that may search the web. Returns the concatenated text."""
    try:
        messages: list[dict] = [{"role": "user", "content": user}]
        for _ in range(6):
            with _get_client().messages.stream(
                model=MAIN_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}],
                output_config={"effort": "medium"},
            ) as stream:
                message = stream.get_final_message()
            if message.stop_reason == "refusal":
                raise AgentError("The model declined this request.")
            if message.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": message.content})
                continue
            if message.stop_reason == "max_tokens":
                raise AgentError("The answer was cut off before it finished. Retry.")
            return "".join(b.text for b in message.content if b.type == "text")
        raise AgentError("The research run did not finish. Retry.")
    except Exception as err:  # noqa: BLE001
        raise _explain(err) from err
