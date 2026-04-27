"""Hardware-aware ASR model selection.

This module is intentionally UI-free. A desktop client, tray app, or CLI can all
call the same selector and then load the chosen ASR backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import ctypes
import os
import platform
import shutil
import subprocess
from typing import Iterable, Literal


TaskType = Literal["dictation", "file_transcription", "long_form"]
Priority = Literal["auto", "speed", "balanced", "accuracy"]
DevicePolicy = Literal["auto", "cpu", "nvidia"]


@dataclass(frozen=True)
class GpuInfo:
    vendor: str
    name: str
    vram_gb: float


@dataclass(frozen=True)
class HardwareInfo:
    os_name: str
    cpu_threads: int
    ram_gb: float
    gpus: tuple[GpuInfo, ...] = ()

    @property
    def has_nvidia(self) -> bool:
        return any(gpu.vendor.lower() == "nvidia" for gpu in self.gpus)

    @property
    def max_nvidia_vram_gb(self) -> float:
        values = [gpu.vram_gb for gpu in self.gpus if gpu.vendor.lower() == "nvidia"]
        return max(values, default=0.0)


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    display_name: str
    backend: str
    min_ram_gb: float
    recommended_ram_gb: float
    min_vram_gb: float = 0.0
    preferred_device: DevicePolicy = "auto"
    task_fit: tuple[TaskType, ...] = ("dictation",)
    priority_fit: tuple[Priority, ...] = ("auto", "balanced")
    languages: tuple[str, ...] = ("auto",)
    experimental: bool = False
    license_note: str = ""
    notes: str = ""


@dataclass(frozen=True)
class SelectionRequest:
    task: TaskType = "dictation"
    priority: Priority = "auto"
    language: str = "auto"
    device_policy: DevicePolicy = "auto"
    manual_model_id: str | None = None
    allow_experimental: bool = True


@dataclass(frozen=True)
class SelectionResult:
    profile: ModelProfile
    reason: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


def get_model_profiles() -> tuple[ModelProfile, ...]:
    """Return the built-in ASR model registry."""

    return (
        ModelProfile(
            model_id="sensevoice-small-onnx-int8",
            display_name="SenseVoice Small ONNX INT8",
            backend="sherpa-onnx",
            min_ram_gb=3,
            recommended_ram_gb=4,
            task_fit=("dictation", "file_transcription"),
            priority_fit=("auto", "speed", "balanced"),
            languages=("auto", "zh", "en", "yue", "ja", "ko"),
            license_note="Check SenseVoice and converted ONNX model license before bundling.",
            notes="Default CPU-friendly low-latency profile.",
        ),
        ModelProfile(
            model_id="paraformer-zh-onnx",
            display_name="Paraformer Chinese ONNX",
            backend="sherpa-onnx",
            min_ram_gb=3,
            recommended_ram_gb=4,
            task_fit=("dictation", "file_transcription"),
            priority_fit=("auto", "speed"),
            languages=("zh",),
            license_note="FunASR model-license; verify distribution terms.",
            notes="Chinese low-resource fallback.",
        ),
        ModelProfile(
            model_id="fun-asr-1.5-dialect-api",
            display_name="Fun-ASR 1.5 Dialect API",
            backend="aliyun-bailian-api",
            min_ram_gb=0,
            recommended_ram_gb=0,
            task_fit=("file_transcription", "long_form"),
            priority_fit=("accuracy",),
            languages=("zh", "yue", "wuu", "nan", "hak", "xiang", "gan"),
            experimental=True,
            license_note="Reported as available through Alibaba Cloud Bailian API and ModelScope demo; verify API terms and any downloadable artifact before use.",
            notes="Special project profile for Chinese dialect transcription: Mandarin, Wu, Xiang, Gan, Hakka, Min, Yue, and regional accents.",
        ),
        ModelProfile(
            model_id="nemotron-speech-streaming-en-0.6b-foundry-local",
            display_name="Nemotron Speech Streaming EN 0.6B",
            backend="foundry-local",
            min_ram_gb=4,
            recommended_ram_gb=8,
            preferred_device="auto",
            task_fit=("dictation", "file_transcription"),
            priority_fit=("balanced",),
            languages=("en",),
            experimental=True,
            license_note="NVIDIA Open Model License for the upstream model; Foundry Local catalog/runtime terms also apply.",
            notes="English-only streaming ASR experiment. Foundry Local catalog reports a CPU ONNX variant around 697 MiB.",
        ),
        ModelProfile(
            model_id="whisper-small-ctranslate2",
            display_name="Whisper Small CTranslate2",
            backend="faster-whisper",
            min_ram_gb=4,
            recommended_ram_gb=6,
            min_vram_gb=2,
            task_fit=("dictation", "file_transcription"),
            priority_fit=("auto", "balanced"),
            languages=("auto",),
            license_note="Check model weights and faster-whisper/CTranslate2 licenses.",
            notes="Portable fallback with mature ecosystem.",
        ),
        ModelProfile(
            model_id="funasr-nano-gguf",
            display_name="FunASR Nano GGUF",
            backend="gguf",
            min_ram_gb=6,
            recommended_ram_gb=8,
            min_vram_gb=4,
            preferred_device="auto",
            task_fit=("dictation", "file_transcription"),
            priority_fit=("auto", "balanced", "accuracy"),
            languages=("auto", "zh", "en"),
            experimental=True,
            license_note="Verify GGUF conversion and base model license.",
            notes="Balanced model for mid-range machines.",
        ),
        ModelProfile(
            model_id="qwen3-asr-0.6b",
            display_name="Qwen3-ASR 0.6B GGUF",
            backend="qwen3-asr-gguf",
            min_ram_gb=8,
            recommended_ram_gb=16,
            min_vram_gb=0,
            preferred_device="auto",
            task_fit=("dictation", "file_transcription"),
            priority_fit=("balanced", "accuracy"),
            languages=("auto",),
            experimental=True,
            license_note="Apache-2.0 according to Qwen3-ASR model releases; verify HaujetZhao GGUF conversion and bundled runtime terms before use.",
            notes="Primary 7840HS benchmark candidate. HaujetZhao/Qwen3-ASR-GGUF uses ONNX Encoder + GGUF Decoder with DirectML/Vulkan/CPU paths; do not auto-download before benchmark planning.",
        ),
        ModelProfile(
            model_id="qwen3-asr-1.7b-q4",
            display_name="Qwen3-ASR 1.7B GGUF Q4",
            backend="qwen-asr-gguf",
            min_ram_gb=8,
            recommended_ram_gb=12,
            min_vram_gb=8,
            preferred_device="nvidia",
            task_fit=("dictation", "file_transcription"),
            priority_fit=("auto", "accuracy"),
            languages=("auto",),
            experimental=True,
            license_note="Apache-2.0 according to Qwen3-ASR/GGUF model cards; verify HaujetZhao GGUF conversion and bundled runtime terms before use.",
            notes="High-accuracy candidate for RTX 4090/server-side transcription; only test on 7840HS after 0.6B baseline is understood.",
        ),
        ModelProfile(
            model_id="remote-4090-qwen3-asr-1.7b",
            display_name="Remote 4090 Qwen3-ASR 1.7B",
            backend="remote-asr",
            min_ram_gb=0,
            recommended_ram_gb=0,
            preferred_device="auto",
            task_fit=("file_transcription", "long_form"),
            priority_fit=("accuracy",),
            languages=("auto", "zh", "en", "yue"),
            experimental=True,
            license_note="Remote server model/runtime terms depend on the 4090 host configuration; verify before distribution.",
            notes="Reserved profile for a future 4090 remote ASR service. Uses remote_asr config and must not be treated as API text post-processing.",
        ),
        ModelProfile(
            model_id="vibevoice-asr-hf-8b",
            display_name="VibeVoice-ASR HF 8B",
            backend="transformers",
            min_ram_gb=24,
            recommended_ram_gb=32,
            min_vram_gb=16,
            preferred_device="nvidia",
            task_fit=("long_form", "file_transcription"),
            priority_fit=("auto", "accuracy"),
            languages=("auto",),
            experimental=True,
            license_note="MIT according to Microsoft VibeVoice-ASR-HF model card.",
            notes="Long-form transcription, timestamps, and speaker-aware output.",
        ),
    )


def select_model(
    request: SelectionRequest,
    hardware: HardwareInfo | None = None,
    profiles: Iterable[ModelProfile] | None = None,
) -> SelectionResult:
    """Select an ASR model for the requested task and hardware."""

    hardware = hardware or detect_hardware()
    registry = tuple(profiles or get_model_profiles())
    by_id = {profile.model_id: profile for profile in registry}

    if request.manual_model_id:
        profile = by_id.get(request.manual_model_id)
        if not profile:
            available = ", ".join(sorted(by_id))
            raise ValueError(f"Unknown model: {request.manual_model_id}. Available: {available}")
        warnings = _resource_warnings(profile, hardware, request.device_policy)
        return SelectionResult(
            profile=profile,
            reason="Manual model selection overrides automatic policy.",
            warnings=warnings,
        )

    candidates = [
        profile
        for profile in registry
        if request.task in profile.task_fit
        and _priority_matches(request.priority, profile)
        and _language_matches(request.language, profile)
        and _device_policy_matches(request.device_policy, profile)
        and (request.allow_experimental or not profile.experimental)
    ]
    if not candidates:
        candidates = [
            profile
            for profile in registry
            if request.task in profile.task_fit and _device_policy_matches(request.device_policy, profile)
            and (request.allow_experimental or not profile.experimental)
        ]

    feasible = [profile for profile in candidates if not _resource_warnings(profile, hardware, request.device_policy)]
    scored = feasible or candidates
    if not scored:
        raise ValueError(f"No model profiles match task={request.task!r}")

    selected = max(scored, key=lambda profile: _score(profile, request, hardware))
    warnings = _resource_warnings(selected, hardware, request.device_policy)
    return SelectionResult(
        profile=selected,
        reason=_selection_reason(selected, request, hardware, bool(feasible)),
        warnings=warnings,
    )


def detect_hardware() -> HardwareInfo:
    """Best-effort hardware detection using only the Python standard library."""

    return HardwareInfo(
        os_name=platform.system() or "Unknown",
        cpu_threads=os.cpu_count() or 1,
        ram_gb=_detect_ram_gb(),
        gpus=tuple(_detect_nvidia_gpus()),
    )


def _detect_ram_gb() -> float:
    if platform.system() == "Windows":
        return _detect_windows_ram_gb()
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round(pages * page_size / (1024**3), 1)
        except (ValueError, OSError, TypeError):
            pass
    return 0.0


def _detect_windows_ram_gb() -> float:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / (1024**3), 1)
    except Exception:
        return 0.0
    return 0.0


def _detect_nvidia_gpus() -> list[GpuInfo]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return []
    command = [
        nvidia_smi,
        "--query-gpu=name,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    gpus: list[GpuInfo] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 2:
            continue
        name, memory_mb = parts
        try:
            vram_gb = round(float(memory_mb) / 1024, 1)
        except ValueError:
            continue
        gpus.append(GpuInfo(vendor="nvidia", name=name, vram_gb=vram_gb))
    return gpus


def _resource_warnings(
    profile: ModelProfile,
    hardware: HardwareInfo,
    device_policy: DevicePolicy,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if hardware.ram_gb and hardware.ram_gb < profile.min_ram_gb:
        warnings.append(
            f"RAM may be too low for {profile.model_id}: "
            f"{hardware.ram_gb:.1f}GB available, {profile.min_ram_gb:.1f}GB minimum."
        )
    if profile.preferred_device == "nvidia" or device_policy == "nvidia":
        if not hardware.has_nvidia:
            warnings.append(f"{profile.model_id} prefers NVIDIA GPU, but no NVIDIA GPU was detected.")
        elif hardware.max_nvidia_vram_gb < profile.min_vram_gb:
            warnings.append(
                f"NVIDIA VRAM may be too low for {profile.model_id}: "
                f"{hardware.max_nvidia_vram_gb:.1f}GB detected, {profile.min_vram_gb:.1f}GB minimum."
            )
    return tuple(warnings)


def _priority_matches(priority: Priority, profile: ModelProfile) -> bool:
    return priority == "auto" or priority in profile.priority_fit or "auto" in profile.priority_fit


def _language_matches(language: str, profile: ModelProfile) -> bool:
    return language == "auto" or "auto" in profile.languages or language in profile.languages


def _device_policy_matches(device_policy: DevicePolicy, profile: ModelProfile) -> bool:
    if device_policy == "auto":
        return True
    if device_policy == "cpu":
        return profile.preferred_device != "nvidia"
    return profile.preferred_device == "nvidia" or profile.min_vram_gb > 0


def _score(profile: ModelProfile, request: SelectionRequest, hardware: HardwareInfo) -> int:
    score = 0

    if request.task in profile.task_fit:
        score += 30
    if request.priority in profile.priority_fit:
        score += 20
    if request.language in profile.languages:
        score += 8
    if "auto" in profile.languages:
        score += 4

    if hardware.has_nvidia and request.device_policy != "cpu":
        if profile.preferred_device == "nvidia":
            score += 25
        if hardware.max_nvidia_vram_gb >= profile.min_vram_gb:
            score += min(int(hardware.max_nvidia_vram_gb), 16)
            if request.priority == "accuracy":
                score += int(profile.min_vram_gb * 2)
    else:
        if profile.min_vram_gb == 0 and profile.preferred_device != "nvidia":
            score += 25
        elif (
            request.device_policy == "cpu"
            and request.priority == "accuracy"
            and profile.preferred_device != "nvidia"
        ):
            score += 25

    if hardware.ram_gb >= profile.recommended_ram_gb:
        score += 10
    elif hardware.ram_gb >= profile.min_ram_gb:
        score += 5
    else:
        score -= 50

    if request.task == "dictation" and profile.model_id == "vibevoice-asr-hf-8b":
        score -= 25
    if request.task == "long_form" and profile.model_id == "vibevoice-asr-hf-8b":
        score += 30

    return score


def _selection_reason(
    profile: ModelProfile,
    request: SelectionRequest,
    hardware: HardwareInfo,
    fully_feasible: bool,
) -> str:
    device = "NVIDIA GPU" if hardware.has_nvidia and profile.preferred_device == "nvidia" else "CPU/local"
    feasibility = "resource checks passed" if fully_feasible else "selected as best effort with warnings"
    return (
        f"Selected {profile.model_id} for {request.task} "
        f"({request.priority} priority) on {device}; {feasibility}."
    )
