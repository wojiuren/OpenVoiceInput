"""JSONL usage log for local debugging and performance checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class TranscriptionLogEntry:
    command: str
    audio_path: str
    model_id: str
    language: str
    text_length: int
    text: str = ""
    elapsed_s: float | None = None
    copied_to_clipboard: bool = False
    pasted_to_active_window: bool = False
    restored_clipboard: bool = False
    clipboard_restore_format_count: int = 0
    clipboard_restore_skipped_format_count: int = 0
    text_path: str | None = None
    srt_path: str | None = None
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data["created_at"]:
            data["created_at"] = datetime.now(timezone.utc).isoformat()
        return data


def default_log_path() -> Path:
    return Path("captures") / "transcriptions.jsonl"


def append_transcription_log(
    entry: TranscriptionLogEntry,
    path: str | Path | None = None,
) -> Path:
    log_path = Path(path) if path else default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry.to_dict(), ensure_ascii=False))
        file.write("\n")
    return log_path


def entry_from_result(
    *,
    command: str,
    result,
    text_output,
    elapsed_s: float | None = None,
) -> TranscriptionLogEntry:
    metadata: Mapping[str, str] = result.metadata
    return TranscriptionLogEntry(
        command=command,
        audio_path=str(metadata.get("source_path", "")),
        model_id=result.model_id,
        language=result.language,
        text_length=len(result.text),
        text=result.text,
        elapsed_s=round(elapsed_s, 3) if elapsed_s is not None else None,
        copied_to_clipboard=text_output.copied_to_clipboard,
        pasted_to_active_window=text_output.pasted_to_active_window,
        restored_clipboard=text_output.restored_clipboard,
        clipboard_restore_format_count=text_output.clipboard_restore_format_count,
        clipboard_restore_skipped_format_count=text_output.clipboard_restore_skipped_format_count,
        text_path=str(text_output.text_path) if text_output.text_path else None,
        srt_path=str(text_output.srt_path) if text_output.srt_path else None,
    )
