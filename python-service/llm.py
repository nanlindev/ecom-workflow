"""Sync DeepSeek/OpenAI JSON helper with deterministic fallbacks when key missing or LLM fails."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI

        _client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )
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
) -> tuple[dict[str, Any], bool]:
    """Return (parsed_json, fallback_used)."""
    client = _get_client()
    model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    if client is None:
        out = fallback()
        out["fallback_used"] = True
        return out, True
    try:
        resp = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        parsed = _extract_json(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM JSON root is not an object")
        parsed.setdefault("fallback_used", False)
        return parsed, bool(parsed.get("fallback_used"))
    except Exception as exc:
        logger.warning("LLM complete_json failed: %s", exc)
        out = fallback()
        out["fallback_used"] = True
        return out, True
