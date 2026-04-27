"""Keyword-routed quick note saving."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from .config import QuickCaptureConfig, QuickCaptureRule


_LEADING_SEPARATORS = " \t\r\n:：,，.。;；、-—"


@dataclass(frozen=True)
class QuickNoteMatch:
    rule: QuickCaptureRule | None
    keyword: str | None
    keyword_start: int | None
    target_dir: Path

    @property
    def matched(self) -> bool:
        return self.rule is not None


@dataclass(frozen=True)
class QuickNoteResult:
    original_text: str
    saved_text: str
    path: Path
    matched_rule: str | None = None
    matched_keyword: str | None = None
    removed_keyword: bool = False


def find_quick_note_match(text: str, config: QuickCaptureConfig) -> QuickNoteMatch:
    """Find the first keyword close to the start of recognized text."""

    leading_text = text.lstrip()
    trim_offset = len(text) - len(leading_text)
    best: tuple[int, int, int, QuickCaptureRule, str] | None = None

    for rule_index, rule in enumerate(config.rules):
        window = rule.match_window_chars
        if window is None:
            window = config.match_window_chars
        for keyword in rule.keywords:
            if not keyword:
                continue
            index = leading_text.find(keyword)
            if index < 0 or index > window:
                continue
            candidate = (index, -len(keyword), rule_index, rule, keyword)
            if best is None or candidate[:3] < best[:3]:
                best = candidate

    if best is None:
        return QuickNoteMatch(
            rule=None,
            keyword=None,
            keyword_start=None,
            target_dir=_resolve_note_dir(config.root_dir, config.inbox_dir),
        )

    index, _negative_length, _rule_index, rule, keyword = best
    return QuickNoteMatch(
        rule=rule,
        keyword=keyword,
        keyword_start=trim_offset + index,
        target_dir=_resolve_note_dir(config.root_dir, rule.target_dir),
    )


def save_quick_note(
    text: str,
    config: QuickCaptureConfig,
    *,
    now: datetime | None = None,
    route_text: str | None = None,
) -> QuickNoteResult:
    original_text = route_text if route_text is not None else text
    match = find_quick_note_match(original_text, config)
    remove_keyword = False
    saved_text = text.strip()

    if match.rule is not None and match.keyword is not None and match.keyword_start is not None:
        remove_setting = match.rule.remove_keyword
        remove_keyword = config.remove_keyword if remove_setting is None else remove_setting
        if remove_keyword:
            if route_text is None:
                saved_text = text[match.keyword_start + len(match.keyword) :].lstrip(_LEADING_SEPARATORS).strip()
            else:
                saved_text = _remove_keyword_prefix_if_present(
                    text,
                    match.keyword,
                    match.rule.match_window_chars
                    if match.rule.match_window_chars is not None
                    else config.match_window_chars,
                )

    target_dir = match.target_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = _unique_note_path(
        target_dir,
        rule_name=match.rule.name if match.rule else "inbox",
        now=now or datetime.now(),
    )
    path.write_text(saved_text, encoding="utf-8")
    return QuickNoteResult(
        original_text=original_text,
        saved_text=saved_text,
        path=path,
        matched_rule=match.rule.name if match.rule else None,
        matched_keyword=match.keyword,
        removed_keyword=remove_keyword,
    )


def _remove_keyword_prefix_if_present(text: str, keyword: str, match_window_chars: int) -> str:
    leading_text = text.lstrip()
    trim_offset = len(text) - len(leading_text)
    index = leading_text.find(keyword)
    if index < 0 or index > match_window_chars:
        return text.strip()
    start = trim_offset + index + len(keyword)
    return text[start:].lstrip(_LEADING_SEPARATORS).strip()


def _resolve_note_dir(root_dir: str, configured_dir: str) -> Path:
    root = Path(root_dir)
    directory = Path(configured_dir)
    if directory.is_absolute():
        return directory
    if directory.parts and root.name and directory.parts[0].lower() == root.name.lower():
        return directory
    return root / directory


def _unique_note_path(target_dir: Path, *, rule_name: str, now: datetime) -> Path:
    safe_rule = _safe_name(rule_name or "note")
    stamp = now.strftime("%Y%m%d-%H%M%S")
    base = target_dir / f"{stamp}-{safe_rule}.txt"
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = target_dir / f"{stamp}-{safe_rule}-{index:03d}.txt"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"too many quick notes already exist for timestamp {stamp}")


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return safe.strip("-") or "note"
