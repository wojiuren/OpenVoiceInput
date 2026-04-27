"""ASR backend registry.

Real model integrations will register concrete implementations here. Until then,
the default registry returns clear unavailable-backend errors instead of failing
with an import error deep in a future UI flow.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .asr import AsrBackend, BackendUnavailableError, TranscriptionJob, TranscriptionResult
from .config import AppConfig, RemoteAsrConfig
from .model_selector import ModelProfile, get_model_profiles
from .remote_asr_backend import RemoteAsrBackend
from .sherpa_backend import SherpaOnnxSenseVoiceBackend


BackendFactory = Callable[[ModelProfile], AsrBackend]


class BackendRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, BackendFactory] = {}

    def register(self, backend_id: str, factory: BackendFactory) -> None:
        self._factories[backend_id] = factory

    def create(self, profile: ModelProfile) -> AsrBackend:
        factory = self._factories.get(profile.backend)
        if factory is None:
            raise BackendUnavailableError(f"No ASR backend registered for {profile.backend!r}.")
        return factory(profile)

    def registered_backend_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


@dataclass(frozen=True)
class UnavailableAsrBackend:
    backend_id: str
    reason: str

    def is_available(self) -> bool:
        return False

    def transcribe_file(self, job: TranscriptionJob, profile: ModelProfile) -> TranscriptionResult:
        raise BackendUnavailableError(
            f"Backend {self.backend_id!r} for model {profile.model_id!r} is not available: {self.reason}"
        )

    def unavailable_reason(self) -> str:
        return self.reason


def create_default_backend_registry(
    profiles: Iterable[ModelProfile] | None = None,
    config: AppConfig | None = None,
) -> BackendRegistry:
    registry = BackendRegistry()
    backend_ids = sorted({profile.backend for profile in (profiles or get_model_profiles())})
    remote_asr_config = config.remote_asr if config else RemoteAsrConfig()
    for backend_id in backend_ids:
        if backend_id == SherpaOnnxSenseVoiceBackend.backend_id:
            registry.register(backend_id, lambda _profile: SherpaOnnxSenseVoiceBackend())
        elif backend_id == RemoteAsrBackend.backend_id:
            registry.register(
                backend_id,
                lambda _profile, remote_asr_config=remote_asr_config: RemoteAsrBackend(remote_asr_config),
            )
        else:
            registry.register(
                backend_id,
                lambda _profile, backend_id=backend_id: UnavailableAsrBackend(
                    backend_id=backend_id,
                    reason=_unavailable_reason_for_backend(backend_id),
                ),
            )
    return registry


def _unavailable_reason_for_backend(backend_id: str) -> str:
    return "the integration has not been wired into this MVP yet"
