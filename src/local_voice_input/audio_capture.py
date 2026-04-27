"""Microphone recording helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


class AudioCaptureError(RuntimeError):
    """Raised when microphone capture cannot start or finish."""


@dataclass(frozen=True)
class AudioInputDevice:
    index: int
    name: str
    max_input_channels: int
    default_sample_rate: float


def list_input_devices(_sounddevice: Any | None = None) -> tuple[AudioInputDevice, ...]:
    sd = _sounddevice or _import_sounddevice()
    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise AudioCaptureError(f"failed to query audio devices: {exc}") from exc

    result: list[AudioInputDevice] = []
    for index, device in enumerate(devices):
        max_input_channels = int(device.get("max_input_channels", 0))
        if max_input_channels <= 0:
            continue
        result.append(
            AudioInputDevice(
                index=index,
                name=_clean_device_name(str(device.get("name", f"Input device {index}"))),
                max_input_channels=max_input_channels,
                default_sample_rate=float(device.get("default_samplerate", 0.0)),
            )
        )
    return tuple(result)


def record_wav(
    output_path: str | Path,
    seconds: float,
    sample_rate_hz: int = 16000,
    channels: int = 1,
    device: int | str | None = None,
    _sounddevice: Any | None = None,
    _soundfile: Any | None = None,
) -> Path:
    if seconds <= 0:
        raise ValueError("seconds must be greater than 0")
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be greater than 0")
    if channels <= 0:
        raise ValueError("channels must be greater than 0")

    sd = _sounddevice or _import_sounddevice()
    sf = _soundfile or _import_soundfile()

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(sample_rate_hz * seconds)

    try:
        audio = sd.rec(
            frame_count,
            samplerate=sample_rate_hz,
            channels=channels,
            dtype="float32",
            device=device,
        )
        sd.wait()
        sf.write(str(path), audio, sample_rate_hz)
    except Exception as exc:
        raise AudioCaptureError(f"failed to record audio to {path}: {exc}") from exc

    return path


class RecordingSession:
    """A microphone recording that starts now and writes a wav when stopped."""

    def __init__(
        self,
        output_path: str | Path,
        sample_rate_hz: int = 16000,
        channels: int = 1,
        device: int | str | None = None,
        _sounddevice: Any | None = None,
        _soundfile: Any | None = None,
    ) -> None:
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be greater than 0")
        if channels <= 0:
            raise ValueError("channels must be greater than 0")

        self.output_path = Path(output_path)
        self.sample_rate_hz = sample_rate_hz
        self.channels = channels
        self.device = device
        self._sounddevice = _sounddevice or _import_sounddevice()
        self._soundfile = _soundfile or _import_soundfile()
        self._chunks: list[Any] = []
        self._lock = Lock()
        self._stream = None
        self._started = False

    @property
    def is_recording(self) -> bool:
        return self._started

    def start(self) -> None:
        if self._started:
            raise AudioCaptureError("recording session is already started")

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self._sounddevice.InputStream(
                samplerate=self.sample_rate_hz,
                channels=self.channels,
                dtype="float32",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()
            self._started = True
        except Exception as exc:
            raise AudioCaptureError(f"failed to start recording {self.output_path}: {exc}") from exc

    def stop(self) -> Path:
        if not self._started or self._stream is None:
            raise AudioCaptureError("recording session is not started")

        try:
            self._stream.stop()
            self._stream.close()
            self._started = False

            with self._lock:
                chunks = list(self._chunks)
            if not chunks:
                raise AudioCaptureError("recording captured no audio")

            audio = _concat_audio_chunks(chunks)
            self._soundfile.write(str(self.output_path), audio, self.sample_rate_hz)
        except AudioCaptureError:
            raise
        except Exception as exc:
            raise AudioCaptureError(f"failed to stop recording {self.output_path}: {exc}") from exc
        finally:
            self._stream = None

        return self.output_path

    def _callback(self, indata, frames, time, status) -> None:
        if status:
            # Keep recording; sounddevice passes status for overruns/underruns.
            pass
        with self._lock:
            self._chunks.append(indata.copy())


def _import_sounddevice():
    try:
        import sounddevice
    except ImportError as exc:
        raise AudioCaptureError("missing Python package: sounddevice") from exc
    return sounddevice


def _import_soundfile():
    try:
        import soundfile
    except ImportError as exc:
        raise AudioCaptureError("missing Python package: soundfile") from exc
    return soundfile


def _clean_device_name(name: str) -> str:
    return " ".join(name.split())


def _concat_audio_chunks(chunks):
    try:
        import numpy as np

        return np.concatenate(chunks, axis=0)
    except Exception:
        combined = []
        for chunk in chunks:
            combined.extend(chunk)
        return combined
