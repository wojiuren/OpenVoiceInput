"""Build lightweight text context for API post-processing."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

from .usage_log import default_log_path


@dataclass(frozen=True)
class ApiContextPackage:
    enabled: bool
    mode: str
    recent_texts: tuple[str, ...] = ()
    glossary_terms: tuple[str, ...] = ()
    max_context_chars: int = 0
    used_chars: int = 0


def build_api_context_package(config, *, log_path: str | Path | None = None) -> ApiContextPackage:
    """Build a text-only context package from recent transcription logs and hotwords."""

    context = config.api_context
    if context.mode != "lightweight":
        return ApiContextPackage(enabled=False, mode=context.mode)

    budget = max(0, int(context.max_context_chars))
    glossary_terms = _fit_terms(
        config.hotwords.words if config.hotwords.enabled and context.glossary_enabled else (),
        budget,
    )
    used_chars = sum(len(term) for term in glossary_terms)
    remaining = max(0, budget - used_chars)
    recent_texts = read_recent_transcription_texts(
        log_path or default_log_path(),
        limit=max(0, int(context.recent_turns)),
        max_chars=remaining,
    )
    used_chars += sum(len(text) for text in recent_texts)
    return ApiContextPackage(
        enabled=True,
        mode=context.mode,
        recent_texts=recent_texts,
        glossary_terms=glossary_terms,
        max_context_chars=budget,
        used_chars=used_chars,
    )


def format_api_context_user_text(current_text: str, package: ApiContextPackage) -> str:
    """Wrap current text with optional glossary and recent text context for the API."""

    if not package.enabled or (not package.recent_texts and not package.glossary_terms):
        return current_text

    sections: list[str] = []
    if package.glossary_terms:
        glossary = "\n".join(f"- {term}" for term in package.glossary_terms)
        sections.append(f"术语表（优先使用这些写法）：\n{glossary}")
    if package.recent_texts:
        recent = "\n".join(f"{index}. {text}" for index, text in enumerate(package.recent_texts, start=1))
        sections.append(f"最近上下文（只用于消歧，不要混入当前输出）：\n{recent}")
    sections.append(f"当前文本：\n{current_text}")
    return "\n\n".join(sections)


def read_recent_transcription_texts(
    path: str | Path,
    *,
    limit: int,
    max_chars: int,
) -> tuple[str, ...]:
    """Read newest transcription texts from JSONL logs, skipping older entries without text."""

    if limit <= 0 or max_chars <= 0:
        return ()
    log_path = Path(path)
    if not log_path.exists():
        return ()

    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()

    texts: list[str] = []
    remaining = max_chars
    for line in reversed(lines):
        if len(texts) >= limit or remaining <= 0:
            break
        text = _text_from_log_line(line)
        if not text:
            continue
        fitted = _truncate_to_budget(text, remaining)
        if not fitted:
            continue
        texts.append(fitted)
        remaining -= len(fitted)
    return tuple(texts)


def _text_from_log_line(line: str) -> str:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    raw = data.get("text")
    if not isinstance(raw, str):
        return ""
    return _compact_text(raw)


def _fit_terms(terms: Sequence[str], budget: int) -> tuple[str, ...]:
    fitted: list[str] = []
    remaining = budget
    seen: set[str] = set()
    for term in terms:
        clean = _compact_text(term)
        if not clean or clean in seen:
            continue
        if len(clean) > remaining:
            break
        fitted.append(clean)
        seen.add(clean)
        remaining -= len(clean)
    return tuple(fitted)


def _compact_text(text: str) -> str:
    return " ".join(text.split())


def _truncate_to_budget(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    if budget <= 3:
        return text[:budget]
    return f"{text[: budget - 3].rstrip()}..."
