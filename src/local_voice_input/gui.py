"""Minimal Tkinter launcher and settings panel for the prototype."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Mapping, Sequence

from .api_context import ApiContextPackage, build_api_context_package
from .api_provider import POSTPROCESS_PRESETS
from .audio_capture import AudioInputDevice, list_input_devices
from .config import (
    ApiProviderConfig,
    AppConfig,
    add_quick_capture_rule,
    default_config_path,
    save_config,
    update_config,
)
from .diagnostics import DiagnosticCheck, run_diagnostics
from .hotkey import normalize_hotkey_name
from .windows_entry import (
    GuiAutostartOptions,
    remove_gui_autostart_launcher,
    resolve_startup_script_path,
    write_gui_autostart_launcher,
)

_SUBMIT_STRATEGY_LABELS = {
    "clipboard_paste": "自动粘贴到当前光标",
    "clipboard_only": "只复制到剪贴板",
    "type_text": "模拟键盘逐字输入",
}
_API_PRESET_LABELS = {
    "clean": "口语整理 clean",
    "formal": "正式改写 formal",
    "todo": "提取待办 todo",
    "translate": "翻译成中文 translate",
}
_DEVICE_CHOICE_NAME_MAX = 30
_NO_INPUT_DEVICE_PLACEHOLDER = "未识别到输入设备"
_MISSING_INPUT_DEVICE_SUFFIX = "已保存设备；当前未识别到输入设备"
_MISSING_SAVED_DEVICE_SUFFIX = "已保存设备；不在最新列表里"

_HOTKEY_LABELS = {
    "caps_lock": "Caps Lock",
    "right ctrl": "右 Ctrl",
    "left ctrl": "左 Ctrl",
    "right alt": "右 Alt",
    "left alt": "左 Alt",
    "right shift": "右 Shift",
    "left shift": "左 Shift",
    "space": "空格",
    "enter": "回车",
    "tab": "Tab",
    "esc": "Esc",
}


@dataclass(frozen=True)
class GuiState:
    config_path: str
    captures_dir: str
    notes_dir: str
    language: str
    input_device: int | str | None
    hold_to_talk: str
    submit_strategy: str
    recommended_model_id: str
    recommended_backend: str
    recommendation_reason: str
    model_help: str
    doctor_ok: bool
    doctor_summary: str
    doctor_help: str
    settings_summary: str
    autostart_enabled: bool
    autostart_summary: str
    autostart_help: str
    device_help: str
    language_help: str
    hotkey_help: str
    hotkey_mode_summary: str
    submit_help: str
    api_process_enabled: bool
    api_preset: str
    api_fallback_raw: bool
    api_processing_summary: str
    api_processing_help: str
    api_provider_status: str
    api_context_summary: str
    api_context_help: str
    quick_note_enabled: bool
    quick_note_summary: str
    quick_note_help: str
    devices: tuple[dict, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HotkeyCheckResult:
    ok: bool
    message: str


def build_gui_state(
    app,
    *,
    config_path: str | Path | None = None,
    captures_dir: str | Path | None = None,
    devices: Sequence[AudioInputDevice] | None = None,
    diagnostics: Sequence[DiagnosticCheck] | None = None,
    autostart_path: str | Path | None = None,
    autostart_enabled: bool | None = None,
) -> GuiState:
    config_file = Path(config_path) if config_path else default_config_path()
    captures_root = Path(captures_dir) if captures_dir else Path("captures")
    notes_root = Path(app.config.quick_capture.root_dir)
    recommendation = app.recommend_model(app.config.selection)
    resolved_devices = _dedupe_devices(tuple(devices) if devices is not None else list_input_devices())
    checks = tuple(diagnostics) if diagnostics is not None else run_diagnostics(run_transcribe_smoke=False)
    failed = [check.name for check in checks if not check.ok]
    doctor_ok = not failed
    doctor_summary = _doctor_summary(checks)
    device_items = tuple(_device_to_dict(device) for device in resolved_devices)
    startup_script = Path(autostart_path) if autostart_path is not None else _default_autostart_path()
    startup_enabled = startup_script.exists() if autostart_enabled is None else autostart_enabled
    api_context_package = build_api_context_package(
        app.config,
        log_path=captures_root / "transcriptions.jsonl",
    )
    return GuiState(
        config_path=str(config_file),
        captures_dir=str(captures_root),
        notes_dir=str(notes_root),
        language=app.config.selection.language,
        input_device=app.config.audio.input_device,
        hold_to_talk=app.config.hotkey.hold_to_talk,
        submit_strategy=app.config.hotkey.submit_strategy,
        recommended_model_id=recommendation.profile.model_id,
        recommended_backend=recommendation.profile.backend,
        recommendation_reason=recommendation.reason,
        model_help=_model_help(
            recommendation.profile.model_id,
            recommendation.profile.backend,
            recommendation.reason,
        ),
        doctor_ok=doctor_ok,
        doctor_summary=doctor_summary,
        doctor_help=_doctor_help(checks),
        settings_summary=_settings_summary(
            language=app.config.selection.language,
            input_device=app.config.audio.input_device,
            hold_to_talk=app.config.hotkey.hold_to_talk,
            submit_strategy=app.config.hotkey.submit_strategy,
            api_process_enabled=app.config.api_processing.enabled,
            api_preset=app.config.api_processing.preset,
            api_fallback_raw=app.config.api_processing.fallback_raw,
            quick_note_enabled=app.config.quick_capture.enabled,
            devices=device_items,
        ),
        autostart_enabled=startup_enabled,
        autostart_summary=_autostart_summary(startup_enabled),
        autostart_help=_autostart_help(startup_enabled, startup_script),
        device_help=_device_help(device_items, app.config.audio.input_device),
        language_help=_language_help(app.config.selection.language),
        hotkey_help=_hotkey_help(app.config.hotkey.hold_to_talk),
        hotkey_mode_summary=_hotkey_mode_summary(app.config.hotkey.hold_to_talk),
        submit_help=_submit_strategy_help(app.config.hotkey.submit_strategy),
        api_process_enabled=app.config.api_processing.enabled,
        api_preset=app.config.api_processing.preset,
        api_fallback_raw=app.config.api_processing.fallback_raw,
        api_processing_summary=_api_processing_summary(
            app.config.api_processing.enabled,
            app.config.api_processing.preset,
            app.config.api_processing.fallback_raw,
        ),
        api_processing_help=_api_processing_help(
            app.config.api_processing.enabled,
            app.config.api_processing.preset,
            app.config.api_processing.fallback_raw,
        ),
        api_provider_status=_api_provider_status(app.config.api_provider),
        api_context_summary=_api_context_summary(app.config, api_context_package),
        api_context_help=_api_context_help(app.config, api_context_package),
        quick_note_enabled=app.config.quick_capture.enabled,
        quick_note_summary=_quick_note_summary(app.config),
        quick_note_help=_quick_note_help(app.config),
        devices=device_items,
    )


def apply_gui_settings(
    config: AppConfig,
    *,
    language: str,
    input_device_text: str,
    hold_to_talk: str,
    submit_strategy: str,
    api_process_enabled: bool | None = None,
    api_preset: str | None = None,
    api_fallback_raw: bool | None = None,
    quick_note_enabled: bool | None = None,
) -> AppConfig:
    return update_config(
        config,
        language=language.strip() or config.selection.language,
        input_device=_parse_input_device_text(input_device_text),
        hold_to_talk=hold_to_talk.strip() or config.hotkey.hold_to_talk,
        submit_strategy=_parse_submit_strategy_text(submit_strategy) or config.hotkey.submit_strategy,
        api_process_enabled=api_process_enabled,
        api_preset=_parse_api_preset_text(api_preset or config.api_processing.preset),
        api_fallback_raw=api_fallback_raw,
        quick_capture_enabled=quick_note_enabled,
    )


def add_quick_note_rule_from_gui(
    config: AppConfig,
    *,
    name: str,
    keyword: str,
    target_dir: str,
    keep_keyword: bool,
) -> AppConfig:
    rule_name = name.strip()
    clean_keyword = keyword.strip()
    clean_target_dir = target_dir.strip()
    if not rule_name:
        raise ValueError("规则名称不能为空。")
    if not clean_keyword:
        raise ValueError("关键词不能为空。")
    if not clean_target_dir:
        raise ValueError("目标目录不能为空。")
    existing_names = {rule.name.strip().lower() for rule in config.quick_capture.rules if rule.name.strip()}
    if rule_name.lower() in existing_names:
        raise ValueError(f"规则名称已存在：{rule_name}。")
    return add_quick_capture_rule(
        config,
        name=rule_name,
        keywords=(clean_keyword,),
        target_dir=clean_target_dir,
        remove_keyword=False if keep_keyword else None,
    )


def remove_quick_note_rule_by_index_from_gui(config: AppConfig, index: int) -> AppConfig:
    rules = config.quick_capture.rules
    if index < 0 or index >= len(rules):
        raise ValueError("请选择要删除的快速记录规则。")
    quick_capture = replace(config.quick_capture, rules=rules[:index] + rules[index + 1 :])
    return replace(config, quick_capture=quick_capture)


def quick_note_rule_labels(config: AppConfig) -> tuple[str, ...]:
    return tuple(
        _quick_note_rule_label(index, rule, global_remove_keyword=config.quick_capture.remove_keyword)
        for index, rule in enumerate(config.quick_capture.rules)
    )


def _quick_note_rule_label(index: int, rule, *, global_remove_keyword: bool) -> str:
    name = rule.name or "未命名"
    keywords = "、".join(keyword for keyword in rule.keywords if keyword.strip()) or "未设置关键词"
    target_dir = rule.target_dir or "未设置目录"
    remove_keyword = _quick_note_rule_remove_keyword_label(rule.remove_keyword, global_remove_keyword)
    return f"{index + 1}. {name} | 关键词：{keywords} | 目录：{target_dir} | {remove_keyword}"


def _quick_note_rule_remove_keyword_label(value: bool | None, global_remove_keyword: bool) -> str:
    if value is None:
        inherited = "移除关键词" if global_remove_keyword else "保留关键词"
        return f"跟随全局：{inherited}"
    if value:
        return "移除关键词"
    return "保留关键词"


def launch_gui(app, *, config_path: str | Path | None = None) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError as exc:
        raise RuntimeError("tkinter is not available in this Python environment.") from exc

    gui_lock = _try_acquire_gui_single_instance_lock()
    if gui_lock is None:
        return
    gui_lock_ref = {"handle": gui_lock}

    config_file = Path(config_path) if config_path else default_config_path()
    state = build_gui_state(app, config_path=config_file)

    try:
        root = tk.Tk()
    except Exception:
        _release_gui_lock_ref(gui_lock_ref)
        raise
    root.title("Open Voice Input")
    root.resizable(False, False)
    root.columnconfigure(1, weight=1)

    language_var = tk.StringVar(value=state.language)
    device_var = tk.StringVar()
    hotkey_var = tk.StringVar(value=state.hold_to_talk)
    submit_var = tk.StringVar(value=_display_submit_strategy(state.submit_strategy))
    model_var = tk.StringVar(value=state.recommended_model_id)
    model_help_var = tk.StringVar(value=state.model_help)
    doctor_var = tk.StringVar(value=state.doctor_summary)
    doctor_help_var = tk.StringVar(value=state.doctor_help)
    summary_var = tk.StringVar(value=state.settings_summary)
    autostart_var = tk.StringVar(value=state.autostart_summary)
    autostart_help_var = tk.StringVar(value=state.autostart_help)
    device_help_var = tk.StringVar(value=state.device_help)
    language_help_var = tk.StringVar(value=state.language_help)
    hotkey_help_var = tk.StringVar(value=state.hotkey_help)
    hotkey_mode_var = tk.StringVar(value=state.hotkey_mode_summary)
    submit_help_var = tk.StringVar(value=state.submit_help)
    api_process_var = tk.BooleanVar(value=state.api_process_enabled)
    api_preset_var = tk.StringVar(value=_display_api_preset(state.api_preset))
    api_fallback_var = tk.BooleanVar(value=state.api_fallback_raw)
    api_help_var = tk.StringVar(value=state.api_processing_help)
    api_provider_var = tk.StringVar(value=state.api_provider_status)
    api_context_var = tk.StringVar(value=state.api_context_summary)
    api_context_help_var = tk.StringVar(value=state.api_context_help)
    quick_note_enabled_var = tk.BooleanVar(value=state.quick_note_enabled)
    quick_note_var = tk.StringVar(value=state.quick_note_summary)
    quick_note_help_var = tk.StringVar(value=state.quick_note_help)
    quick_rule_name_var = tk.StringVar()
    quick_rule_keyword_var = tk.StringVar()
    quick_rule_target_var = tk.StringVar()
    quick_rule_keep_keyword_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value=_status_ready())
    hold_process = {"process": None}

    ttk.Label(root, text="推荐模型").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
    ttk.Label(root, textvariable=model_var).grid(row=0, column=1, sticky="w", padx=10, pady=(10, 4))
    ttk.Label(root, textvariable=model_help_var, wraplength=320, justify="left").grid(
        row=1, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="环境体检").grid(row=2, column=0, sticky="w", padx=10, pady=4)
    ttk.Label(root, textvariable=doctor_var).grid(row=2, column=1, sticky="w", padx=10, pady=4)
    ttk.Label(root, textvariable=doctor_help_var, wraplength=320, justify="left").grid(
        row=3, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="当前设置").grid(row=4, column=0, sticky="nw", padx=10, pady=4)
    ttk.Label(root, textvariable=summary_var, wraplength=320, justify="left").grid(
        row=4, column=1, sticky="w", padx=10, pady=4
    )

    ttk.Label(root, text="语言").grid(row=5, column=0, sticky="w", padx=10, pady=4)
    ttk.Entry(root, textvariable=language_var, width=24).grid(row=5, column=1, sticky="ew", padx=10, pady=4)
    ttk.Label(root, textvariable=language_help_var, wraplength=320, justify="left").grid(
        row=6, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="输入设备").grid(row=7, column=0, sticky="w", padx=10, pady=4)
    device_box = ttk.Combobox(root, textvariable=device_var, values=(), width=40)
    device_box.grid(row=7, column=1, sticky="ew", padx=10, pady=4)
    _sync_device_widgets(device_var, device_box, state.input_device, state.devices)
    ttk.Label(root, textvariable=device_help_var, wraplength=320, justify="left").grid(
        row=8, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="热键").grid(row=9, column=0, sticky="w", padx=10, pady=4)
    ttk.Entry(root, textvariable=hotkey_var, width=24).grid(row=9, column=1, sticky="ew", padx=10, pady=4)
    ttk.Label(root, textvariable=hotkey_mode_var, wraplength=320, justify="left").grid(
        row=10, column=1, sticky="w", padx=10, pady=(0, 4)
    )
    ttk.Label(root, textvariable=hotkey_help_var, wraplength=320, justify="left").grid(
        row=11, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="提交方式").grid(row=12, column=0, sticky="w", padx=10, pady=4)
    ttk.Combobox(
        root,
        textvariable=submit_var,
        values=_submit_strategy_choices(),
        width=28,
        state="readonly",
    ).grid(row=12, column=1, sticky="ew", padx=10, pady=4)
    ttk.Label(root, textvariable=submit_help_var, wraplength=320, justify="left").grid(
        row=13, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="API 整理").grid(row=14, column=0, sticky="w", padx=10, pady=4)
    api_frame = ttk.Frame(root)
    api_frame.grid(row=14, column=1, sticky="ew", padx=10, pady=4)
    api_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(api_frame, text="启用", variable=api_process_var).grid(row=0, column=0, sticky="w")
    ttk.Combobox(
        api_frame,
        textvariable=api_preset_var,
        values=_api_preset_choices(),
        width=18,
        state="readonly",
    ).grid(row=0, column=1, sticky="ew", padx=6)
    ttk.Checkbutton(api_frame, text="失败退回原文", variable=api_fallback_var).grid(row=0, column=2, sticky="w")
    ttk.Label(root, textvariable=api_help_var, wraplength=320, justify="left").grid(
        row=15, column=1, sticky="w", padx=10, pady=(0, 4)
    )
    ttk.Label(root, textvariable=api_provider_var, wraplength=320, justify="left").grid(
        row=16, column=1, sticky="w", padx=10, pady=(0, 4)
    )
    ttk.Label(root, textvariable=api_context_var, wraplength=320, justify="left").grid(
        row=17, column=1, sticky="w", padx=10, pady=(0, 4)
    )
    ttk.Label(root, textvariable=api_context_help_var, wraplength=320, justify="left").grid(
        row=18, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="快速记录").grid(row=19, column=0, sticky="w", padx=10, pady=4)
    quick_note_frame = ttk.Frame(root)
    quick_note_frame.grid(row=19, column=1, sticky="ew", padx=10, pady=4)
    quick_note_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(quick_note_frame, text="启用", variable=quick_note_enabled_var).grid(row=0, column=0, sticky="w")
    ttk.Label(quick_note_frame, textvariable=quick_note_var, wraplength=260, justify="left").grid(
        row=0, column=1, sticky="w", padx=(6, 0)
    )
    ttk.Label(quick_note_frame, text="规则列表").grid(row=1, column=0, sticky="nw", pady=(6, 0))
    quick_rule_listbox = tk.Listbox(quick_note_frame, height=3, width=46, exportselection=False)
    quick_rule_listbox.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(6, 0))
    _sync_quick_rule_listbox(quick_rule_listbox, app.config)
    ttk.Label(quick_note_frame, text="规则名").grid(row=2, column=0, sticky="w", pady=(6, 0))
    ttk.Entry(quick_note_frame, textvariable=quick_rule_name_var, width=22).grid(
        row=2, column=1, sticky="ew", padx=(6, 0), pady=(6, 0)
    )
    ttk.Label(quick_note_frame, text="关键词").grid(row=3, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(quick_note_frame, textvariable=quick_rule_keyword_var, width=22).grid(
        row=3, column=1, sticky="ew", padx=(6, 0), pady=(4, 0)
    )
    ttk.Label(quick_note_frame, text="目标目录").grid(row=4, column=0, sticky="w", pady=(4, 0))
    ttk.Entry(quick_note_frame, textvariable=quick_rule_target_var, width=22).grid(
        row=4, column=1, sticky="ew", padx=(6, 0), pady=(4, 0)
    )
    quick_rule_action_frame = ttk.Frame(quick_note_frame)
    quick_rule_action_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    quick_rule_action_frame.columnconfigure(1, weight=1)
    ttk.Checkbutton(quick_rule_action_frame, text="保留关键词", variable=quick_rule_keep_keyword_var).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Button(quick_rule_action_frame, text="新增规则", command=lambda: add_quick_rule()).grid(
        row=0, column=1, sticky="ew", padx=(8, 0)
    )
    ttk.Button(quick_rule_action_frame, text="删除选中规则", command=lambda: delete_quick_rule()).grid(
        row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0)
    )
    ttk.Label(root, textvariable=quick_note_help_var, wraplength=320, justify="left").grid(
        row=20, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    ttk.Label(root, text="开机自启").grid(row=21, column=0, sticky="w", padx=10, pady=4)
    ttk.Label(root, textvariable=autostart_var).grid(row=21, column=1, sticky="w", padx=10, pady=4)
    ttk.Label(root, textvariable=autostart_help_var, wraplength=320, justify="left").grid(
        row=22, column=1, sticky="w", padx=10, pady=(0, 4)
    )

    button_frame = ttk.Frame(root)
    button_frame.grid(row=23, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 4))
    for index in range(2):
        button_frame.columnconfigure(index, weight=1)

    def apply_state(new_state: GuiState) -> None:
        nonlocal state
        state = new_state
        model_var.set(state.recommended_model_id)
        model_help_var.set(state.model_help)
        doctor_var.set(state.doctor_summary)
        doctor_help_var.set(state.doctor_help)
        summary_var.set(state.settings_summary)
        autostart_var.set(state.autostart_summary)
        autostart_help_var.set(state.autostart_help)
        device_help_var.set(state.device_help)
        language_help_var.set(state.language_help)
        hotkey_help_var.set(state.hotkey_help)
        hotkey_mode_var.set(state.hotkey_mode_summary)
        _sync_device_widgets(device_var, device_box, state.input_device, state.devices)
        submit_var.set(_display_submit_strategy(state.submit_strategy))
        submit_help_var.set(state.submit_help)
        api_process_var.set(state.api_process_enabled)
        api_preset_var.set(_display_api_preset(state.api_preset))
        api_fallback_var.set(state.api_fallback_raw)
        api_help_var.set(state.api_processing_help)
        api_provider_var.set(state.api_provider_status)
        api_context_var.set(state.api_context_summary)
        api_context_help_var.set(state.api_context_help)
        quick_note_enabled_var.set(state.quick_note_enabled)
        quick_note_var.set(state.quick_note_summary)
        quick_note_help_var.set(state.quick_note_help)
        _sync_quick_rule_listbox(quick_rule_listbox, app.config)

    def sync_language_help(*_args) -> None:
        language_help_var.set(_language_help(language_var.get()))

    language_var.trace_add("write", sync_language_help)

    def sync_submit_help(*_args) -> None:
        submit_help_var.set(_submit_strategy_help(submit_var.get()))

    submit_var.trace_add("write", sync_submit_help)

    def sync_api_help(*_args) -> None:
        api_help_var.set(
            _api_processing_help(
                api_process_var.get(),
                _parse_api_preset_text(api_preset_var.get()),
                api_fallback_var.get(),
            )
        )

    api_process_var.trace_add("write", sync_api_help)
    api_preset_var.trace_add("write", sync_api_help)
    api_fallback_var.trace_add("write", sync_api_help)

    def sync_hotkey_help(*_args) -> None:
        hotkey_help_var.set(_hotkey_help(hotkey_var.get()))
        hotkey_mode_var.set(_hotkey_mode_summary(hotkey_var.get()))

    hotkey_var.trace_add("write", sync_hotkey_help)

    def refresh() -> None:
        try:
            apply_state(build_gui_state(app, config_path=config_file))
        except Exception as exc:
            status_var.set(_status_action_error("重新检查状态", exc))
            return
        status_var.set(_status_after_check(state.doctor_ok, state.doctor_summary))

    def save() -> None:
        try:
            updated = apply_gui_settings(
                app.config,
                language=language_var.get(),
                input_device_text=device_var.get(),
                hold_to_talk=hotkey_var.get(),
                submit_strategy=submit_var.get(),
                api_process_enabled=api_process_var.get(),
                api_preset=api_preset_var.get(),
                api_fallback_raw=api_fallback_var.get(),
                quick_note_enabled=quick_note_enabled_var.get(),
            )
            save_config(updated, config_file)
            app.config = updated
            apply_state(build_gui_state(app, config_path=config_file))
        except Exception as exc:
            status_var.set(_status_action_error("保存当前设置", exc))
            return
        status_var.set(_status_action_success("已保存当前设置", str(config_file)))

    def add_quick_rule() -> None:
        try:
            base = apply_gui_settings(
                app.config,
                language=language_var.get(),
                input_device_text=device_var.get(),
                hold_to_talk=hotkey_var.get(),
                submit_strategy=submit_var.get(),
                api_process_enabled=api_process_var.get(),
                api_preset=api_preset_var.get(),
                api_fallback_raw=api_fallback_var.get(),
                quick_note_enabled=quick_note_enabled_var.get(),
            )
            updated = add_quick_note_rule_from_gui(
                base,
                name=quick_rule_name_var.get(),
                keyword=quick_rule_keyword_var.get(),
                target_dir=quick_rule_target_var.get(),
                keep_keyword=quick_rule_keep_keyword_var.get(),
            )
            save_config(updated, config_file)
            app.config = updated
            apply_state(build_gui_state(app, config_path=config_file))
        except Exception as exc:
            status_var.set(_status_action_error("新增快速记录规则", exc))
            return
        quick_rule_name_var.set("")
        quick_rule_keyword_var.set("")
        quick_rule_target_var.set("")
        quick_rule_keep_keyword_var.set(False)
        status_var.set(_status_action_success("已新增快速记录规则", str(config_file)))

    def delete_quick_rule() -> None:
        selection = quick_rule_listbox.curselection()
        if not selection:
            status_var.set(_status_action_error("删除快速记录规则", ValueError("请先在规则列表里选中一条规则。")))
            return
        try:
            base = apply_gui_settings(
                app.config,
                language=language_var.get(),
                input_device_text=device_var.get(),
                hold_to_talk=hotkey_var.get(),
                submit_strategy=submit_var.get(),
                api_process_enabled=api_process_var.get(),
                api_preset=api_preset_var.get(),
                api_fallback_raw=api_fallback_var.get(),
                quick_note_enabled=quick_note_enabled_var.get(),
            )
            updated = remove_quick_note_rule_by_index_from_gui(base, selection[0])
            save_config(updated, config_file)
            app.config = updated
            apply_state(build_gui_state(app, config_path=config_file))
        except Exception as exc:
            status_var.set(_status_action_error("删除快速记录规则", exc))
            return
        status_var.set(_status_action_success("已删除选中的快速记录规则", "只删除规则，不删除已经保存的笔记文件"))

    def enable_autostart() -> None:
        startup_path = _default_autostart_path()
        try:
            write_gui_autostart_launcher(
                startup_path,
                GuiAutostartOptions(
                    cwd=Path.cwd(),
                    pythonw_command=_gui_python_command(),
                    config_path=config_file,
                ),
                overwrite=True,
            )
            apply_state(build_gui_state(app, config_path=config_file))
        except Exception as exc:
            status_var.set(_status_action_error("启用开机自启", exc))
            return
        status_var.set(_status_action_success("已启用开机自启", str(startup_path)))

    def disable_autostart() -> None:
        startup_path = _default_autostart_path()
        try:
            removed = remove_gui_autostart_launcher(startup_path)
            apply_state(build_gui_state(app, config_path=config_file))
        except Exception as exc:
            status_var.set(_status_action_error("关闭开机自启", exc))
            return
        if removed:
            status_var.set(_status_action_success("已关闭开机自启", str(startup_path)))
        else:
            status_var.set(_status_action_success("开机自启本来就没有启用"))

    def launch_hold_to_talk() -> None:
        log_path = _hold_to_talk_log_path(state.captures_dir)
        if _process_is_running(hold_process["process"]):
            status_var.set(
                _status_action_success(
                    "按住说话已经在后台运行",
                    f"PID {hold_process['process'].pid}；日志写入 {log_path}",
                )
            )
            return
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("ab") as log_file:
                process = subprocess.Popen(
                    _hold_to_talk_command(config_file, app.config),
                    cwd=str(Path.cwd()),
                    stdout=log_file,
                    stderr=log_file,
                    creationflags=_windows_hidden_creationflags(),
                )
            returncode = _wait_for_quick_exit(process)
            if returncode is not None:
                detail = _hold_to_talk_start_failure_detail(returncode, log_path)
                status_var.set(_status_action_success("按住说话启动后立刻退出", detail))
                return
            hold_process["process"] = process
        except Exception as exc:
            status_var.set(_status_action_error("启动按住说话", exc))
            return
        status_var.set(
            _status_action_success(
                "已在后台启动按住说话",
                f"PID {process.pid}；可以按住热键开始录音；日志写入 {log_path}",
            )
        )

    def stop_hold_to_talk() -> None:
        process = hold_process["process"]
        if not _process_is_running(process):
            hold_process["process"] = None
            status_var.set(_status_action_success("按住说话当前没有后台进程"))
            return
        try:
            _terminate_process(process)
        except Exception as exc:
            status_var.set(_status_action_error("停止按住说话", exc))
            return
        hold_process["process"] = None
        status_var.set(_status_action_success("已停止后台按住说话"))

    def check_hotkey() -> None:
        result = _check_hotkey_registration(hotkey_var.get())
        status_var.set(_status_action_success("热键检查", result.message))

    def recommend_hotkey() -> None:
        recommended = _recommended_hotkey()
        hotkey_var.set(recommended)
        status_var.set(_status_action_success("已填入推荐热键", _recommended_hotkey_reason(recommended)))

    def open_config_dir() -> None:
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
            _open_path(config_file.parent)
        except Exception as exc:
            status_var.set(_status_action_error("打开配置文件夹", exc))
            return
        status_var.set(_status_action_success("已打开配置文件夹"))

    def open_captures_dir() -> None:
        try:
            path = Path(state.captures_dir)
            path.mkdir(parents=True, exist_ok=True)
            _open_path(path)
        except Exception as exc:
            status_var.set(_status_action_error("打开识别结果目录", exc))
            return
        status_var.set(_status_action_success("已打开识别结果目录"))

    def quit_panel() -> None:
        _release_gui_lock_ref(gui_lock_ref)
        root.destroy()

    ttk.Button(button_frame, text="保存当前设置", command=save).grid(row=0, column=0, sticky="ew", padx=(0, 6))
    ttk.Button(button_frame, text="重新检查状态", command=refresh).grid(row=0, column=1, sticky="ew")
    ttk.Button(button_frame, text="启用开机自启", command=enable_autostart).grid(
        row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 0)
    )
    ttk.Button(button_frame, text="关闭开机自启", command=disable_autostart).grid(
        row=1, column=1, sticky="ew", pady=(6, 0)
    )
    ttk.Button(button_frame, text="检查热键冲突", command=check_hotkey).grid(
        row=2, column=0, sticky="ew", padx=(0, 6), pady=(6, 0)
    )
    ttk.Button(button_frame, text="推荐低冲突热键", command=recommend_hotkey).grid(
        row=2, column=1, sticky="ew", pady=(6, 0)
    )

    action_frame = ttk.Frame(root)
    action_frame.grid(row=24, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
    for index in range(3):
        action_frame.columnconfigure(index, weight=1)

    ttk.Button(action_frame, text="启动按住说话", command=launch_hold_to_talk).grid(
        row=0, column=0, sticky="ew", padx=(0, 6)
    )
    ttk.Button(action_frame, text="停止按住说话", command=stop_hold_to_talk).grid(
        row=0, column=1, sticky="ew", padx=6
    )
    ttk.Button(action_frame, text="退出面板", command=quit_panel).grid(
        row=0, column=2, sticky="ew", padx=(6, 0)
    )
    ttk.Button(action_frame, text="打开配置文件夹", command=open_config_dir).grid(
        row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 0)
    )
    ttk.Button(action_frame, text="打开识别结果目录", command=open_captures_dir).grid(
        row=1, column=1, columnspan=2, sticky="ew", padx=(6, 0), pady=(6, 0)
    )

    ttk.Label(root, textvariable=status_var, wraplength=420, justify="left").grid(
        row=25, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 2)
    )
    ttk.Label(root, text="提示：点右上角关闭会缩到任务栏，不会退出。", wraplength=420, justify="left").grid(
        row=26, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10)
    )
    root.protocol("WM_DELETE_WINDOW", quit_panel)
    try:
        root.mainloop()
    finally:
        _release_gui_lock_ref(gui_lock_ref)


def _device_to_dict(device: AudioInputDevice) -> dict:
    return {
        "index": device.index,
        "name": device.name,
        "max_input_channels": device.max_input_channels,
        "default_sample_rate": device.default_sample_rate,
    }


def _device_choice_text(device: dict) -> str:
    return f"{device['index']}: {_truncate_device_name(device['name'])}"


def _device_choice_values(devices: Sequence[dict], input_device: int | str | None = None) -> tuple[str, ...]:
    if not devices:
        return (_current_device_text(input_device, devices),)
    values = tuple(_device_choice_text(device) for device in devices)
    if input_device is not None and not _is_known_input_device(input_device, devices):
        return (_current_device_text(input_device, devices),) + values
    return values


def _current_device_text(value: int | str | None, devices: Sequence[dict]) -> str:
    if value is None:
        if not devices:
            return _NO_INPUT_DEVICE_PLACEHOLDER
        return ""
    try:
        index = int(value)
    except (TypeError, ValueError):
        return str(value)
    for device in devices:
        if device["index"] == index:
            return _device_choice_text(device)
    if not devices:
        return f"{index}: {_MISSING_INPUT_DEVICE_SUFFIX}"
    return f"{index}: {_MISSING_SAVED_DEVICE_SUFFIX}"


def _sync_device_widgets(device_var, device_widget, input_device: int | str | None, devices: Sequence[dict]) -> None:
    device_widget["values"] = _device_choice_values(devices, input_device)
    device_var.set(_current_device_text(input_device, devices))


def _sync_quick_rule_listbox(listbox, config: AppConfig) -> None:
    listbox.delete(0, "end")
    for label in quick_note_rule_labels(config):
        listbox.insert("end", label)


def _parse_input_device_text(raw: str) -> int | str | None:
    text = raw.strip()
    if text == _NO_INPUT_DEVICE_PLACEHOLDER:
        return None
    if not text:
        return None
    prefix = text.split(":", 1)[0].strip()
    try:
        return int(prefix)
    except ValueError:
        return text


def _truncate_device_name(name: str, max_length: int = _DEVICE_CHOICE_NAME_MAX) -> str:
    text = name.strip()
    if len(text) <= max_length:
        return text
    head = max_length // 2
    tail = max_length - head - 3
    return f"{text[:head].rstrip()}...{text[-tail:].lstrip()}"


def _open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))
        return
    subprocess.Popen(["xdg-open", str(path)])


def _default_autostart_path() -> Path:
    return resolve_startup_script_path()


def _gui_python_command() -> str:
    if os.name == "nt" and Path(r"C:\Windows\pyw.exe").exists():
        return "pyw"
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(executable)


def _console_python_executable() -> str:
    executable = Path(sys.executable)
    name = executable.name.lower()
    if name == "pythonw.exe":
        candidate = executable.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    if name == "pyw.exe":
        candidate = executable.with_name("py.exe")
        if candidate.exists():
            return str(candidate)
    return str(executable)


def _hold_to_talk_command(config_file: str | Path, config: AppConfig | None = None) -> list[str]:
    command = [
        _console_python_executable(),
        "-m",
        "local_voice_input",
        "--config",
        str(config_file),
        "hold-to-talk",
    ]
    if config is not None and config.api_processing.enabled:
        command.extend(["--api-process", "--api-preset", config.api_processing.preset])
        if config.api_processing.fallback_raw:
            command.append("--api-fallback-raw")
    if config is not None and config.quick_capture.enabled:
        command.append("--quick-note")
    return command


def _hold_to_talk_log_path(captures_dir: str | Path) -> Path:
    return Path(captures_dir) / "hold-to-talk.log"


def _process_is_running(process) -> bool:
    return process is not None and process.poll() is None


def _wait_for_quick_exit(process, timeout_s: float = 0.35) -> int | None:
    try:
        return process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None


def _terminate_process(process, timeout_s: float = 2.0) -> None:
    process.terminate()
    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout_s)


def _hold_to_talk_start_failure_detail(returncode: int, log_path: Path) -> str:
    tail = _read_text_tail(log_path)
    detail = f"退出码 {returncode}；日志写入 {log_path}"
    if tail:
        return f"{detail}；最后日志：{tail}"
    return detail


def _read_text_tail(path: str | Path, max_chars: int = 600) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:].strip()


def _windows_hidden_creationflags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _minimize_window(window) -> None:
    window.iconify()


def _try_acquire_gui_single_instance_lock(lock_path: Path | None = None):
    if os.name != "nt":
        return object()
    try:
        import msvcrt
    except ImportError:
        return object()

    path = lock_path or Path(tempfile.gettempdir()) / "OpenVoiceInput-MVP.gui.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def _release_gui_single_instance_lock(handle) -> None:
    if handle is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            try:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
    finally:
        handle.close()


def _release_gui_lock_ref(lock_ref: dict) -> None:
    handle = lock_ref.pop("handle", None)
    if handle is not None:
        _release_gui_single_instance_lock(handle)


def _dedupe_devices(devices: Sequence[AudioInputDevice]) -> tuple[AudioInputDevice, ...]:
    best_by_key: dict[tuple[str, int, int], AudioInputDevice] = {}
    for device in devices:
        key = (
            device.name.strip().lower(),
            device.max_input_channels,
            int(device.default_sample_rate),
        )
        existing = best_by_key.get(key)
        if existing is None or device.index < existing.index:
            best_by_key[key] = device
    return tuple(sorted(best_by_key.values(), key=lambda item: item.index))


def _doctor_summary(checks: Sequence[DiagnosticCheck]) -> str:
    failed = [check.name for check in checks if not check.ok]
    if failed:
        return "失败项目: " + ", ".join(failed)
    smoke = next((check for check in checks if check.name == "smoke:transcribe"), None)
    if smoke:
        return "已通过体检和转录冒烟测试"
    return "已通过基础体检"


def _doctor_help(checks: Sequence[DiagnosticCheck]) -> str:
    failed = [check.name for check in checks if not check.ok]
    if failed:
        return "这里会检查依赖、模型和音频设备；如果有失败项目，先处理这些基础问题，再试录音或转录。"
    smoke = next((check for check in checks if check.name == "smoke:transcribe"), None)
    if smoke and smoke.ok:
        return "这表示基础依赖、模型文件和一次非隐私的转录冒烟测试都已经跑通。"
    return "这表示基础依赖、模型文件和音频设备检查已经通过；还没做转录冒烟测试。"


def _autostart_summary(enabled: bool) -> str:
    return "已启用" if enabled else "未启用"


def _autostart_help(enabled: bool, path: Path) -> str:
    if enabled:
        return f"登录 Windows 后会自动打开语音输入面板。当前自启动脚本：{path}"
    return f"当前还没有开机自启。启用后会在登录 Windows 时自动打开语音输入面板。脚本位置：{path}"


def _quick_note_summary(config: AppConfig) -> str:
    quick = config.quick_capture
    enabled = "已启用" if quick.enabled else "未启用"
    inbox = _display_note_dir(quick.root_dir, quick.inbox_dir)
    rule_count = len(quick.rules)
    if rule_count:
        names = ", ".join(rule.name or "未命名" for rule in quick.rules[:3])
        if rule_count > 3:
            names = f"{names}..."
        return f"快速记录：{enabled}；规则 {rule_count} 条；未命中存到 {inbox}；规则：{names}。"
    return f"快速记录：{enabled}；规则 0 条；未命中会存到 {inbox}。"


def _quick_note_help(config: AppConfig) -> str:
    quick = config.quick_capture
    if quick.rules:
        prefix = "勾选启用后，" if not quick.enabled else ""
        return (
            f"{prefix}说话内容开头附近命中关键词时，会按规则保存；默认匹配窗口 {quick.match_window_chars} 个字符。"
            "没有命中关键词时，会进 inbox。"
        )
    if quick.enabled:
        return "已启用快速记录，但还没有规则；所有快速记录都会先进入 inbox。可以在面板里新增规则，也可以用 quick-rule add 配关键词和目标文件夹。"
    return "还没有启用快速记录，也还没有规则。启用后会先用 inbox 兜底；可以在面板里新增规则，也可以用 quick-rule add 配关键词和目标文件夹。"


def _display_note_dir(root_dir: str, configured_dir: str) -> str:
    root = Path(root_dir)
    directory = Path(configured_dir)
    if directory.is_absolute():
        return str(directory)
    if directory.parts and root.name and directory.parts[0].lower() == root.name.lower():
        return str(directory)
    return str(root / directory)


def _settings_summary(
    *,
    language: str,
    input_device: int | str | None,
    hold_to_talk: str,
    submit_strategy: str,
    api_process_enabled: bool,
    api_preset: str,
    api_fallback_raw: bool,
    quick_note_enabled: bool,
    devices: Sequence[dict],
) -> str:
    device_text = _display_input_device(input_device, devices)
    quick_note_text = "已启用" if quick_note_enabled else "未启用"
    summary = (
        f"语言：{_display_language(language)}  |  输入设备：{device_text}\n"
        f"热键：{_display_hotkey(hold_to_talk)}  |  提交方式：{_display_submit_strategy(submit_strategy)}\n"
        f"API 整理：{_api_processing_summary(api_process_enabled, api_preset, api_fallback_raw)}\n"
        f"快速记录：{quick_note_text}"
    )
    if input_device is not None and not _is_known_input_device(input_device, devices):
        if devices:
            return (
                f"{summary}\n"
                "提醒：保存设备不在列表里\n"
                f"可选项：{len(devices)} 个\n"
                "操作：下拉切换"
            )
        return f"{summary}\n提醒：保存设备不在列表里。"
    if input_device is None and not devices:
        return f"{summary}\n提醒：当前没有识别到任何输入设备。"
    return summary


def _device_help(devices: Sequence[dict], selected: int | str | None) -> str:
    base = "直接选“编号: 名称”。留空继续用自动/系统默认设备。"
    if selected is not None:
        if not _is_known_input_device(selected, devices):
            next_step = (
                f"可选项：{len(devices)} 个\n操作：下拉切换"
                if devices
                else "可以重新选择，或留空改回自动/系统默认设备。"
            )
            return (
                f"{base}\n\n"
                f"已保存：{selected}。\n\n"
                "提醒：不在最新列表里，可能已断开、改名或暂不可用。\n\n"
                f"{next_step}"
            )
        return f"{base} 当前保存的是：{_display_input_device(selected, devices)}。"
    if devices:
        return f"{base} 当前共识别到 {len(devices)} 个去重后的输入设备。"
    return (
        f"{base} 当前没有识别到任何输入设备。请检查麦克风、蓝牙耳机或虚拟声卡是否已连接，"
        "必要时重新插拔或切换设备后，再点“重新检查状态”试一次。"
    )


def _is_known_input_device(value: int | str | None, devices: Sequence[dict]) -> bool:
    if value is None:
        return False
    try:
        index = int(value)
    except (TypeError, ValueError):
        return False
    return any(device["index"] == index for device in devices)


def _display_input_device(value: int | str | None, devices: Sequence[dict]) -> str:
    if value is None:
        return "自动/系统默认"
    try:
        index = int(value)
    except (TypeError, ValueError):
        return str(value)
    for device in devices:
        if device["index"] == index:
            return f"{index}: {device['name']}"
    return str(value)


def _status_ready() -> str:
    return "状态：准备就绪。"


def _status_after_check(doctor_ok: bool, doctor_summary: str) -> str:
    if doctor_ok:
        return f"状态：已完成检查。{doctor_summary}。"
    return f"状态：检查发现问题。{doctor_summary}。"


def _status_action_success(action: str, detail: str | None = None) -> str:
    if detail:
        return f"状态：{action}。{detail}。"
    return f"状态：{action}。"


def _status_action_error(action: str, exc: Exception) -> str:
    return f"状态：{action}失败。{exc}"


def _display_language(language: str) -> str:
    return "自动判断" if language == "auto" else language


def _language_help(language: str) -> str:
    normalized = language.strip().lower()
    if normalized == "auto" or not normalized:
        return "语言可填 auto、zh、en 等。auto 表示让程序自动判断，更适合平时中英混着说。"
    if normalized == "zh":
        return "当前固定为中文识别。适合你主要说中文，想减少自动判断带来的摇摆。"
    if normalized == "en":
        return "当前固定为英文识别。适合你主要说英文，想减少自动判断带来的误判。"
    return f"当前会按“{language}”处理。常见写法有 auto、zh、en，也可以按模型支持情况填别的语言代码。"


def _hotkey_help(hotkey: str) -> str:
    normalized = hotkey.strip().lower()
    if not normalized:
        return "这里可以自定义单键热键，例如 Caps Lock、F8、右 Ctrl。填好后可以点“检查热键冲突”。"
    if _looks_like_hotkey_combo(normalized):
        return "当前按住说话只支持单键热键，组合键先不支持。建议先用 F8、Caps Lock 或右 Ctrl。"
    if normalized == "caps_lock":
        return f"当前用的是 {_display_hotkey(hotkey)}。好按，但可能会和大小写切换打架；建议点“检查热键冲突”。"
    if normalized.startswith("f") and normalized[1:].isdigit():
        return f"当前用的是 {_display_hotkey(hotkey)}。功能键通常比较稳，适合当按住说话的热键。"
    if "ctrl" in normalized or "alt" in normalized or "shift" in normalized:
        return f"当前用的是 {_display_hotkey(hotkey)}。修饰键常见，但容易和复制、切换窗口或输入法快捷键叠在一起。"
    return f"当前用的是 {_display_hotkey(hotkey)}。建议点“检查热键冲突”，确认它能被当前环境注册。"


def _hotkey_mode_summary(hotkey: str) -> str:
    normalized = normalize_hotkey_name(hotkey)
    if not normalized:
        return "热键模式：未设置。当前版本需要一个单键热键。"
    if _looks_like_hotkey_combo(normalized):
        return "热键模式：组合键暂不支持。当前版本先做单键按住说话。"
    return "热键模式：单键按住说话。组合键先作为后续候选。"


def _recommended_hotkey() -> str:
    return "f8"


def _recommended_hotkey_reason(hotkey: str) -> str:
    return f"{_display_hotkey(hotkey)} 通常比 Caps Lock、Ctrl、Alt 这类按键更少影响日常输入。"


def _display_hotkey(hotkey: str) -> str:
    normalized = hotkey.strip().lower()
    if not normalized:
        return "未设置"
    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized.upper()
    return _HOTKEY_LABELS.get(normalized, hotkey)


def _check_hotkey_registration(hotkey: str, keyboard_module=None) -> HotkeyCheckResult:
    normalized = normalize_hotkey_name(hotkey)
    display = _display_hotkey(hotkey)
    if not normalized:
        return HotkeyCheckResult(False, "请先填写一个热键，例如 F8、Caps Lock 或右 Ctrl。")
    if _looks_like_hotkey_combo(normalized):
        return HotkeyCheckResult(False, "当前按住说话只支持单键热键；组合键之后再单独做。")

    warning = _known_hotkey_conflict_warning(normalized)
    keyboard = keyboard_module
    if keyboard is None:
        try:
            import keyboard as keyboard
        except ImportError:
            return HotkeyCheckResult(False, "缺少 keyboard 依赖，暂时无法做全局热键检查。")

    handler = None
    try:
        handler = keyboard.on_press_key(normalized, lambda _event: None, suppress=False)
    except Exception as exc:
        return HotkeyCheckResult(False, f"{display} 无法注册为全局热键：{exc}")
    finally:
        if handler is not None:
            _unhook_keyboard_handler(keyboard, handler)

    if warning:
        return HotkeyCheckResult(True, f"{display} 可以注册，但{warning}")
    return HotkeyCheckResult(True, f"{display} 可以注册为全局热键。")


def _looks_like_hotkey_combo(normalized_hotkey: str) -> bool:
    return "+" in normalized_hotkey or "," in normalized_hotkey


def _known_hotkey_conflict_warning(normalized_hotkey: str) -> str | None:
    if normalized_hotkey == "esc":
        return "它同时是退出键，不建议拿来做按住说话。"
    if normalized_hotkey == "caps lock":
        return "它可能会切换大小写，部分输入法也会占用它。"
    if normalized_hotkey in {"space", "enter", "tab", "backspace"}:
        return "它是高频输入键，容易在普通输入框里误触。"
    if normalized_hotkey in {"left ctrl", "right ctrl", "left alt", "right alt", "left shift", "right shift"}:
        return "它是修饰键，可能和输入法、复制粘贴或窗口切换习惯冲突。"
    if normalized_hotkey == "f1":
        return "F1 经常被软件当作帮助键，可能偶尔被占用。"
    return None


def _unhook_keyboard_handler(keyboard_module, handler) -> None:
    unhook = getattr(keyboard_module, "unhook", None)
    if unhook is not None:
        unhook(handler)
        return
    unhook_all = getattr(keyboard_module, "unhook_all", None)
    if unhook_all is not None:
        unhook_all()


def _model_help(model_id: str, backend: str, reason: str) -> str:
    lowered = reason.lower()
    if "dictation" in lowered:
        if "cpu" in lowered or "local" in lowered:
            return f"当前按听写优先和本机本地环境，先推荐 {model_id} 这类更轻、更稳的模型。"
        return f"当前按听写优先，先推荐 {model_id} 作为更稳妥的默认模型。"
    if "resource checks passed" in lowered:
        return f"当前资源检查通过，所以先推荐 {model_id} 作为默认模型。"
    if backend:
        return f"这是程序按当前任务和环境自动挑出来的推荐模型，当前后端是 {backend}。"
    return "这是程序按当前任务和环境自动挑出来的推荐模型。"


def _display_submit_strategy(value: str) -> str:
    return _SUBMIT_STRATEGY_LABELS.get(value, value)


def _parse_submit_strategy_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return stripped
    reverse = {label: key for key, label in _SUBMIT_STRATEGY_LABELS.items()}
    return reverse.get(stripped, stripped)


def _submit_strategy_choices() -> list[str]:
    return list(_SUBMIT_STRATEGY_LABELS.values())


def _submit_strategy_help(value: str) -> str:
    normalized = _parse_submit_strategy_text(value)
    if normalized == "clipboard_paste":
        return "自动粘贴：识别后会直接发 Ctrl+V 到当前光标，适合聊天框和普通输入框。"
    if normalized == "clipboard_only":
        return "只复制：结果只会放进剪贴板，不会自动粘贴，适合你想自己决定何时粘贴。"
    if normalized == "type_text":
        return "模拟输入：像键盘一样逐字输入，适合不方便用剪贴板的软件，但通常会更慢。"
    return "提交方式决定识别结果是自动粘贴、只复制，还是模拟键盘输入。"


def _display_api_preset(value: str) -> str:
    return _API_PRESET_LABELS.get(value, value)


def _parse_api_preset_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "clean"
    reverse = {label: key for key, label in _API_PRESET_LABELS.items()}
    return reverse.get(stripped, stripped)


def _api_preset_choices() -> list[str]:
    return [_display_api_preset(key) for key in sorted(POSTPROCESS_PRESETS)]


def _api_processing_summary(enabled: bool, preset: str, fallback_raw: bool) -> str:
    if not enabled:
        return "未启用"
    fallback = "失败退回原文" if fallback_raw else "失败时报错"
    return f"已启用，{_display_api_preset(preset)}，{fallback}"


def _api_processing_help(enabled: bool, preset: str, fallback_raw: bool) -> str:
    if not enabled:
        return "未启用时，语音识别出来的原始文字会直接输出，不会再交给 API 整理。"
    fallback = "如果 API 失败，会先用原始识别文本顶上。" if fallback_raw else "如果 API 失败，这次输出会报错，方便你发现配置问题。"
    return f"启用后会在本地识别完成后调用 API，用“{_display_api_preset(preset)}”处理文字。{fallback}"


def _api_context_summary(config: AppConfig, package: ApiContextPackage) -> str:
    context = config.api_context
    available_terms = _available_glossary_count(config)
    if context.mode == "lightweight":
        return (
            "增强上下文：轻量；"
            f"最近 {len(package.recent_texts)}/{context.recent_turns} 条；"
            f"术语表 {len(package.glossary_terms)} 条；上限 {context.max_context_chars} 字。"
        )
    if context.mode == "compressed":
        return (
            "增强上下文：压缩模式预留，当前未启用；"
            f"最近设置 {context.recent_turns} 条；术语表可用 {available_terms} 条。"
        )
    return f"增强上下文：未启用；最近 0 条；术语表可用 {available_terms} 条。"


def _api_context_help(config: AppConfig, package: ApiContextPackage) -> str:
    context = config.api_context
    if context.mode == "lightweight":
        if package.recent_texts:
            recent_note = f"当前已找到 {len(package.recent_texts)} 条可用最近文本。"
        else:
            recent_note = "当前日志里还没有可用最近文本，之后有新转写会自动进入上下文。"
        return (
            "轻量模式只把文字上下文发给 API：最近转写文本和术语表；不会发送音频或音频路径。"
            f"{recent_note}"
        )
    if context.mode == "compressed":
        return "压缩模式只是后续预留，V1 还不会发送长历史压缩摘要；建议先用轻量模式。"
    return "关闭时，API 只处理当前这一次识别文本，不会带最近转写或术语表。"


def _available_glossary_count(config: AppConfig) -> int:
    if not config.hotwords.enabled or not config.api_context.glossary_enabled:
        return 0
    return len({word.strip() for word in config.hotwords.words if word.strip()})


def _api_provider_status(
    config: ApiProviderConfig,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    provider = str(config.provider or "").strip() or "未设置"
    base_url = str(config.base_url or "").strip()
    model = str(config.model or "").strip()
    key_env = str(config.api_key_env or "").strip()

    missing = []
    if not base_url:
        missing.append("接口地址")
    if not model:
        missing.append("模型")
    if not key_env:
        missing.append("密钥环境变量")
        key_text = "未填"
    elif env.get(key_env):
        key_text = f"{key_env} 已设置"
    else:
        missing.append("密钥值")
        key_text = f"{key_env} 未设置"

    state = "已就绪" if not missing else "未就绪"
    base_text = "已填" if base_url else "未填"
    model_text = model or "未填"
    detail = (
        f"API 接口：{state}；provider={provider}；base_url={base_text}；"
        f"model={model_text}；key={key_text}"
    )
    if missing:
        return f"{detail}；缺少：{'、'.join(missing)}。"
    return f"{detail}。"
