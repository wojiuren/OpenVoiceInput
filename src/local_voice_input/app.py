"""Application service layer for the local voice input prototype."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Callable

from .asr import BackendUnavailableError, TranscriptionJob, TranscriptionResult
from .audio_capture import RecordingSession, record_wav
from .backends import BackendRegistry, create_default_backend_registry
from .config import AppConfig
from .model_selector import (
    HardwareInfo,
    ModelProfile,
    SelectionRequest,
    SelectionResult,
    detect_hardware,
    get_model_profiles,
    select_model,
)


HardwareProbe = Callable[[], HardwareInfo]


class VoiceInputApp:
    """Coordinate configuration, model selection, and ASR backend execution."""

    def __init__(
        self,
        config: AppConfig | None = None,
        backend_registry: BackendRegistry | None = None,
        model_profiles: Iterable[ModelProfile] | None = None,
        hardware_probe: HardwareProbe = detect_hardware,
    ) -> None:
        self.config = config or AppConfig()
        self.model_profiles = tuple(model_profiles or get_model_profiles())
        self.backend_registry = backend_registry or create_default_backend_registry(
            self.model_profiles,
            config=self.config,
        )
        self._hardware_probe = hardware_probe

    def recommend_model(self, request: SelectionRequest | None = None) -> SelectionResult:
        return select_model(
            request or self.config.selection,
            hardware=self._hardware_probe(),
            profiles=self.model_profiles,
        )

    def transcribe_file(
        self,
        source_path: str | Path,
        request: SelectionRequest | None = None,
    ) -> TranscriptionResult:
        selection_request = request or self.config.selection

        selection = self.recommend_model(selection_request)
        backend = self.backend_registry.create(selection.profile)
        if not backend.is_available():
            detail = _backend_unavailable_detail(backend)
            raise BackendUnavailableError(
                f"Selected {selection.profile.model_id!r}, but backend {selection.profile.backend!r} is unavailable."
                f"{' ' + detail if detail else ''}"
            )

        job = TranscriptionJob(
            source_path=Path(source_path),
            task=selection_request.task,
            language=selection_request.language,
        )
        return backend.transcribe_file(job, selection.profile)

    def record_audio(
        self,
        output_path: str | Path,
        seconds: float,
        device: int | str | None = None,
    ) -> Path:
        return record_wav(
            output_path,
            seconds=seconds,
            sample_rate_hz=self.config.audio.sample_rate_hz,
            channels=self.config.audio.channels,
            device=device if device is not None else self.config.audio.input_device,
        )

    def listen_once(
        self,
        output_path: str | Path,
        seconds: float,
        request: SelectionRequest | None = None,
        device: int | str | None = None,
    ) -> TranscriptionResult:
        audio_path = self.record_audio(output_path, seconds=seconds, device=device)
        selection_request = request or self.config.selection
        return self.transcribe_file(audio_path, request=selection_request)

    def create_recording_session(
        self,
        output_path: str | Path,
        device: int | str | None = None,
    ) -> RecordingSession:
        return RecordingSession(
            output_path,
            sample_rate_hz=self.config.audio.sample_rate_hz,
            channels=self.config.audio.channels,
            device=device if device is not None else self.config.audio.input_device,
        )


def _backend_unavailable_detail(backend) -> str:
    checker = getattr(backend, "unavailable_reason", None)
    if checker is None:
        return ""
    reason = checker()
    return f"Reason: {reason}" if reason else ""
