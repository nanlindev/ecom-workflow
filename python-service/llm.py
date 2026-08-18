"""Sync DeepSeek/OpenAI JSON helper with deterministic fallbacks when key missing or LLM fails."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_client = None
_langfuse_wrapped = False


def _langfuse_enabled() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    )


def _get_client():
    """OpenAI-compatible client. Uses langfuse.openai when Langfuse keys are set."""
    global _client, _langfuse_wrapped
    if _client is not None:
        return _client
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    kwargs = {
        "api_key": api_key,
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
    }
    try:
        if _langfuse_enabled():
            from langfuse.openai import OpenAI as LangfuseOpenAI

            _client = LangfuseOpenAI(**kwargs)
            _langfuse_wrapped = True
        else:
            from openai import OpenAI

            _client = OpenAI(**kwargs)
            _langfuse_wrapped = False
        return _client
    except Exception as exc:
        logger.warning("OpenAI client init failed: %s", exc)
        return None


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def complete_json(
    *,
    system: str,
    user: str,
    model: str | None = None,
    fallback: Callable[[], dict[str, Any]],
    operation: str = "ecom-llm",
) -> tuple[dict[str, Any], bool]:
    """Return (parsed_json, fallback_used). Langfuse generations go to sidecar keys, not collector."""
    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if client is None:
        out = fallback()
        out["fallback_used"] = True
        return out, True

    def _call() -> tuple[dict[str, Any], bool]:
        create_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        if _langfuse_wrapped:
            create_kwargs["name"] = operation
            create_kwargs["metadata"] = {"operation": operation, "tags": ["ecom-workflow"]}
        resp = client.chat.completions.create(**create_kwargs)
        content = resp.choices[0].message.content or ""
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON root is not an object")
        parsed.setdefault("fallback_used", False)
        return parsed, bool(parsed.get("fallback_used"))

    try:
        if _langfuse_wrapped:
            from langfuse import get_client, propagate_attributes

            lf = get_client()
            with lf.start_as_current_observation(
                as_type="span",
                name=operation,
                input={"system_preview": system[:300], "user_preview": user[:500]},
            ):
                with propagate_attributes(tags=["ecom-workflow"]):
                    result = _call()
            try:
                lf.flush()
            except Exception:
                logger.debug("Langfuse flush skipped", exc_info=True)
            return result
        return _call()
    except Exception as exc:
        logger.warning("LLM complete_json failed: %s", exc)
        out = fallback()
        out["fallback_used"] = True
        return out, True
