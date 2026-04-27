"""Application configuration helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
import json
import os
from pathlib import Path
from typing import Any, TypeVar

from .model_selector import Priority, SelectionRequest, TaskType


@dataclass(frozen=True)
class AudioConfig:
    input_device: int | str | None = None
    sample_rate_hz: int = 16000
    channels: int = 1
    chunk_ms: int = 30


@dataclass(frozen=True)
class RecordingConfig:
    keep_audio_files: bool = False


@dataclass(frozen=True)
class HotkeyConfig:
    hold_to_talk: str = "caps_lock"
    cancel: str = "esc"
    submit_strategy: str = "clipboard_paste"


@dataclass(frozen=True)
class QuickCaptureRule:
    name: str
    keywords: tuple[str, ...]
    target_dir: str
    match_window_chars: int | None = None
    remove_keyword: bool | None = None


@dataclass(frozen=True)
class QuickCaptureConfig:
    enabled: bool = False
    root_dir: str = "notes"
    inbox_dir: str = "inbox"
    match_window_chars: int = 16
    remove_keyword: bool = True
    rules: tuple[QuickCaptureRule, ...] = ()


@dataclass(frozen=True)
class HotwordConfig:
    words: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True)
class ApiProviderConfig:
    provider: str = "local"
    base_url: str = ""
    api_key_env: str = ""
    model: str = ""
    timeout_s: float = 30.0


@dataclass(frozen=True)
class ApiProcessingConfig:
    enabled: bool = False
    preset: str = "clean"
    fallback_raw: bool = False


@dataclass(frozen=True)
class ApiContextConfig:
    mode: str = "off"
    recent_turns: int = 3
    max_context_chars: int = 1200
    glossary_enabled: bool = True
    compression_enabled: bool = False
    compressed_summary_chars: int = 800


@dataclass(frozen=True)
class RemoteAsrProfileConfig:
    base_url: str = ""
    api_key_env: str = ""
    timeout_s: float = 120.0
    connect_timeout_s: float = 5.0
    upload_mode: str = "multipart"
    fallback_model_id: str = "sensevoice-small-onnx-int8"
    max_audio_mb: int = 200
    verify_tls: bool = True


@dataclass(frozen=True)
class RemoteAsrConfig:
    enabled: bool = False
    profile: str = "home_4090"
    profiles: dict[str, RemoteAsrProfileConfig] = field(
        default_factory=lambda: {"home_4090": RemoteAsrProfileConfig()}
    )


@dataclass(frozen=True)
class TaskRouteConfig:
    priority: Priority = "auto"
    background: bool = False
    manual_model_id: str | None = None


@dataclass(frozen=True)
class TaskRoutingConfig:
    dictation: TaskRouteConfig = field(
        default_factory=lambda: TaskRouteConfig(priority="speed", background=False)
    )
    file_transcription: TaskRouteConfig = field(
        default_factory=lambda: TaskRouteConfig(priority="balanced", background=True)
    )
    long_form: TaskRouteConfig = field(
        default_factory=lambda: TaskRouteConfig(priority="accuracy", background=True)
    )


@dataclass(frozen=True)
class AppConfig:
    selection: SelectionRequest = field(default_factory=SelectionRequest)
    audio: AudioConfig = field(default_factory=AudioConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    quick_capture: QuickCaptureConfig = field(default_factory=QuickCaptureConfig)
    hotwords: HotwordConfig = field(default_factory=HotwordConfig)
    api_provider: ApiProviderConfig = field(default_factory=ApiProviderConfig)
    api_processing: ApiProcessingConfig = field(default_factory=ApiProcessingConfig)
    api_context: ApiContextConfig = field(default_factory=ApiContextConfig)
    remote_asr: RemoteAsrConfig = field(default_factory=RemoteAsrConfig)
    task_routes: TaskRoutingConfig = field(default_factory=TaskRoutingConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        audio_data = data.get("audio", {})
        if isinstance(audio_data, dict) and "input_device_name" in audio_data and "input_device" not in audio_data:
            audio_data = {**audio_data, "input_device": audio_data["input_device_name"]}
        return cls(
            selection=_coerce_dataclass(SelectionRequest, data.get("selection", {})),
            audio=_coerce_dataclass(AudioConfig, audio_data),
            recording=_coerce_recording(data.get("recording", {})),
            hotkey=_coerce_dataclass(HotkeyConfig, data.get("hotkey", {})),
            quick_capture=_coerce_quick_capture(data.get("quick_capture", {})),
            hotwords=_coerce_hotwords(data.get("hotwords", {})),
            api_provider=_coerce_dataclass(ApiProviderConfig, data.get("api_provider", {})),
            api_processing=_coerce_dataclass(ApiProcessingConfig, data.get("api_processing", {})),
            api_context=_coerce_api_context(data.get("api_context", {})),
            remote_asr=_coerce_remote_asr(data.get("remote_asr", {})),
            task_routes=_coerce_task_routes(data.get("task_routes", {})),
        )


T = TypeVar("T")


def _coerce_dataclass(cls: type[T], raw: object) -> T:
    if not isinstance(raw, dict):
        return cls()  # type: ignore[call-arg]
    allowed = {field.name for field in fields(cls)}
    values = {key: value for key, value in raw.items() if key in allowed}
    return cls(**values)  # type: ignore[call-arg]


def _coerce_quick_capture(raw: object) -> QuickCaptureConfig:
    if not isinstance(raw, dict):
        return QuickCaptureConfig()
    rules = tuple(_coerce_quick_capture_rule(item) for item in raw.get("rules", ()) if isinstance(item, dict))
    base = _coerce_dataclass(QuickCaptureConfig, {key: value for key, value in raw.items() if key != "rules"})
    return replace(base, rules=rules)


def _coerce_quick_capture_rule(raw: dict[str, Any]) -> QuickCaptureRule:
    keywords = raw.get("keywords", ())
    if isinstance(keywords, str):
        keyword_values = (keywords,)
    else:
        keyword_values = tuple(str(keyword) for keyword in keywords)
    return QuickCaptureRule(
        name=str(raw.get("name") or ""),
        keywords=keyword_values,
        target_dir=str(raw.get("target_dir") or ""),
        match_window_chars=raw.get("match_window_chars"),
        remove_keyword=raw.get("remove_keyword"),
    )


def _coerce_recording(raw: object) -> RecordingConfig:
    config = _coerce_dataclass(RecordingConfig, raw)
    return replace(config, keep_audio_files=_coerce_bool(config.keep_audio_files, default=False))


def _coerce_hotwords(raw: object) -> HotwordConfig:
    if not isinstance(raw, dict):
        return HotwordConfig()
    words = raw.get("words", ())
    if isinstance(words, str):
        word_values = (words,)
    else:
        word_values = tuple(str(word) for word in words)
    return HotwordConfig(words=word_values, enabled=bool(raw.get("enabled", True)))


def _coerce_api_context(raw: object) -> ApiContextConfig:
    config = _coerce_dataclass(ApiContextConfig, raw)
    mode = str(config.mode or "off").strip().lower()
    if mode not in {"off", "lightweight", "compressed"}:
        mode = "off"
    recent_turns = _clamp_int(config.recent_turns, default=3, minimum=0, maximum=20)
    max_context_chars = _clamp_int(config.max_context_chars, default=1200, minimum=0, maximum=20000)
    compressed_summary_chars = _clamp_int(
        config.compressed_summary_chars,
        default=800,
        minimum=0,
        maximum=10000,
    )
    return replace(
        config,
        mode=mode,
        recent_turns=recent_turns,
        max_context_chars=max_context_chars,
        compressed_summary_chars=compressed_summary_chars,
    )


def _coerce_remote_asr(raw: object) -> RemoteAsrConfig:
    if not isinstance(raw, dict):
        return RemoteAsrConfig()
    enabled = _coerce_bool(raw.get("enabled"), default=False)
    profile = str(raw.get("profile") or "home_4090").strip() or "home_4090"
    profiles_raw = raw.get("profiles", {})
    profiles: dict[str, RemoteAsrProfileConfig] = {}
    if isinstance(profiles_raw, dict):
        for name, value in profiles_raw.items():
            clean_name = str(name).strip()
            if not clean_name or not isinstance(value, dict):
                continue
            profiles[clean_name] = _coerce_remote_asr_profile(value)
    if not profiles:
        profiles = {profile: RemoteAsrProfileConfig()}
    elif profile not in profiles:
        profiles[profile] = RemoteAsrProfileConfig()
    return RemoteAsrConfig(enabled=enabled, profile=profile, profiles=profiles)


def _coerce_remote_asr_profile(raw: object) -> RemoteAsrProfileConfig:
    config = _coerce_dataclass(RemoteAsrProfileConfig, raw)
    upload_mode = str(config.upload_mode or "multipart").strip().lower()
    if upload_mode not in {"multipart"}:
        upload_mode = "multipart"
    return replace(
        config,
        base_url=str(config.base_url or "").strip().rstrip("/"),
        api_key_env=str(config.api_key_env or "").strip(),
        timeout_s=_clamp_float(config.timeout_s, default=120.0, minimum=1.0, maximum=3600.0),
        connect_timeout_s=_clamp_float(config.connect_timeout_s, default=5.0, minimum=1.0, maximum=120.0),
        upload_mode=upload_mode,
        fallback_model_id=str(config.fallback_model_id or "").strip(),
        max_audio_mb=_clamp_int(config.max_audio_mb, default=200, minimum=1, maximum=2048),
        verify_tls=_coerce_bool(config.verify_tls, default=True),
    )


def _coerce_task_routes(raw: object) -> TaskRoutingConfig:
    if not isinstance(raw, dict):
        return TaskRoutingConfig()
    return TaskRoutingConfig(
        dictation=_coerce_dataclass(TaskRouteConfig, raw.get("dictation", {})),
        file_transcription=_coerce_dataclass(TaskRouteConfig, raw.get("file_transcription", {})),
        long_form=_coerce_dataclass(TaskRouteConfig, raw.get("long_form", {})),
    )


def _clamp_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _clamp_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "on"}:
            return True
        if clean in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def default_config_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "OpenVoiceInput" / "config.json"
    return Path.home() / ".config" / "open-voice-input" / "config.json"


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = Path(path) if path else default_config_path()
    if not config_path.exists():
        return AppConfig()
    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a JSON object: {config_path}")
    return AppConfig.from_dict(data)


def save_config(config: AppConfig, path: str | Path | None = None) -> Path:
    config_path = Path(path) if path else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as file:
        json.dump(config.to_dict(), file, ensure_ascii=False, indent=2)
        file.write("\n")
    return config_path


def update_config(
    config: AppConfig,
    *,
    language: str | None = None,
    priority: str | None = None,
    device_policy: str | None = None,
    manual_model_id: str | None = None,
    allow_experimental: bool | None = None,
    input_device: int | str | None = None,
    sample_rate_hz: int | None = None,
    channels: int | None = None,
    keep_audio_files: bool | None = None,
    hold_to_talk: str | None = None,
    submit_strategy: str | None = None,
    api_process_enabled: bool | None = None,
    api_preset: str | None = None,
    api_fallback_raw: bool | None = None,
    api_context_mode: str | None = None,
    api_context_recent_turns: int | None = None,
    api_context_max_chars: int | None = None,
    api_context_glossary_enabled: bool | None = None,
    api_context_compression_enabled: bool | None = None,
    api_context_compressed_summary_chars: int | None = None,
    quick_capture_enabled: bool | None = None,
) -> AppConfig:
    selection = config.selection
    if language is not None:
        selection = replace(selection, language=language)
    if priority is not None:
        selection = replace(selection, priority=priority)
    if device_policy is not None:
        selection = replace(selection, device_policy=device_policy)
    if manual_model_id is not None:
        selection = replace(selection, manual_model_id=manual_model_id or None)
    if allow_experimental is not None:
        selection = replace(selection, allow_experimental=allow_experimental)

    audio = config.audio
    if input_device is not None:
        audio = replace(audio, input_device=input_device)
    if sample_rate_hz is not None:
        audio = replace(audio, sample_rate_hz=sample_rate_hz)
    if channels is not None:
        audio = replace(audio, channels=channels)

    recording = config.recording
    if keep_audio_files is not None:
        recording = replace(recording, keep_audio_files=keep_audio_files)

    hotkey = config.hotkey
    if hold_to_talk is not None:
        hotkey = replace(hotkey, hold_to_talk=hold_to_talk)
    if submit_strategy is not None:
        hotkey = replace(hotkey, submit_strategy=submit_strategy)

    quick_capture = config.quick_capture
    if quick_capture_enabled is not None:
        quick_capture = replace(quick_capture, enabled=quick_capture_enabled)

    api_processing = config.api_processing
    if api_process_enabled is not None:
        api_processing = replace(api_processing, enabled=api_process_enabled)
    if api_preset is not None:
        api_processing = replace(api_processing, preset=api_preset)
    if api_fallback_raw is not None:
        api_processing = replace(api_processing, fallback_raw=api_fallback_raw)

    api_context = config.api_context
    if api_context_mode is not None:
        api_context = replace(api_context, mode=api_context_mode)
    if api_context_recent_turns is not None:
        api_context = replace(api_context, recent_turns=api_context_recent_turns)
    if api_context_max_chars is not None:
        api_context = replace(api_context, max_context_chars=api_context_max_chars)
    if api_context_glossary_enabled is not None:
        api_context = replace(api_context, glossary_enabled=api_context_glossary_enabled)
    if api_context_compression_enabled is not None:
        api_context = replace(api_context, compression_enabled=api_context_compression_enabled)
    if api_context_compressed_summary_chars is not None:
        api_context = replace(api_context, compressed_summary_chars=api_context_compressed_summary_chars)
    api_context = _coerce_api_context(asdict(api_context))

    return replace(
        config,
        selection=selection,
        audio=audio,
        recording=recording,
        hotkey=hotkey,
        quick_capture=quick_capture,
        api_processing=api_processing,
        api_context=api_context,
    )


def add_quick_capture_rule(
    config: AppConfig,
    *,
    name: str,
    keywords: tuple[str, ...],
    target_dir: str,
    match_window_chars: int | None = None,
    remove_keyword: bool | None = None,
) -> AppConfig:
    rule = QuickCaptureRule(
        name=name,
        keywords=keywords,
        target_dir=target_dir,
        match_window_chars=match_window_chars,
        remove_keyword=remove_keyword,
    )
    quick_capture = replace(config.quick_capture, rules=(*config.quick_capture.rules, rule))
    return replace(config, quick_capture=quick_capture)


def clear_quick_capture_rules(config: AppConfig) -> AppConfig:
    return replace(config, quick_capture=replace(config.quick_capture, rules=()))


def add_hotwords(config: AppConfig, words: tuple[str, ...]) -> AppConfig:
    merged = _unique_words((*config.hotwords.words, *words))
    return replace(config, hotwords=replace(config.hotwords, words=merged))


def clear_hotwords(config: AppConfig) -> AppConfig:
    return replace(config, hotwords=replace(config.hotwords, words=()))


def set_hotwords_enabled(config: AppConfig, enabled: bool) -> AppConfig:
    return replace(config, hotwords=replace(config.hotwords, enabled=enabled))


def update_api_provider(
    config: AppConfig,
    *,
    provider: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    model: str | None = None,
    timeout_s: float | None = None,
) -> AppConfig:
    api_provider = config.api_provider
    if provider is not None:
        api_provider = replace(api_provider, provider=provider)
    if base_url is not None:
        api_provider = replace(api_provider, base_url=base_url)
    if api_key_env is not None:
        api_provider = replace(api_provider, api_key_env=api_key_env)
    if model is not None:
        api_provider = replace(api_provider, model=model)
    if timeout_s is not None:
        api_provider = replace(api_provider, timeout_s=timeout_s)
    return replace(config, api_provider=api_provider)


def update_remote_asr(
    config: AppConfig,
    *,
    enabled: bool | None = None,
    profile: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    timeout_s: float | None = None,
    connect_timeout_s: float | None = None,
    upload_mode: str | None = None,
    fallback_model_id: str | None = None,
    max_audio_mb: int | None = None,
    verify_tls: bool | None = None,
) -> AppConfig:
    remote_asr = config.remote_asr
    active_profile = (profile or remote_asr.profile or "home_4090").strip() or "home_4090"
    profiles = dict(remote_asr.profiles)
    profile_config = profiles.get(active_profile, RemoteAsrProfileConfig())

    if base_url is not None:
        profile_config = replace(profile_config, base_url=base_url)
    if api_key_env is not None:
        profile_config = replace(profile_config, api_key_env=api_key_env)
    if timeout_s is not None:
        profile_config = replace(profile_config, timeout_s=timeout_s)
    if connect_timeout_s is not None:
        profile_config = replace(profile_config, connect_timeout_s=connect_timeout_s)
    if upload_mode is not None:
        profile_config = replace(profile_config, upload_mode=upload_mode)
    if fallback_model_id is not None:
        profile_config = replace(profile_config, fallback_model_id=fallback_model_id)
    if max_audio_mb is not None:
        profile_config = replace(profile_config, max_audio_mb=max_audio_mb)
    if verify_tls is not None:
        profile_config = replace(profile_config, verify_tls=verify_tls)

    profiles[active_profile] = _coerce_remote_asr_profile(asdict(profile_config))
    remote_asr = replace(
        remote_asr,
        enabled=remote_asr.enabled if enabled is None else enabled,
        profile=active_profile,
        profiles=profiles,
    )
    return replace(config, remote_asr=_coerce_remote_asr(asdict(remote_asr)))


def update_task_route(
    config: AppConfig,
    task: TaskType,
    *,
    priority: Priority | None = None,
    background: bool | None = None,
    manual_model_id: str | None = None,
    clear_manual_model: bool = False,
) -> AppConfig:
    route = getattr(config.task_routes, task)
    if priority is not None:
        route = replace(route, priority=priority)
    if background is not None:
        route = replace(route, background=background)
    if clear_manual_model:
        route = replace(route, manual_model_id=None)
    elif manual_model_id is not None:
        route = replace(route, manual_model_id=manual_model_id or None)
    routes = replace(config.task_routes, **{task: route})
    return replace(config, task_routes=routes)


def selection_for_task(
    config: AppConfig,
    task: TaskType,
    *,
    language: str | None = None,
) -> SelectionRequest:
    route = getattr(config.task_routes, task)
    manual_model_id = route.manual_model_id or config.selection.manual_model_id
    return replace(
        config.selection,
        task=task,
        priority=route.priority,
        language=language or config.selection.language,
        manual_model_id=manual_model_id,
    )


def _unique_words(words: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        clean = word.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return tuple(result)
