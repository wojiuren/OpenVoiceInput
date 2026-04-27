"""sherpa-onnx ASR backend integration."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path

from .asr import BackendUnavailableError, TranscriptionError, TranscriptionJob, TranscriptionResult
from .model_selector import ModelProfile


SENSEVOICE_DIR_NAME = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"


@dataclass(frozen=True)
class SenseVoiceModelFiles:
    model: Path
    tokens: Path

    @classmethod
    def discover(cls, model_root: str | Path | None = None) -> "SenseVoiceModelFiles":
        root = Path(model_root) if model_root else default_model_root()
        candidates = [
            root / SENSEVOICE_DIR_NAME,
            root / "sensevoice-small-onnx-int8",
            root,
        ]
        for directory in candidates:
            model = _first_existing(
                directory / "model.int8.onnx",
                directory / "model.onnx",
            )
            tokens = directory / "tokens.txt"
            if model and tokens.exists():
                return cls(model=model, tokens=tokens)
        return cls(model=root / SENSEVOICE_DIR_NAME / "model.int8.onnx", tokens=root / SENSEVOICE_DIR_NAME / "tokens.txt")

    def missing_paths(self) -> tuple[Path, ...]:
        paths = []
        if not self.model.exists():
            paths.append(self.model)
        if not self.tokens.exists():
            paths.append(self.tokens)
        return tuple(paths)


class SherpaOnnxSenseVoiceBackend:
    backend_id = "sherpa-onnx"

    def __init__(
        self,
        model_root: str | Path | None = None,
        num_threads: int = 2,
        provider: str = "cpu",
        use_itn: bool = True,
    ) -> None:
        self.model_files = SenseVoiceModelFiles.discover(model_root)
        self.num_threads = num_threads
        self.provider = provider
        self.use_itn = use_itn

    def is_available(self) -> bool:
        return self.unavailable_reason() is None

    def unavailable_reason(self) -> str | None:
        try:
            import sherpa_onnx  # noqa: F401
            import soundfile  # noqa: F401
        except ImportError as exc:
            return f"missing Python package: {exc.name}"

        missing = self.model_files.missing_paths()
        if missing:
            paths = ", ".join(str(path) for path in missing)
            return f"missing model files: {paths}"
        return None

    def transcribe_file(self, job: TranscriptionJob, profile: ModelProfile) -> TranscriptionResult:
        reason = self.unavailable_reason()
        if reason:
            raise BackendUnavailableError(
                f"Backend {self.backend_id!r} for model {profile.model_id!r} is not available: {reason}"
            )

        import sherpa_onnx
        import soundfile as sf

        try:
            samples, sample_rate = sf.read(str(job.source_path), dtype="float32", always_2d=False)
            if getattr(samples, "ndim", 1) == 2:
                samples = samples.mean(axis=1)

            language = "" if job.language == "auto" else job.language
            with _temporary_working_directory(self.model_files.model.parent):
                recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                    model=self.model_files.model.name,
                    tokens=self.model_files.tokens.name,
                    num_threads=self.num_threads,
                    provider=self.provider,
                    language=language,
                    use_itn=self.use_itn,
                )
                stream = recognizer.create_stream()
                stream.accept_waveform(sample_rate, samples)
                recognizer.decode_stream(stream)
        except Exception as exc:
            raise TranscriptionError(f"sherpa-onnx failed to transcribe {job.source_path}: {exc}") from exc

        text = getattr(stream.result, "text", "")
        return TranscriptionResult(
            text=text,
            model_id=profile.model_id,
            language=job.language,
            metadata={
                "backend": self.backend_id,
                "sample_rate_hz": str(sample_rate),
                "duration_s": f"{len(samples) / sample_rate:.3f}",
                "source_path": str(job.source_path),
            },
        )


def default_model_root() -> Path:
    configured = os.environ.get("OPEN_VOICE_INPUT_MODEL_DIR")
    if configured:
        return Path(configured)
    for candidate in _default_model_root_candidates():
        if candidate.exists():
            return candidate
    return _default_model_root_candidates()[0]


def _default_model_root_candidates() -> tuple[Path, ...]:
    package_models = Path(__file__).resolve().parents[2] / "models"
    cwd_models = Path.cwd().resolve() / "models"
    candidates = []
    for path in (package_models, cwd_models):
        if path not in candidates:
            candidates.append(path)
    return tuple(candidates)


def _first_existing(*paths: Path) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


@contextmanager
def _temporary_working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)
