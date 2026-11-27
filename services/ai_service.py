"""Gemini access with validated JSON output, retries and clear error types.

All AI calls in the project go through generate_structured(), so error handling lives in one place.
"""
from __future__ import annotations

import re
import time
from typing import TypeVar

from pydantic import BaseModel, ValidationError

import config

T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    """Base class for AI problems. The agent catches this and falls back to rule-based logic."""


class AIUnavailableError(AIError):
    """No key, bad key, unknown model or SDK missing."""


class AIQuotaError(AIError):
    """Rate limit or quota exhausted."""


class AIOutputError(AIError):
    """The model answered, but not with valid JSON for our schema."""


# After a quota/auth failure we stop calling the API for the rest of the run (saves time).
_circuit_reason: str | None = None


def reset_circuit() -> None:
    global _circuit_reason
    _circuit_reason = None


def is_available() -> bool:
    return config.ai_configured() and _circuit_reason is None


def _call_model(prompt: str, system: str | None, schema: type[BaseModel]) -> str:
    """The only function that touches the Gemini SDK (tests replace it)."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.get_api_key())
    kwargs = dict(system_instruction=system, temperature=0.2, response_mime_type="application/json")
    try:
        cfg = types.GenerateContentConfig(response_schema=schema, **kwargs)
        response = client.models.generate_content(model=config.get_model(), contents=prompt, config=cfg)
    except (TypeError, ValueError):
        # Schema conversion not supported by this SDK/model: ask for JSON in the prompt instead.
        hint = f"\n\nReturn ONLY JSON matching this JSON schema:\n{schema.model_json_schema()}"
        cfg = types.GenerateContentConfig(**kwargs)
        response = client.models.generate_content(model=config.get_model(), contents=prompt + hint, config=cfg)
    return response.text or ""


def _classify(exc: Exception) -> tuple[AIError, bool]:
    """Turn an SDK exception into one of our errors. Second value: True = permanent (stop retrying)."""
    text = f"{type(exc).__name__} {exc}"
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    lowered = text.lower()
    if isinstance(exc, ImportError):
        return AIUnavailableError("The google-genai package is not installed."), True
    if code == 429 or "resource_exhausted" in lowered or "quota" in lowered or "rate limit" in lowered:
        return AIQuotaError("Gemini rate limit or quota reached. Wait a bit or check your quota."), True
    if code in (401, 403) or "api key" in lowered or "api_key" in lowered or "permission_denied" in lowered:
        return AIUnavailableError("Gemini rejected the API key. Check GEMINI_API_KEY in .env."), True
    if code == 404 or "not found" in lowered:
        return AIUnavailableError(f"Gemini model '{config.get_model()}' was not found. Check GEMINI_MODEL in .env."), True
    return AIError(f"Could not reach Gemini ({type(exc).__name__}). Check your internet connection."), False


def _strip_fences(raw: str) -> str:
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)


def generate_structured(prompt: str, schema: type[T], system: str | None = None, max_attempts: int = 2) -> T:
    """Ask Gemini for JSON and return a validated Pydantic object, or raise an AIError."""
    global _circuit_reason
    if not config.ai_configured():
        raise AIUnavailableError("GEMINI_API_KEY is not configured.")
    if _circuit_reason:
        raise AIUnavailableError(f"AI skipped after earlier failure: {_circuit_reason}")

    last_error: AIError = AIError("Unknown AI failure.")
    for attempt in range(max_attempts):
        try:
            raw = _call_model(prompt, system, schema)
        except Exception as exc:  # SDK errors vary by version, so classify them ourselves
            error, permanent = _classify(exc)
            if permanent:
                _circuit_reason = str(error)
                raise error from exc
            last_error = error
            if attempt + 1 < max_attempts:
                time.sleep(1.5)
            continue
        try:
            return schema.model_validate_json(_strip_fences(raw))
        except (ValidationError, ValueError) as exc:
            last_error = AIOutputError(f"Gemini returned invalid JSON for {schema.__name__}.")
            prompt += "\n\nYour previous answer was invalid. Return ONLY valid JSON that matches the schema."
    raise last_error
