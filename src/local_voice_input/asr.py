"""ASR backend contracts and transcription result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol

from .model_selector import ModelProfile, TaskType


@dataclass(frozen=True)
class TranscriptionJob:
    """A file-based transcription request passed to an ASR backend."""

    source_path: Path
    task: TaskType = "file_transcription"
    language: str = "auto"
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptionSegment:
    text: str
    start_s: float | None = None
    end_s: float | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    model_id: str
    language: str = "auto"
    segments: tuple[TranscriptionSegment, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)


class BackendUnavailableError(RuntimeError):
    """Raised when a selected ASR backend is not installed or not implemented."""


class TranscriptionError(RuntimeError):
    """Raised when an available backend fails while decoding audio."""


class AsrBackend(Protocol):
    backend_id: str

    def is_available(self) -> bool:
        """Return whether this backend can run in the current environment."""

    def transcribe_file(self, job: TranscriptionJob, profile: ModelProfile) -> TranscriptionResult:
        """Transcribe an audio or video file with the selected model profile."""
