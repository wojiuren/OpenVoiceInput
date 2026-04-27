"""Subtitle formatting helpers."""

from __future__ import annotations

from pathlib import Path

from .asr import TranscriptionResult, TranscriptionSegment


def write_srt_file(result: TranscriptionResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(format_srt(result), encoding="utf-8")
    return path


def format_srt(result: TranscriptionResult) -> str:
    segments = _segments_for_srt(result)
    blocks = []
    for index, segment in enumerate(segments, start=1):
        start_s = segment.start_s if segment.start_s is not None else 0.0
        end_s = segment.end_s if segment.end_s is not None else max(start_s + 1.0, _duration_s(result))
        speaker = f"{segment.speaker}: " if segment.speaker else ""
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{format_srt_timestamp(start_s)} --> {format_srt_timestamp(end_s)}",
                    f"{speaker}{segment.text.strip()}",
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_for_srt(result: TranscriptionResult) -> tuple[TranscriptionSegment, ...]:
    timed = tuple(segment for segment in result.segments if segment.text.strip())
    if timed:
        return timed
    text = result.text.strip()
    if not text:
        return ()
    return (TranscriptionSegment(text=text, start_s=0.0, end_s=_duration_s(result)),)


def _duration_s(result: TranscriptionResult) -> float:
    raw = result.metadata.get("duration_s", "")
    try:
        duration = float(raw)
    except (TypeError, ValueError):
        duration = 1.0
    return max(duration, 1.0)
