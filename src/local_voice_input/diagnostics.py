"""Environment checks for the local voice input prototype."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from pathlib import Path

from .audio_capture import AudioCaptureError, list_input_devices
from .sherpa_backend import SENSEVOICE_DIR_NAME, SherpaOnnxSenseVoiceBackend, default_model_root


@dataclass(frozen=True)
class DiagnosticCheck:
    name: str
    ok: bool
    message: str


def run_diagnostics(run_transcribe_smoke: bool = False) -> tuple[DiagnosticCheck, ...]:
    checks = [
        _package_check("sherpa_onnx"),
        _package_check("soundfile"),
        _package_check("sounddevice"),
        _package_check("keyboard"),
        _package_check("pyperclip"),
        _sensevoice_model_check(),
        _audio_device_check(),
    ]
    if run_transcribe_smoke:
        checks.append(_transcribe_smoke_check())
    return tuple(checks)


def has_failures(checks: tuple[DiagnosticCheck, ...]) -> bool:
    return any(not check.ok for check in checks)


def format_diagnostics(checks: tuple[DiagnosticCheck, ...]) -> str:
    lines = []
    for check in checks:
        marker = "OK" if check.ok else "FAIL"
        lines.append(f"{marker}\t{check.name}\t{check.message}")
    return "\n".join(lines)


def _package_check(module_name: str) -> DiagnosticCheck:
    ok = importlib.util.find_spec(module_name) is not None
    message = "installed" if ok else "not installed"
    return DiagnosticCheck(name=f"package:{module_name}", ok=ok, message=message)


def _sensevoice_model_check() -> DiagnosticCheck:
    backend = SherpaOnnxSenseVoiceBackend()
    reason = backend.unavailable_reason()
    if reason:
        return DiagnosticCheck(name="model:sensevoice", ok=False, message=reason)
    return DiagnosticCheck(name="model:sensevoice", ok=True, message=str(backend.model_files.model))


def _audio_device_check() -> DiagnosticCheck:
    try:
        devices = list_input_devices()
    except AudioCaptureError as exc:
        return DiagnosticCheck(name="audio:input_devices", ok=False, message=str(exc))
    if not devices:
        return DiagnosticCheck(name="audio:input_devices", ok=False, message="no input devices found")
    return DiagnosticCheck(name="audio:input_devices", ok=True, message=f"{len(devices)} input device(s) found")


def _transcribe_smoke_check() -> DiagnosticCheck:
    sample = default_model_root() / SENSEVOICE_DIR_NAME / "test_wavs" / "zh.wav"
    if not sample.exists():
        return DiagnosticCheck(name="smoke:transcribe", ok=False, message=f"sample wav not found: {sample}")

    try:
        from .app import VoiceInputApp
        from .model_selector import SelectionRequest

        result = VoiceInputApp().transcribe_file(
            sample,
            request=SelectionRequest(task="file_transcription", language="zh"),
        )
    except Exception as exc:
        return DiagnosticCheck(name="smoke:transcribe", ok=False, message=str(exc))

    text = result.text.strip()
    if not text:
        return DiagnosticCheck(name="smoke:transcribe", ok=False, message="empty transcription")
    return DiagnosticCheck(name="smoke:transcribe", ok=True, message=text)
