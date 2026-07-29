"""Load versioned prompt markdown files with frontmatter."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "")) if os.getenv("PROMPTS_DIR") else None

if not PROMPTS_DIR or not PROMPTS_DIR.exists():
    for candidate in (Path("/app/prompts"), Path(__file__).resolve().parent.parent / "prompts"):
        if candidate.exists():
            PROMPTS_DIR = candidate
            break
    else:
        PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@dataclass(frozen=True)
class PromptTemplate:
    key: str
    version: str
    model: str
    output_format: str
    body: str
    file_path: str

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:16]

    def render(self, **kwargs: str) -> str:
        result = self.body
        for key, value in kwargs.items():
            result = result.replace("{" + key + "}", str(value or ""))
        return result


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(text.strip())
    if not match:
        return {}, text.strip()
    meta_block, body = match.group(1), match.group(2).strip()
    meta: dict[str, str] = {}
    for line in meta_block.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, body


def load_prompt(key: str) -> PromptTemplate:
    file_path = PROMPTS_DIR / f"{key}.md"
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    raw = file_path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw)
    return PromptTemplate(
        key=key,
        version=meta.get("version", f"{key}-unknown"),
        model=meta.get("model", "deepseek-chat"),
        output_format=meta.get("output_format", "json"),
        body=body,
        file_path=str(file_path.relative_to(PROMPTS_DIR.parent)),
    )


def list_prompts() -> list[str]:
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
