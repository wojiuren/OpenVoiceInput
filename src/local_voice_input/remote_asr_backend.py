"""Remote ASR backend placeholder.

This backend owns remote-ASR configuration checks, but intentionally does not
send HTTP requests yet. Keeping that boundary explicit lets the app select a
remote model profile without accidentally hitting a real server during tests.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .asr import (
    BackendUnavailableError,
    TranscriptionError,
    TranscriptionJob,
    TranscriptionResult,
    TranscriptionSegment,
)
from .config import RemoteAsrConfig, RemoteAsrProfileConfig
from .model_selector import ModelProfile


REMOTE_ASR_TRANSCRIPTIONS_PATH = "/v1/asr/transcriptions"


@dataclass(frozen=True)
class RemoteAsrTransportRequest:
    url: str
    audio_path: Path
    request_payload: Mapping[str, str]
    profile_name: str
    api_key_env: str
    timeout_s: float
    connect_timeout_s: float
    upload_mode: str
    max_audio_mb: int
    verify_tls: bool


RemoteAsrTransport = Callable[[RemoteAsrTransportRequest], Mapping[str, object]]


@dataclass(frozen=True)
class RemoteAsrError:
    code: str
    message: str
    retryable: bool = False
    details: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RemoteAsrBackend:
    config: RemoteAsrConfig = field(default_factory=RemoteAsrConfig)
    transport: RemoteAsrTransport | None = None

    backend_id: ClassVar[str] = "remote-asr"

    def is_available(self) -> bool:
        return self.configuration_problem() is None and self.transport is not None

    def transcribe_file(self, job: TranscriptionJob, profile: ModelProfile) -> TranscriptionResult:
        problem = self.configuration_problem()
        if problem:
            raise BackendUnavailableError(
                f"Backend {self.backend_id!r} for model {profile.model_id!r} cannot run yet: {problem}"
            )
        if self.transport is None:
            raise BackendUnavailableError(
                f"Backend {self.backend_id!r} for model {profile.model_id!r} cannot run yet: "
                f"{self.unavailable_reason()}"
            )

        profile_config = self.profile_config()
        if profile_config is None:
            raise BackendUnavailableError(f"remote_asr profile {self.profile_name!r} is missing.")

        request = build_remote_asr_transport_request(
            job,
            profile,
            profile_name=self.profile_name,
            profile_config=profile_config,
            client_job_id=_client_job_id(job, profile),
        )
        response_payload = self.transport(request)
        return parse_remote_asr_response(response_payload)

    def unavailable_reason(self) -> str:
        problem = self.configuration_problem()
        if problem:
            return problem
        return "RemoteAsrBackend HTTP transport is not implemented yet; no request was sent."

    def configuration_problem(self) -> str | None:
        if not self.config.enabled:
            return (
                "remote_asr is disabled; enable it and set "
                f"remote_asr.profiles.{self.profile_name}.base_url before selecting a remote ASR model."
            )

        profile = self.profile_config()
        if profile is None:
            return f"remote_asr profile {self.profile_name!r} is missing."
        if not profile.base_url:
            return f"remote_asr profile {self.profile_name!r} is missing base_url."
        return None

    @property
    def profile_name(self) -> str:
        return (self.config.profile or "home_4090").strip() or "home_4090"

    def profile_config(self) -> RemoteAsrProfileConfig | None:
        return self.config.profiles.get(self.profile_name)


def build_remote_asr_request_payload(
    job: TranscriptionJob,
    profile: ModelProfile,
    *,
    client_job_id: str,
    timestamp_granularity: str = "segment",
) -> dict[str, str]:
    return {
        "client_job_id": client_job_id,
        "task": job.task,
        "language": job.language,
        "model_id": profile.model_id,
        "source_name": job.source_path.name,
        "response_format": "json",
        "timestamp_granularity": timestamp_granularity,
    }


def build_remote_asr_transport_request(
    job: TranscriptionJob,
    profile: ModelProfile,
    *,
    profile_name: str,
    profile_config: RemoteAsrProfileConfig,
    client_job_id: str,
    timestamp_granularity: str = "segment",
) -> RemoteAsrTransportRequest:
    return RemoteAsrTransportRequest(
        url=remote_asr_transcriptions_url(profile_config.base_url),
        audio_path=job.source_path,
        request_payload=build_remote_asr_request_payload(
            job,
            profile,
            client_job_id=client_job_id,
            timestamp_granularity=timestamp_granularity,
        ),
        profile_name=profile_name,
        api_key_env=profile_config.api_key_env,
        timeout_s=profile_config.timeout_s,
        connect_timeout_s=profile_config.connect_timeout_s,
        upload_mode=profile_config.upload_mode,
        max_audio_mb=profile_config.max_audio_mb,
        verify_tls=profile_config.verify_tls,
    )


def remote_asr_transcriptions_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{REMOTE_ASR_TRANSCRIPTIONS_PATH}"


def parse_remote_asr_response(payload: Mapping[str, object]) -> TranscriptionResult:
    if not isinstance(payload, Mapping):
        raise TranscriptionError("Remote ASR response must be a JSON object.")
    if "error" in payload:
        error = parse_remote_asr_error(payload)
        raise TranscriptionError(format_remote_asr_error(error))

    text = _required_string(payload, "text")
    model_id = _required_string(payload, "model_id")
    language = _optional_string(payload.get("language"), default="auto")
    segments = _parse_segments(payload.get("segments", ()))
    metadata = _string_mapping(payload.get("metadata", {}))
    metadata.setdefault("backend", "remote-asr")
    return TranscriptionResult(
        text=text,
        model_id=model_id,
        language=language,
        segments=segments,
        metadata=metadata,
    )


def parse_remote_asr_error(payload: Mapping[str, object]) -> RemoteAsrError:
    error_payload: object = payload.get("error", payload)
    if not isinstance(error_payload, Mapping):
        return RemoteAsrError(
            code="invalid_error",
            message="Remote ASR returned an invalid error payload.",
            retryable=False,
        )

    code = _optional_string(error_payload.get("code"), default="unknown")
    message = _optional_string(error_payload.get("message"), default="Remote ASR request failed.")
    retryable = bool(error_payload.get("retryable", False))
    details = _string_mapping(error_payload.get("details", {}))
    return RemoteAsrError(code=code, message=message, retryable=retryable, details=details)


def format_remote_asr_error(error: RemoteAsrError) -> str:
    retryable = "true" if error.retryable else "false"
    return f"Remote ASR error {error.code}: {error.message} (retryable={retryable})"


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise TranscriptionError(f"Remote ASR response is missing string field {key!r}.")
    return value


def _optional_string(value: object, *, default: str) -> str:
    if isinstance(value, str) and value:
        return value
    return default


def _parse_segments(value: object) -> tuple[TranscriptionSegment, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list | tuple):
        raise TranscriptionError("Remote ASR response field 'segments' must be a list.")

    segments: list[TranscriptionSegment] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TranscriptionError(f"Remote ASR segment {index} must be a JSON object.")
        segments.append(
            TranscriptionSegment(
                text=_optional_string(item.get("text"), default=""),
                start_s=_optional_float(item.get("start_s")),
                end_s=_optional_float(item.get("end_s")),
                speaker=_optional_nullable_string(item.get("speaker")),
            )
        )
    return tuple(segments)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise TranscriptionError(f"Remote ASR segment timestamp must be numeric, got {value!r}.") from None


def _optional_nullable_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): "" if item is None else str(item) for key, item in value.items()}


def _client_job_id(job: TranscriptionJob, profile: ModelProfile) -> str:
    existing = job.metadata.get("client_job_id")
    if existing:
        return existing
    return f"{profile.model_id}:{job.source_path.name}"
