import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.audio_capture import AudioInputDevice
from local_voice_input.config import (
    ApiContextConfig,
    ApiProviderConfig,
    AppConfig,
    HotkeyConfig,
    HotwordConfig,
    QuickCaptureConfig,
    QuickCaptureRule,
    SelectionRequest,
)
from local_voice_input.diagnostics import DiagnosticCheck
from local_voice_input.gui import (
    add_quick_note_rule_from_gui,
    quick_note_rule_labels,
    remove_quick_note_rule_by_index_from_gui,
    _api_context_help,
    _api_context_summary,
    _api_processing_help,
    _api_processing_summary,
    _api_provider_status,
    _api_preset_choices,
    _autostart_help,
    _autostart_summary,
    _check_hotkey_registration,
    _console_python_executable,
    _current_device_text,
    _dedupe_devices,
    _device_choice_text,
    _device_choice_values,
    _display_input_device,
    _display_submit_strategy,
    _display_hotkey,
    _doctor_help,
    _hotkey_help,
    _hotkey_mode_summary,
    _hold_to_talk_command,
    _hold_to_talk_start_failure_detail,
    _hold_to_talk_log_path,
    _is_known_input_device,
    _language_help,
    _model_help,
    _parse_api_preset_text,
    _parse_submit_strategy_text,
    _quick_note_help,
    _quick_note_summary,
    _submit_strategy_help,
    _status_action_error,
    _status_action_success,
    _status_after_check,
    _status_ready,
    _sync_device_widgets,
    _minimize_window,
    _process_is_running,
    _read_text_tail,
    _recommended_hotkey,
    _recommended_hotkey_reason,
    _release_gui_single_instance_lock,
    _terminate_process,
    _try_acquire_gui_single_instance_lock,
    _windows_hidden_creationflags,
    apply_gui_settings,
    build_gui_state,
)
from local_voice_input.model_selector import ModelProfile, SelectionResult


class FakeGuiApp:
    def __init__(self):
        self.config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
        )

    def recommend_model(self, _request=None):
        return SelectionResult(
            profile=ModelProfile(
                model_id="sensevoice-small-onnx-int8",
                display_name="SenseVoice Small ONNX INT8",
                backend="sherpa-onnx",
                min_ram_gb=3,
                recommended_ram_gb=4,
            ),
            reason="Selected for dictation.",
        )


class FakeStringVar:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakeWindow:
    def __init__(self):
        self.iconified = False
        self.destroyed = False

    def iconify(self):
        self.iconified = True

    def destroy(self):
        self.destroyed = True


class FakeKeyboard:
    def __init__(self, fail=False):
        self.fail = fail
        self.registered_key = None
        self.unhooked = None

    def on_press_key(self, key, callback, suppress=False):
        if self.fail:
            raise RuntimeError("busy")
        self.registered_key = key
        return "handler"

    def unhook(self, handler):
        self.unhooked = handler


class FakeProcess:
    def __init__(self, running=True):
        self.running = running
        self.terminated = False
        self.killed = False
        self.pid = 1234

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def kill(self):
        self.killed = True
        self.running = False

    def wait(self, timeout=None):
        if self.running:
            raise TimeoutError("still running")
        return 0


class GuiTests(unittest.TestCase):
    def test_build_gui_state_includes_recommendation_and_devices(self):
        app = FakeGuiApp()
        devices = (
            AudioInputDevice(index=1, name="Mic", max_input_channels=1, default_sample_rate=16000),
        )
        diagnostics = (
            DiagnosticCheck(name="audio:input_devices", ok=True, message="1 input device(s) found"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            state = build_gui_state(
                app,
                config_path=Path(temp_dir) / "config.json",
                captures_dir=Path(temp_dir) / "captures",
                devices=devices,
                diagnostics=diagnostics,
                autostart_path=Path(temp_dir) / "OpenVoiceInput GUI.vbs",
                autostart_enabled=False,
            )

        self.assertEqual(state.language, "zh")
        self.assertEqual(state.recommended_model_id, "sensevoice-small-onnx-int8")
        self.assertTrue(state.doctor_ok)
        self.assertEqual(state.devices[0]["index"], 1)
        self.assertIn("当前按听写优先", state.model_help)
        self.assertIn("基础依赖、模型文件和音频设备检查已经通过", state.doctor_help)
        self.assertIn("语言：zh", state.settings_summary)
        self.assertIn("热键：Caps Lock", state.settings_summary)
        self.assertIn("提交方式：自动粘贴到当前光标", state.settings_summary)
        self.assertFalse(state.api_process_enabled)
        self.assertEqual(state.api_preset, "clean")
        self.assertFalse(state.api_fallback_raw)
        self.assertIn("API 整理", state.settings_summary)
        self.assertIn("未启用", state.api_processing_summary)
        self.assertIn("原始文字", state.api_processing_help)
        self.assertIn("API 接口：未就绪", state.api_provider_status)
        self.assertIn("增强上下文：未启用", state.api_context_summary)
        self.assertIn("只处理当前这一次识别文本", state.api_context_help)
        self.assertFalse(state.quick_note_enabled)
        self.assertIn("快速记录：未启用", state.quick_note_summary)
        self.assertIn("规则 0 条", state.quick_note_summary)
        self.assertIn("notes", state.quick_note_summary)
        self.assertIn("inbox", state.quick_note_summary)
        self.assertIn("快速记录：未启用", state.settings_summary)
        self.assertIn("直接选“编号: 名称”", state.device_help)
        self.assertIn("固定为中文识别", state.language_help)
        self.assertIn("Caps Lock", state.hotkey_help)
        self.assertIn("单键按住说话", state.hotkey_mode_summary)
        self.assertIn("自动粘贴", state.submit_help)
        self.assertIn("1 个去重后的输入设备", state.device_help)
        self.assertEqual(state.autostart_summary, "未启用")
        self.assertIn("开机自启", state.autostart_help)

    def test_build_gui_state_formats_selected_input_device_with_name(self):
        app = FakeGuiApp()
        app.config = apply_gui_settings(
            app.config,
            language="zh",
            input_device_text="3: USB Mic",
            hold_to_talk=app.config.hotkey.hold_to_talk,
            submit_strategy=app.config.hotkey.submit_strategy,
        )
        devices = (
            AudioInputDevice(index=3, name="USB Mic", max_input_channels=1, default_sample_rate=16000),
        )

        state = build_gui_state(
            app,
            devices=devices,
            diagnostics=(DiagnosticCheck(name="audio:input_devices", ok=True, message="ok"),),
        )

        self.assertIn("输入设备：3: USB Mic", state.settings_summary)
        self.assertIn("当前保存的是：3: USB Mic", state.device_help)

    def test_build_gui_state_warns_when_selected_input_device_is_missing(self):
        app = FakeGuiApp()
        app.config = apply_gui_settings(
            app.config,
            language="zh",
            input_device_text="99",
            hold_to_talk=app.config.hotkey.hold_to_talk,
            submit_strategy=app.config.hotkey.submit_strategy,
        )
        devices = (
            AudioInputDevice(index=3, name="USB Mic", max_input_channels=1, default_sample_rate=16000),
        )

        state = build_gui_state(
            app,
            devices=devices,
            diagnostics=(DiagnosticCheck(name="audio:input_devices", ok=True, message="ok"),),
        )

        self.assertIn("输入设备：99", state.settings_summary)
        self.assertIn("提醒：保存设备不在列表里", state.settings_summary)
        self.assertIn("可选项：1 个", state.settings_summary)
        self.assertIn("操作：下拉切换", state.settings_summary)
        self.assertIn("不在列表里\n可选项：1 个\n操作：下拉切换", state.settings_summary)
        self.assertIn("已保存：99", state.device_help)
        self.assertIn("直接选“编号: 名称”。留空继续用自动/系统默认设备。\n\n已保存：99。", state.device_help)
        self.assertIn("已保存：99。\n\n提醒：", state.device_help)
        self.assertIn("提醒：不在最新列表里，可能已断开、改名或暂不可用。\n\n可选项：1 个\n操作：下拉切换", state.device_help)
        self.assertIn("不在最新列表里", state.device_help)
        self.assertIn("可选项：1 个", state.device_help)
        self.assertIn("操作：下拉切换", state.device_help)

    def test_build_gui_state_explains_when_no_input_devices_are_found(self):
        app = FakeGuiApp()

        state = build_gui_state(
            app,
            devices=(),
            diagnostics=(DiagnosticCheck(name="audio:input_devices", ok=True, message="0 input device(s) found"),),
        )

        self.assertIn("提醒：当前没有识别到任何输入设备", state.settings_summary)
        self.assertIn("当前没有识别到任何输入设备", state.device_help)
        self.assertIn("重新检查状态", state.device_help)
        self.assertEqual(_current_device_text(None, state.devices), "未识别到输入设备")

    def test_build_gui_state_shows_lightweight_api_context_status(self):
        app = FakeGuiApp()
        app.config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
            api_context=ApiContextConfig(mode="lightweight", recent_turns=2, max_context_chars=1200),
            hotwords=HotwordConfig(words=("Qwen3-ASR", "K7"), enabled=True),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            captures_dir = Path(temp_dir) / "captures"
            captures_dir.mkdir()
            (captures_dir / "transcriptions.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"text": "上一条提到 Qwen"}, ensure_ascii=False),
                        json.dumps({"text": "刚才讲 K7 麦克风"}, ensure_ascii=False),
                    ]
                ),
                encoding="utf-8",
            )
            state = build_gui_state(
                app,
                captures_dir=captures_dir,
                devices=(AudioInputDevice(index=1, name="Mic", max_input_channels=1, default_sample_rate=16000),),
                diagnostics=(DiagnosticCheck(name="audio:input_devices", ok=True, message="ok"),),
            )

        self.assertIn("增强上下文：轻量", state.api_context_summary)
        self.assertIn("最近 2/2 条", state.api_context_summary)
        self.assertIn("术语表 2 条", state.api_context_summary)
        self.assertIn("不会发送音频或音频路径", state.api_context_help)

    def test_build_gui_state_shows_quick_note_rules_and_inbox(self):
        app = FakeGuiApp()
        app.config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
            quick_capture=QuickCaptureConfig(
                root_dir="notes",
                inbox_dir="inbox",
                match_window_chars=12,
                rules=(
                    QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),
                    QuickCaptureRule(name="todo", keywords=("待办",), target_dir="todo"),
                ),
            ),
        )

        state = build_gui_state(
            app,
            devices=(AudioInputDevice(index=1, name="Mic", max_input_channels=1, default_sample_rate=16000),),
            diagnostics=(DiagnosticCheck(name="audio:input_devices", ok=True, message="ok"),),
        )

        self.assertIn("规则 2 条", state.quick_note_summary)
        self.assertIn("notes\\inbox", state.quick_note_summary)
        self.assertIn("ideas, todo", state.quick_note_summary)
        self.assertIn("默认匹配窗口 12 个字符", state.quick_note_help)

    def test_apply_gui_settings_updates_selected_fields(self):
        config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
        )

        updated = apply_gui_settings(
            config,
            language="en",
            input_device_text="3: USB Mic",
            hold_to_talk="f8",
            submit_strategy="只复制到剪贴板",
            api_process_enabled=True,
            api_preset="正式改写 formal",
            api_fallback_raw=True,
            quick_note_enabled=True,
        )

        self.assertEqual(updated.selection.language, "en")
        self.assertEqual(updated.audio.input_device, 3)
        self.assertEqual(updated.hotkey.hold_to_talk, "f8")
        self.assertEqual(updated.hotkey.submit_strategy, "clipboard_only")
        self.assertTrue(updated.api_processing.enabled)
        self.assertEqual(updated.api_processing.preset, "formal")
        self.assertTrue(updated.api_processing.fallback_raw)
        self.assertTrue(updated.quick_capture.enabled)

    def test_apply_gui_settings_ignores_no_device_placeholder(self):
        config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
        )

        updated = apply_gui_settings(
            config,
            language="zh",
            input_device_text="未识别到输入设备",
            hold_to_talk="caps_lock",
            submit_strategy="自动粘贴到当前光标",
        )

        self.assertIsNone(updated.audio.input_device)

    def test_add_quick_note_rule_from_gui_trims_single_keyword_and_keep_setting(self):
        config = AppConfig(quick_capture=QuickCaptureConfig(enabled=True))

        updated = add_quick_note_rule_from_gui(
            config,
            name=" ideas ",
            keyword=" 灵感 ",
            target_dir=" ideas ",
            keep_keyword=True,
        )

        self.assertTrue(updated.quick_capture.enabled)
        self.assertEqual(len(updated.quick_capture.rules), 1)
        rule = updated.quick_capture.rules[0]
        self.assertEqual(rule.name, "ideas")
        self.assertEqual(rule.keywords, ("灵感",))
        self.assertEqual(rule.target_dir, "ideas")
        self.assertFalse(rule.remove_keyword)

    def test_add_quick_note_rule_from_gui_rejects_duplicate_rule_name(self):
        config = AppConfig(
            quick_capture=QuickCaptureConfig(
                rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
            )
        )

        with self.assertRaisesRegex(ValueError, "已存在"):
            add_quick_note_rule_from_gui(
                config,
                name=" Ideas ",
                keyword="想法",
                target_dir="ideas",
                keep_keyword=False,
            )

    def test_add_quick_note_rule_from_gui_rejects_blank_fields(self):
        config = AppConfig()

        with self.assertRaisesRegex(ValueError, "规则名称"):
            add_quick_note_rule_from_gui(config, name=" ", keyword="灵感", target_dir="ideas", keep_keyword=False)
        with self.assertRaisesRegex(ValueError, "关键词"):
            add_quick_note_rule_from_gui(config, name="ideas", keyword=" ", target_dir="ideas", keep_keyword=False)
        with self.assertRaisesRegex(ValueError, "目标目录"):
            add_quick_note_rule_from_gui(config, name="ideas", keyword="灵感", target_dir=" ", keep_keyword=False)

    def test_quick_note_rule_labels_show_keywords_target_and_keyword_policy(self):
        config = AppConfig(
            quick_capture=QuickCaptureConfig(
                remove_keyword=True,
                rules=(
                    QuickCaptureRule(name="ideas", keywords=("灵感", "想法"), target_dir="ideas"),
                    QuickCaptureRule(name="todo", keywords=("待办",), target_dir="todo", remove_keyword=False),
                ),
            )
        )

        labels = quick_note_rule_labels(config)

        self.assertEqual(len(labels), 2)
        self.assertIn("1. ideas", labels[0])
        self.assertIn("关键词：灵感、想法", labels[0])
        self.assertIn("目录：ideas", labels[0])
        self.assertIn("跟随全局：移除关键词", labels[0])
        self.assertIn("2. todo", labels[1])
        self.assertIn("保留关键词", labels[1])

    def test_remove_quick_note_rule_by_index_from_gui_removes_only_selected_rule(self):
        config = AppConfig(
            quick_capture=QuickCaptureConfig(
                rules=(
                    QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),
                    QuickCaptureRule(name="todo", keywords=("待办",), target_dir="todo"),
                    QuickCaptureRule(name="quotes", keywords=("摘录",), target_dir="quotes"),
                ),
            )
        )

        updated = remove_quick_note_rule_by_index_from_gui(config, 1)

        self.assertEqual([rule.name for rule in updated.quick_capture.rules], ["ideas", "quotes"])

    def test_remove_quick_note_rule_by_index_from_gui_rejects_invalid_index(self):
        config = AppConfig(
            quick_capture=QuickCaptureConfig(
                rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
            )
        )

        with self.assertRaisesRegex(ValueError, "请选择"):
            remove_quick_note_rule_by_index_from_gui(config, -1)
        with self.assertRaisesRegex(ValueError, "请选择"):
            remove_quick_note_rule_by_index_from_gui(config, 1)

    def test_apply_gui_settings_parses_missing_device_label_back_to_index(self):
        config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
        )

        updated = apply_gui_settings(
            config,
            language="zh",
            input_device_text="99: 已保存设备；当前未识别到输入设备",
            hold_to_talk="caps_lock",
            submit_strategy="自动粘贴到当前光标",
        )

        self.assertEqual(updated.audio.input_device, 99)

    def test_apply_gui_settings_parses_missing_saved_device_label_back_to_index(self):
        config = AppConfig(
            selection=SelectionRequest(language="zh"),
            hotkey=HotkeyConfig(hold_to_talk="caps_lock", submit_strategy="clipboard_paste"),
        )

        updated = apply_gui_settings(
            config,
            language="zh",
            input_device_text="99: 已保存设备；不在最新列表里",
            hold_to_talk="caps_lock",
            submit_strategy="自动粘贴到当前光标",
        )

        self.assertEqual(updated.audio.input_device, 99)

    def test_build_gui_state_dedupes_duplicate_devices(self):
        app = FakeGuiApp()
        devices = (
            AudioInputDevice(index=10, name="Mic", max_input_channels=2, default_sample_rate=44100),
            AudioInputDevice(index=1, name="Mic", max_input_channels=2, default_sample_rate=44100),
            AudioInputDevice(index=2, name="Other", max_input_channels=1, default_sample_rate=16000),
        )

        state = build_gui_state(
            app,
            devices=devices,
            diagnostics=(DiagnosticCheck(name="audio:input_devices", ok=True, message="ok"),),
        )

        self.assertEqual([device["index"] for device in state.devices], [1, 2])

    def test_dedupe_devices_keeps_lowest_index_for_same_name_and_rate(self):
        devices = (
            AudioInputDevice(index=8, name="Mic", max_input_channels=2, default_sample_rate=44100),
            AudioInputDevice(index=3, name="Mic", max_input_channels=2, default_sample_rate=44100),
        )

        deduped = _dedupe_devices(devices)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].index, 3)

    def test_status_helpers_provide_clear_feedback(self):
        self.assertEqual(_status_ready(), "状态：准备就绪。")
        self.assertEqual(
            _status_after_check(True, "已通过基础体检"),
            "状态：已完成检查。已通过基础体检。",
        )
        self.assertEqual(
            _status_action_success("已保存当前设置", "C:\\config.json"),
            "状态：已保存当前设置。C:\\config.json。",
        )
        self.assertIn("状态：重新检查状态失败。", _status_action_error("重新检查状态", RuntimeError("boom")))
        self.assertIn("boom", _status_action_error("重新检查状态", RuntimeError("boom")))

    def test_submit_strategy_helpers_show_human_labels(self):
        self.assertEqual(_display_submit_strategy("clipboard_paste"), "自动粘贴到当前光标")
        self.assertEqual(_parse_submit_strategy_text("只复制到剪贴板"), "clipboard_only")
        self.assertEqual(_parse_submit_strategy_text("type_text"), "type_text")
        self.assertIn("直接发 Ctrl+V", _submit_strategy_help("clipboard_paste"))
        self.assertIn("不会自动粘贴", _submit_strategy_help("只复制到剪贴板"))

    def test_api_processing_helpers_show_gui_summary(self):
        self.assertIn("口语整理 clean", _api_preset_choices())
        self.assertEqual(_parse_api_preset_text("正式改写 formal"), "formal")
        self.assertEqual(_parse_api_preset_text("todo"), "todo")
        self.assertEqual(_api_processing_summary(False, "clean", False), "未启用")
        self.assertIn("提取待办 todo", _api_processing_summary(True, "todo", True))
        self.assertIn("失败退回原文", _api_processing_summary(True, "todo", True))
        self.assertIn("原始文字", _api_processing_help(False, "clean", False))
        self.assertIn("调用 API", _api_processing_help(True, "clean", False))

    def test_api_provider_status_never_shows_secret_value(self):
        config = ApiProviderConfig(
            provider="siliconflow",
            base_url="https://api.siliconflow.cn/v1",
            api_key_env="SILICONFLOW_API_KEY",
            model="Qwen/Qwen3-8B",
        )

        status = _api_provider_status(config, environ={"SILICONFLOW_API_KEY": "secret-value"})

        self.assertIn("API 接口：已就绪", status)
        self.assertIn("provider=siliconflow", status)
        self.assertIn("model=Qwen/Qwen3-8B", status)
        self.assertIn("SILICONFLOW_API_KEY 已设置", status)
        self.assertNotIn("secret-value", status)

    def test_api_provider_status_lists_missing_fields(self):
        status = _api_provider_status(ApiProviderConfig(), environ={})

        self.assertIn("API 接口：未就绪", status)
        self.assertIn("接口地址", status)
        self.assertIn("模型", status)
        self.assertIn("密钥环境变量", status)

    def test_api_context_helpers_explain_modes(self):
        from local_voice_input.api_context import ApiContextPackage

        off_config = AppConfig(hotwords=HotwordConfig(words=("术语",), enabled=True))
        off_package = ApiContextPackage(enabled=False, mode="off")
        self.assertIn("未启用", _api_context_summary(off_config, off_package))
        self.assertIn("术语表可用 1 条", _api_context_summary(off_config, off_package))
        self.assertIn("当前这一次", _api_context_help(off_config, off_package))

        light_config = AppConfig(
            api_context=ApiContextConfig(mode="lightweight", recent_turns=3, max_context_chars=1200),
            hotwords=HotwordConfig(words=("Qwen3-ASR",), enabled=True),
        )
        light_package = ApiContextPackage(
            enabled=True,
            mode="lightweight",
            recent_texts=("上一句",),
            glossary_terms=("Qwen3-ASR",),
            max_context_chars=1200,
            used_chars=10,
        )
        self.assertIn("最近 1/3 条", _api_context_summary(light_config, light_package))
        self.assertIn("术语表 1 条", _api_context_summary(light_config, light_package))
        self.assertIn("只把文字上下文发给 API", _api_context_help(light_config, light_package))

    def test_quick_note_helpers_explain_rules_and_fallback(self):
        empty = AppConfig()
        self.assertIn("未启用", _quick_note_summary(empty))
        self.assertIn("规则 0 条", _quick_note_summary(empty))
        self.assertIn("quick-rule add", _quick_note_help(empty))

        configured = AppConfig(
            quick_capture=QuickCaptureConfig(
                enabled=True,
                root_dir="notes",
                inbox_dir="inbox",
                match_window_chars=16,
                rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
            )
        )
        self.assertIn("已启用", _quick_note_summary(configured))
        self.assertIn("规则 1 条", _quick_note_summary(configured))
        self.assertIn("ideas", _quick_note_summary(configured))
        self.assertIn("开头附近", _quick_note_help(configured))

    def test_language_help_explains_common_values(self):
        self.assertIn("auto 表示让程序自动判断", _language_help("auto"))
        self.assertIn("固定为中文识别", _language_help("zh"))
        self.assertIn("固定为英文识别", _language_help("en"))

    def test_model_help_explains_recommendation(self):
        self.assertIn(
            "当前按听写优先",
            _model_help(
                "sensevoice-small-onnx-int8",
                "sherpa-onnx",
                "Selected sensevoice-small-onnx-int8 for dictation (auto priority) on CPU/local; resource checks passed.",
            ),
        )

    def test_doctor_help_explains_check_scope(self):
        self.assertIn(
            "还没做转录冒烟测试",
            _doctor_help((DiagnosticCheck(name="audio:input_devices", ok=True, message="ok"),)),
        )
        self.assertIn(
            "转录冒烟测试都已经跑通",
            _doctor_help((DiagnosticCheck(name="smoke:transcribe", ok=True, message="ok"),)),
        )

    def test_hotkey_help_explains_common_key_choices(self):
        self.assertIn("Caps Lock", _hotkey_help("caps_lock"))
        self.assertIn("功能键通常比较稳", _hotkey_help("f8"))
        self.assertIn("右 Ctrl", _hotkey_help("right ctrl"))

    def test_hotkey_mode_summary_makes_single_key_limit_explicit(self):
        self.assertIn("单键按住说话", _hotkey_mode_summary("f8"))
        self.assertIn("组合键暂不支持", _hotkey_mode_summary("ctrl+space"))

    def test_recommended_hotkey_prefers_low_conflict_function_key(self):
        self.assertEqual(_recommended_hotkey(), "f8")
        self.assertIn("更少影响日常输入", _recommended_hotkey_reason("f8"))

    def test_display_hotkey_humanizes_common_values(self):
        self.assertEqual(_display_hotkey("caps_lock"), "Caps Lock")
        self.assertEqual(_display_hotkey("f8"), "F8")
        self.assertEqual(_display_hotkey("right ctrl"), "右 Ctrl")

    def test_display_input_device_prefers_index_plus_name(self):
        devices = ({"index": 3, "name": "USB Mic"},)

        self.assertEqual(_display_input_device(3, devices), "3: USB Mic")
        self.assertEqual(_display_input_device("3", devices), "3: USB Mic")
        self.assertEqual(_display_input_device(None, devices), "自动/系统默认")

    def test_is_known_input_device_checks_latest_device_list(self):
        devices = ({"index": 3, "name": "USB Mic"},)

        self.assertTrue(_is_known_input_device(3, devices))
        self.assertTrue(_is_known_input_device("3", devices))
        self.assertFalse(_is_known_input_device(99, devices))
        self.assertFalse(_is_known_input_device("usb mic", devices))

    def test_device_choice_text_truncates_long_names(self):
        device = {
            "index": 31,
            "name": "Headset Device Path Noise Marker (WH-1000XM5) Extra Tail",
        }

        text = _device_choice_text(device)

        self.assertTrue(text.startswith("31: "))
        self.assertIn("...", text)
        self.assertIn("Extra Tail", text)

    def test_current_device_text_uses_same_short_label_as_dropdown(self):
        devices = (
            {
                "index": 31,
                "name": "Headset Device Path Noise Marker (WH-1000XM5) Extra Tail",
            },
        )

        self.assertEqual(_current_device_text(31, devices), _device_choice_text(devices[0]))

    def test_current_device_text_explains_missing_saved_device_when_no_devices_exist(self):
        self.assertEqual(
            _current_device_text(99, ()),
            "99: 已保存设备；当前未识别到输入设备",
        )

    def test_current_device_text_explains_missing_saved_device_when_other_devices_exist(self):
        devices = ({"index": 3, "name": "USB Mic"},)

        self.assertEqual(
            _current_device_text(99, devices),
            "99: 已保存设备；不在最新列表里",
        )

    def test_device_choice_values_match_dropdown_labels(self):
        devices = (
            {"index": 3, "name": "USB Mic"},
            {"index": 31, "name": "Headset Device Path Noise Marker (WH-1000XM5) Extra Tail"},
        )

        values = _device_choice_values(devices)

        self.assertEqual(values[0], "3: USB Mic")
        self.assertIn("...", values[1])

    def test_device_choice_values_use_placeholder_when_empty(self):
        self.assertEqual(_device_choice_values(()), ("未识别到输入设备",))

    def test_device_choice_values_keep_missing_saved_device_hint_when_empty(self):
        self.assertEqual(
            _device_choice_values((), 99),
            ("99: 已保存设备；当前未识别到输入设备",),
        )

    def test_device_choice_values_keep_missing_saved_device_hint_when_other_devices_exist(self):
        devices = ({"index": 3, "name": "USB Mic"},)

        self.assertEqual(
            _device_choice_values(devices, 99),
            ("99: 已保存设备；不在最新列表里", "3: USB Mic"),
        )

    def test_sync_device_widgets_refreshes_values_and_current_selection(self):
        devices = (
            {"index": 31, "name": "Headset Device Path Noise Marker (WH-1000XM5) Extra Tail"},
        )
        device_var = FakeStringVar()
        device_widget = {}

        _sync_device_widgets(device_var, device_widget, 31, devices)

        self.assertEqual(device_widget["values"], _device_choice_values(devices))
        self.assertEqual(device_var.value, _device_choice_text(devices[0]))

    def test_sync_device_widgets_uses_placeholder_when_no_devices_exist(self):
        device_var = FakeStringVar()
        device_widget = {}

        _sync_device_widgets(device_var, device_widget, None, ())

        self.assertEqual(device_widget["values"], ("未识别到输入设备",))
        self.assertEqual(device_var.value, "未识别到输入设备")

    def test_sync_device_widgets_keeps_missing_saved_device_hint_when_no_devices_exist(self):
        device_var = FakeStringVar()
        device_widget = {}

        _sync_device_widgets(device_var, device_widget, 99, ())

        self.assertEqual(device_widget["values"], ("99: 已保存设备；当前未识别到输入设备",))
        self.assertEqual(device_var.value, "99: 已保存设备；当前未识别到输入设备")

    def test_sync_device_widgets_keeps_missing_saved_device_hint_when_other_devices_exist(self):
        device_var = FakeStringVar()
        device_widget = {}
        devices = ({"index": 3, "name": "USB Mic"},)

        _sync_device_widgets(device_var, device_widget, 99, devices)

        self.assertEqual(device_widget["values"], ("99: 已保存设备；不在最新列表里", "3: USB Mic"))
        self.assertEqual(device_var.value, "99: 已保存设备；不在最新列表里")

    def test_console_python_executable_prefers_python_over_pythonw(self):
        with mock.patch("local_voice_input.gui.sys.executable", "C:\\Python312\\pythonw.exe"):
            with mock.patch("pathlib.Path.exists", autospec=True) as exists_mock:
                exists_mock.side_effect = lambda path: path.name.lower() == "python.exe"
                self.assertEqual(_console_python_executable(), "C:\\Python312\\python.exe")

    def test_console_python_executable_prefers_py_over_pyw(self):
        with mock.patch("local_voice_input.gui.sys.executable", "C:\\Windows\\pyw.exe"):
            with mock.patch("pathlib.Path.exists", autospec=True) as exists_mock:
                exists_mock.side_effect = lambda path: path.name.lower() == "py.exe"
                self.assertEqual(_console_python_executable(), "C:\\Windows\\py.exe")

    def test_hold_to_talk_command_uses_console_python_and_config_path(self):
        with mock.patch("local_voice_input.gui._console_python_executable", return_value="C:\\Python312\\python.exe"):
            command = _hold_to_talk_command(Path("config.json"))

        self.assertEqual(
            command,
            [
                "C:\\Python312\\python.exe",
                "-m",
                "local_voice_input",
                "--config",
                "config.json",
                "hold-to-talk",
            ],
        )

    def test_hold_to_talk_command_includes_api_processing_flags_from_gui_config(self):
        config = apply_gui_settings(
            AppConfig(),
            language="zh",
            input_device_text="",
            hold_to_talk="caps_lock",
            submit_strategy="自动粘贴到当前光标",
            api_process_enabled=True,
            api_preset="提取待办 todo",
            api_fallback_raw=True,
        )

        with mock.patch("local_voice_input.gui._console_python_executable", return_value="C:\\Python312\\python.exe"):
            command = _hold_to_talk_command(Path("config.json"), config)

        self.assertEqual(
            command[-5:],
            ["hold-to-talk", "--api-process", "--api-preset", "todo", "--api-fallback-raw"],
        )

    def test_hold_to_talk_command_includes_quick_note_when_enabled_in_gui_config(self):
        config = apply_gui_settings(
            AppConfig(),
            language="zh",
            input_device_text="",
            hold_to_talk="caps_lock",
            submit_strategy="自动粘贴到当前光标",
            quick_note_enabled=True,
        )

        with mock.patch("local_voice_input.gui._console_python_executable", return_value="C:\\Python312\\python.exe"):
            command = _hold_to_talk_command(Path("config.json"), config)

        self.assertIn("--quick-note", command)
        self.assertEqual(command[-1], "--quick-note")

    def test_hold_to_talk_log_path_uses_captures_directory(self):
        self.assertEqual(_hold_to_talk_log_path(Path("captures")), Path("captures") / "hold-to-talk.log")

    def test_windows_hidden_creationflags_returns_int(self):
        creationflags = _windows_hidden_creationflags()

        self.assertIsInstance(creationflags, int)
        self.assertGreaterEqual(creationflags, 0)

    def test_autostart_helpers_explain_current_state(self):
        path = Path("Startup") / "OpenVoiceInput GUI.vbs"

        self.assertEqual(_autostart_summary(True), "已启用")
        self.assertEqual(_autostart_summary(False), "未启用")
        self.assertIn(str(path), _autostart_help(True, path))
        self.assertIn("当前还没有开机自启", _autostart_help(False, path))

    def test_minimize_window_calls_iconify(self):
        window = FakeWindow()

        _minimize_window(window)

        self.assertTrue(window.iconified)

    @unittest.skipUnless(os.name == "nt", "Windows-only lock behavior")
    def test_gui_single_instance_lock_rejects_second_holder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "gui.lock"
            first = _try_acquire_gui_single_instance_lock(lock_path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(_try_acquire_gui_single_instance_lock(lock_path))
            finally:
                _release_gui_single_instance_lock(first)

            second = _try_acquire_gui_single_instance_lock(lock_path)
            try:
                self.assertIsNotNone(second)
            finally:
                _release_gui_single_instance_lock(second)

    def test_check_hotkey_registration_registers_and_unhooks_key(self):
        keyboard = FakeKeyboard()

        result = _check_hotkey_registration("f8", keyboard)

        self.assertTrue(result.ok)
        self.assertEqual(keyboard.registered_key, "f8")
        self.assertEqual(keyboard.unhooked, "handler")
        self.assertIn("可以注册", result.message)

    def test_check_hotkey_registration_warns_for_likely_conflicts(self):
        result = _check_hotkey_registration("caps_lock", FakeKeyboard())

        self.assertTrue(result.ok)
        self.assertIn("可能会切换大小写", result.message)

    def test_check_hotkey_registration_rejects_combo_for_now(self):
        result = _check_hotkey_registration("ctrl+space", FakeKeyboard())

        self.assertFalse(result.ok)
        self.assertIn("只支持单键热键", result.message)

    def test_check_hotkey_registration_reports_registration_failure(self):
        result = _check_hotkey_registration("f8", FakeKeyboard(fail=True))

        self.assertFalse(result.ok)
        self.assertIn("无法注册", result.message)

    def test_process_helpers_report_running_and_terminate(self):
        process = FakeProcess(running=True)

        self.assertTrue(_process_is_running(process))
        _terminate_process(process)

        self.assertTrue(process.terminated)
        self.assertFalse(_process_is_running(process))

    def test_read_text_tail_and_start_failure_detail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "hold-to-talk.log"
            path.write_text("first\nsecond\nthird", encoding="utf-8")

            self.assertEqual(_read_text_tail(path, max_chars=12), "second\nthird")
            detail = _hold_to_talk_start_failure_detail(2, path)

        self.assertIn("退出码 2", detail)
        self.assertIn("third", detail)


if __name__ == "__main__":
    unittest.main()
