import contextlib
from io import StringIO
import json
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

import test_bootstrap  # noqa: F401

from local_voice_input.asr import TranscriptionResult
from local_voice_input.api_context import ApiContextPackage
from local_voice_input.api_provider import ApiTextResult
from local_voice_input.cli import (
    _dictation_stem,
    _maybe_process_text_with_api,
    _print_hold_to_talk_api_summary,
    _print_hold_to_talk_device_and_model_summary,
    _print_hold_to_talk_quick_note_summary,
    _print_hold_to_talk_startup_summary,
    _print_quick_note_status,
    _run_hold_to_talk,
    _maybe_write_srt,
    _result_for_output_text,
    _sidecar_output_path,
    _voice_output_mode,
    main,
)
from local_voice_input.config import ApiProviderConfig, AppConfig, QuickCaptureConfig, QuickCaptureRule, save_config
from local_voice_input.model_selector import ModelProfile, SelectionRequest, SelectionResult
from local_voice_input.quick_note import QuickNoteResult
from local_voice_input.text_output import TextOutputResult


class CliTests(unittest.TestCase):
    def test_config_set_and_show_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            with contextlib.redirect_stdout(StringIO()):
                set_code = main(
                    [
                        "--config",
                        str(path),
                        "config",
                        "set",
                        "--language",
                        "zh",
                        "--input-device",
                        "1",
                        "--sample-rate",
                        "48000",
                    ]
                )

            output = StringIO()
            with contextlib.redirect_stdout(output):
                show_code = main(["--config", str(path), "config", "show"])

        self.assertEqual(set_code, 0)
        self.assertEqual(show_code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["selection"]["language"], "zh")
        self.assertEqual(data["audio"]["input_device"], 1)
        self.assertEqual(data["audio"]["sample_rate_hz"], 48000)

    def test_config_path_uses_override(self):
        output = StringIO()
        with contextlib.redirect_stdout(output):
            code = main(["--config", "custom.json", "config", "path"])

        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue().strip(), "custom.json")

    def test_dictation_stem_includes_turn_number(self):
        stem = _dictation_stem(7)

        self.assertTrue(stem.startswith("dictation-"))
        self.assertTrue(stem.endswith("-007"))

    def test_voice_output_mode_defaults_to_paste_for_clipboard_paste_strategy(self):
        class Args:
            copy = True
            clipboard_only = False
            no_paste = False

        self.assertEqual(_voice_output_mode(Args(), "clipboard_paste"), (False, True))

    def test_voice_output_mode_can_force_clipboard_only(self):
        class Args:
            copy = False
            clipboard_only = True
            no_paste = False

        self.assertEqual(_voice_output_mode(Args(), "clipboard_paste"), (True, False))

    def test_run_hold_to_talk_prints_status_progression(self):
        class FakeSession:
            def __init__(self, audio_path):
                self.audio_path = audio_path

            def start(self):
                return None

            def stop(self):
                return self.audio_path

        class FakeApp:
            def __init__(self):
                self.config = AppConfig()

            def create_recording_session(self, audio_path, device=None):
                self.device = device
                return FakeSession(audio_path)

            def recommend_model(self, request=None):
                return SelectionResult(
                    profile=ModelProfile(
                        model_id="sensevoice-small-onnx-int8",
                        display_name="SenseVoice Small ONNX INT8",
                        backend="sherpa-onnx",
                        min_ram_gb=3,
                        recommended_ram_gb=4,
                    ),
                    reason="test",
                )

            def transcribe_file(self, path, request=None):
                return TranscriptionResult(
                    text="hello from asr",
                    model_id="fake-model",
                    language=request.language,
                    metadata={"source_path": str(path)},
                )

        class FakeRunner:
            def __init__(self, on_press, on_release, names):
                self.on_press = on_press
                self.on_release = on_release
                self.names = names

            def run_until_quit(self):
                self.on_press()
                self.on_release()

        args = SimpleNamespace(
            hold_key=None,
            quit_key=None,
            output_dir="captures",
            text_out_dir=None,
            srt_out_dir=None,
            device=None,
            quick_note=False,
            no_log=True,
            copy=False,
            clipboard_only=False,
            no_paste=True,
        )
        output = StringIO()

        with patch("local_voice_input.cli.PushToTalkHotkeyRunner", FakeRunner):
            with contextlib.redirect_stdout(output):
                code = _run_hold_to_talk(FakeApp(), SelectionRequest(language="zh"), args)

        rendered = output.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("startup: submit_strategy=terminal_only (只在终端显示/调试)", rendered)
        self.assertIn("startup: api_processing=disabled (未启用，直接输出原始识别文本)", rendered)
        self.assertIn("startup: quick_note=disabled", rendered)
        self.assertIn("规则 0 条", rendered)
        self.assertIn("notes\\inbox", rendered)
        self.assertIn("startup: language=zh (固定中文识别)", rendered)
        self.assertIn("startup: input_device_source=system_default (系统默认设备)", rendered)
        self.assertIn("startup: input_device=auto (自动/系统默认设备)", rendered)
        self.assertIn("startup: recommended_model=sensevoice-small-onnx-int8 (sherpa-onnx)", rendered)
        self.assertIn("status: recording_started", rendered)
        self.assertIn("recording:", rendered)
        self.assertIn("status: recording_stopped", rendered)
        self.assertIn("status: transcribing", rendered)
        self.assertIn("hello from asr", rendered)
        self.assertIn("status: completed", rendered)
        self.assertLess(rendered.index("status: recording_started"), rendered.index("status: recording_stopped"))
        self.assertLess(rendered.index("status: recording_stopped"), rendered.index("status: transcribing"))
        self.assertLess(rendered.index("status: transcribing"), rendered.index("status: completed"))

    def test_run_hold_to_talk_prints_failed_status_on_transcription_error(self):
        class FakeSession:
            def __init__(self, audio_path):
                self.audio_path = audio_path

            def start(self):
                return None

            def stop(self):
                return self.audio_path

        class FakeApp:
            def __init__(self):
                self.config = AppConfig()

            def create_recording_session(self, audio_path, device=None):
                self.device = device
                return FakeSession(audio_path)

            def recommend_model(self, request=None):
                return SelectionResult(
                    profile=ModelProfile(
                        model_id="sensevoice-small-onnx-int8",
                        display_name="SenseVoice Small ONNX INT8",
                        backend="sherpa-onnx",
                        min_ram_gb=3,
                        recommended_ram_gb=4,
                    ),
                    reason="test",
                )

            def transcribe_file(self, path, request=None):
                raise ValueError("boom")

        class FakeRunner:
            def __init__(self, on_press, on_release, names):
                self.on_press = on_press
                self.on_release = on_release
                self.names = names

            def run_until_quit(self):
                self.on_press()
                self.on_release()

        args = SimpleNamespace(
            hold_key=None,
            quit_key=None,
            output_dir="captures",
            text_out_dir=None,
            srt_out_dir=None,
            device=None,
            quick_note=False,
            no_log=True,
            copy=False,
            clipboard_only=False,
            no_paste=True,
        )
        stdout = StringIO()
        stderr = StringIO()

        with patch("local_voice_input.cli.PushToTalkHotkeyRunner", FakeRunner):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = _run_hold_to_talk(FakeApp(), SelectionRequest(language="zh"), args)

        self.assertEqual(code, 0)
        self.assertIn("status: failed", stdout.getvalue())
        self.assertIn("error: boom", stderr.getvalue())

    def test_hold_to_talk_startup_summary_reports_effective_clipboard_paste_mode(self):
        args = SimpleNamespace(no_paste=False, clipboard_only=False, copy=False)
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_startup_summary(args, "clipboard_paste")

        self.assertIn("startup: submit_strategy=clipboard_paste", output.getvalue())
        self.assertIn("自动粘贴到当前光标", output.getvalue())

    def test_hold_to_talk_startup_summary_reports_effective_clipboard_only_override(self):
        args = SimpleNamespace(no_paste=False, clipboard_only=True, copy=False)
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_startup_summary(args, "clipboard_paste")

        self.assertIn("startup: submit_strategy=clipboard_only", output.getvalue())
        self.assertIn("只复制到剪贴板", output.getvalue())

    def test_hold_to_talk_api_summary_reports_disabled_by_default(self):
        args = SimpleNamespace(api_process=False)
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_api_summary(args)

        self.assertIn("startup: api_processing=disabled", output.getvalue())
        self.assertIn("原始识别文本", output.getvalue())

    def test_hold_to_talk_api_summary_reports_preset_source(self):
        args = SimpleNamespace(
            api_process=True,
            api_preset="clean",
            api_system_prompt=None,
            api_fallback_raw=False,
        )
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_api_summary(args)

        rendered = output.getvalue()
        self.assertIn("startup: api_processing=enabled", rendered)
        self.assertIn("prompt_source=preset:clean", rendered)
        self.assertIn("fallback_raw=false", rendered)

    def test_hold_to_talk_api_summary_reports_custom_prompt_source(self):
        args = SimpleNamespace(
            api_process=True,
            api_preset="clean",
            api_system_prompt="整理成正式中文",
            api_fallback_raw=True,
        )
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_api_summary(args)

        rendered = output.getvalue()
        self.assertIn("prompt_source=custom:--api-system-prompt", rendered)
        self.assertIn("fallback_raw=true", rendered)

    def test_hold_to_talk_quick_note_summary_reports_disabled_state(self):
        args = SimpleNamespace(quick_note=False)
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_quick_note_summary(args, AppConfig())

        rendered = output.getvalue()
        self.assertIn("startup: quick_note=disabled", rendered)
        self.assertIn("未启用 --quick-note", rendered)
        self.assertIn("规则 0 条", rendered)
        self.assertIn("未命中目录=notes\\inbox", rendered)

    def test_hold_to_talk_quick_note_summary_reports_enabled_rules_and_inbox(self):
        args = SimpleNamespace(quick_note=True)
        config = AppConfig(
            quick_capture=QuickCaptureConfig(
                root_dir="my_notes",
                inbox_dir="fallback",
                rules=(
                    QuickCaptureRule(
                        name="ideas",
                        keywords=("灵感",),
                        target_dir="ideas",
                    ),
                    QuickCaptureRule(
                        name="todo",
                        keywords=("待办",),
                        target_dir="todo",
                    ),
                ),
            )
        )
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_quick_note_summary(args, config)

        rendered = output.getvalue()
        self.assertIn("startup: quick_note=enabled", rendered)
        self.assertIn("已启用 --quick-note", rendered)
        self.assertIn("规则 2 条", rendered)
        self.assertIn("未命中目录=my_notes\\fallback", rendered)

    def test_hold_to_talk_device_and_model_summary_reports_auto_language_device_and_model(self):
        class FakeApp:
            def __init__(self):
                self.config = AppConfig()

            def recommend_model(self, request=None):
                return SelectionResult(
                    profile=ModelProfile(
                        model_id="sensevoice-small-onnx-int8",
                        display_name="SenseVoice Small ONNX INT8",
                        backend="sherpa-onnx",
                        min_ram_gb=3,
                        recommended_ram_gb=4,
                    ),
                    reason="test",
                )

        args = SimpleNamespace(device=None)
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_device_and_model_summary(FakeApp(), SelectionRequest(language=None), args)

        rendered = output.getvalue()
        self.assertIn("startup: language=auto (自动判断语言)", rendered)
        self.assertIn("startup: input_device_source=system_default (系统默认设备)", rendered)
        self.assertIn("startup: input_device=auto (自动/系统默认设备)", rendered)
        self.assertIn("startup: recommended_model=sensevoice-small-onnx-int8 (sherpa-onnx)", rendered)

    def test_hold_to_talk_device_and_model_summary_reports_fixed_device_override(self):
        class FakeApp:
            def __init__(self):
                self.config = AppConfig()

            def recommend_model(self, request=None):
                return SelectionResult(
                    profile=ModelProfile(
                        model_id="sensevoice-small-onnx-int8",
                        display_name="SenseVoice Small ONNX INT8",
                        backend="sherpa-onnx",
                        min_ram_gb=3,
                        recommended_ram_gb=4,
                    ),
                    reason="test",
                )

        args = SimpleNamespace(device="4")
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_device_and_model_summary(FakeApp(), SelectionRequest(language="zh"), args)

        rendered = output.getvalue()
        self.assertIn("startup: language=zh (固定中文识别)", rendered)
        self.assertIn("startup: input_device_source=cli_override (命令行临时指定)", rendered)
        self.assertIn("startup: input_device=4 (固定设备)", rendered)

    def test_hold_to_talk_device_and_model_summary_reports_config_fixed_device_source(self):
        class FakeApp:
            def __init__(self):
                self.config = SimpleNamespace(audio=SimpleNamespace(input_device=7))

            def recommend_model(self, request=None):
                return SelectionResult(
                    profile=ModelProfile(
                        model_id="sensevoice-small-onnx-int8",
                        display_name="SenseVoice Small ONNX INT8",
                        backend="sherpa-onnx",
                        min_ram_gb=3,
                        recommended_ram_gb=4,
                    ),
                    reason="test",
                )

        args = SimpleNamespace(device=None)
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_hold_to_talk_device_and_model_summary(FakeApp(), SelectionRequest(language="en"), args)

        rendered = output.getvalue()
        self.assertIn("startup: language=en (固定英文识别)", rendered)
        self.assertIn("startup: input_device_source=config_fixed (配置里的固定设备)", rendered)
        self.assertIn("startup: input_device=7 (固定设备)", rendered)

    def test_maybe_write_srt_adds_path_to_text_output_result(self):
        result = TranscriptionResult(text="hello", model_id="model", metadata={"duration_s": "2.0"})
        output = TextOutputResult(text="hello")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "out.srt"

            updated = _maybe_write_srt(result, output, path)

            self.assertEqual(updated.srt_path, path)
            self.assertIn("00:00:02,000", path.read_text(encoding="utf-8"))

    def test_sidecar_output_path_uses_source_stem(self):
        self.assertEqual(
            _sidecar_output_path(Path("audio") / "meeting.wav", "out", ".txt"),
            Path("out") / "meeting.txt",
        )

    def test_transcribe_multiple_files_requires_output_directory_options(self):
        stderr = StringIO()

        with contextlib.redirect_stderr(stderr):
            code = main(["transcribe", "a.wav", "b.wav", "--text-out", "one.txt"])

        self.assertEqual(code, 2)
        self.assertIn("--text-out-dir", stderr.getvalue())

    def test_benchmark_command_prints_json_summary(self):
        class FakeApp:
            def transcribe_file(self, path, request=None):
                return TranscriptionResult(
                    text="ok",
                    model_id="fake-model",
                    language=request.language,
                    metadata={"duration_s": "4.0"},
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.wav"
            path.write_bytes(b"fake")
            output = StringIO()

            with patch("local_voice_input.cli.VoiceInputApp", return_value=FakeApp()):
                with contextlib.redirect_stdout(output):
                    code = main(["benchmark", str(path), "--language", "zh", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["summary"]["count"], 1)
        self.assertEqual(data["all_summary"]["count"], 1)
        self.assertIsNone(data["warm_summary"])
        self.assertIn("后台文件转写", data["advice"])
        self.assertEqual(data["results"][0]["model_id"], "fake-model")

    def test_benchmark_command_can_discard_first_run_from_summary(self):
        class FakeApp:
            def transcribe_file(self, path, request=None):
                return TranscriptionResult(
                    text="ok",
                    model_id="fake-model",
                    language=request.language,
                    metadata={"duration_s": "4.0"},
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.wav"
            path.write_bytes(b"fake")
            output = StringIO()

            with patch("local_voice_input.cli.VoiceInputApp", return_value=FakeApp()):
                with contextlib.redirect_stdout(output):
                    code = main(
                        [
                            "benchmark",
                            str(path),
                            "--repeat",
                            "3",
                            "--discard-first",
                            "--json",
                        ]
                    )

        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["summary"]["count"], 2)
        self.assertEqual(data["summary"]["discarded_first_count"], 1)
        self.assertEqual(data["all_summary"]["count"], 3)
        self.assertEqual(data["warm_summary"]["count"], 2)
        self.assertIn("后台文件转写", data["advice"])

    def test_api_processing_helper_replaces_output_text(self):
        class Args:
            api_process = True
            api_system_prompt = "整理"
            api_preset = None
            api_temperature = 0
            api_max_tokens = 20
            api_fallback_raw = False

        def fake_call(config, text, **_kwargs):
            self.assertEqual(text, "原始语音")
            return ApiTextResult(
                text="整理后的语音。",
                provider=config.provider,
                model=config.model,
                endpoint=config.base_url,
            )

        config = AppConfig(
            api_provider=ApiProviderConfig(
                provider="test",
                base_url="https://example.com/v1/chat/completions",
                api_key_env="TEST_KEY",
                model="model",
            )
        )
        result = TranscriptionResult(text="原始语音", model_id="asr")

        with patch("local_voice_input.cli.call_chat_completion", fake_call):
            summary = _maybe_process_text_with_api("原始语音", config, Args())

        updated = _result_for_output_text(result, summary)

        self.assertTrue(summary.processed)
        self.assertEqual(updated.text, "整理后的语音。")
        self.assertEqual(updated.metadata["api_process_processed"], "true")

    def test_api_processing_helper_can_fallback_to_raw_text(self):
        class Args:
            api_process = True
            api_system_prompt = "整理"
            api_preset = None
            api_temperature = 0
            api_max_tokens = 20
            api_fallback_raw = True

        def fake_call(_config, _text, **_kwargs):
            from local_voice_input.api_provider import ApiProviderError

            raise ApiProviderError("bad key")

        with patch("local_voice_input.cli.call_chat_completion", fake_call):
            summary = _maybe_process_text_with_api("原始语音", AppConfig(), Args())

        self.assertFalse(summary.processed)
        self.assertEqual(summary.text, "原始语音")
        self.assertIn("bad key", summary.error)

    def test_api_processing_helper_uses_named_preset(self):
        class Args:
            api_process = True
            api_system_prompt = None
            api_preset = "todo"
            api_temperature = 0
            api_max_tokens = 20
            api_fallback_raw = False

        seen = {}

        def fake_call(_config, _text, **kwargs):
            seen["system_prompt"] = kwargs["system_prompt"]
            return ApiTextResult(text="- 买牛奶", provider="test", model="model", endpoint="endpoint")

        with patch("local_voice_input.cli.call_chat_completion", fake_call):
            summary = _maybe_process_text_with_api("记得买牛奶", AppConfig(), Args())

        self.assertEqual(summary.text, "- 买牛奶")
        self.assertIn("待办", seen["system_prompt"])

    def test_api_processing_helper_wraps_text_with_lightweight_context(self):
        class Args:
            api_process = True
            api_system_prompt = "整理"
            api_preset = None
            api_temperature = 0
            api_max_tokens = 20
            api_fallback_raw = False

        seen = {}

        def fake_call(_config, text, **_kwargs):
            seen["text"] = text
            return ApiTextResult(text="整理后", provider="test", model="model", endpoint="endpoint")

        package = ApiContextPackage(
            enabled=True,
            mode="lightweight",
            recent_texts=("上一句讲 Qwen",),
            glossary_terms=("Qwen3-ASR",),
            max_context_chars=1200,
            used_chars=16,
        )

        with patch("local_voice_input.cli.build_api_context_package", return_value=package):
            with patch("local_voice_input.cli.call_chat_completion", fake_call):
                summary = _maybe_process_text_with_api("当前语音", AppConfig(), Args())

        self.assertIn("术语表", seen["text"])
        self.assertIn("Qwen3-ASR", seen["text"])
        self.assertIn("上一句讲 Qwen", seen["text"])
        self.assertIn("当前语音", seen["text"])
        self.assertEqual(summary.context_mode, "lightweight")
        self.assertEqual(summary.context_recent_count, 1)
        self.assertEqual(summary.context_glossary_count, 1)

    def test_quick_rule_add_lists_rule(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            with contextlib.redirect_stdout(StringIO()):
                add_code = main(
                    [
                        "--config",
                        str(path),
                        "quick-rule",
                        "add",
                        "--name",
                        "ideas",
                        "--keyword",
                        "灵感",
                        "--target-dir",
                        "ideas",
                    ]
                )

            output = StringIO()
            with contextlib.redirect_stdout(output):
                list_code = main(["--config", str(path), "quick-rule", "list"])

        self.assertEqual(add_code, 0)
        self.assertEqual(list_code, 0)
        rules = json.loads(output.getvalue())
        self.assertEqual(rules[0]["name"], "ideas")
        self.assertEqual(rules[0]["keywords"], ["灵感"])

    def test_quick_note_command_saves_routed_note(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            save_config(
                AppConfig(
                    quick_capture=QuickCaptureConfig(
                        root_dir=str(Path(temp_dir) / "notes"),
                        rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
                    )
                ),
                config_path,
            )

            output = StringIO()
            with contextlib.redirect_stdout(output):
                code = main(["--config", str(config_path), "quick-note", "灵感", "新的点子", "--json"])

            self.assertEqual(code, 0)
            data = json.loads(output.getvalue())
            self.assertEqual(data["matched_keyword"], "灵感")
            self.assertEqual(data["saved_text"], "新的点子")
            self.assertTrue(Path(data["path"]).exists())

    def test_print_quick_note_status_distinguishes_matched_rule(self):
        result = QuickNoteResult(
            original_text="灵感 新想法",
            saved_text="新想法",
            path=Path("notes") / "ideas" / "note.txt",
            matched_rule="ideas",
            matched_keyword="灵感",
            removed_keyword=True,
        )
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_quick_note_status(result)

        rendered = output.getvalue()
        self.assertIn("quick_note_status: matched_rule", rendered)
        self.assertIn("命中规则", rendered)
        self.assertIn("saved_quick_note: notes\\ideas\\note.txt", rendered)
        self.assertIn("matched_rule: ideas", rendered)
        self.assertIn("matched_keyword: 灵感", rendered)
        self.assertIn("removed_keyword: true", rendered)

    def test_print_quick_note_status_distinguishes_inbox_fallback(self):
        result = QuickNoteResult(
            original_text="普通记录",
            saved_text="普通记录",
            path=Path("notes") / "inbox" / "note.txt",
        )
        output = StringIO()

        with contextlib.redirect_stdout(output):
            _print_quick_note_status(result)

        rendered = output.getvalue()
        self.assertIn("quick_note_status: inbox", rendered)
        self.assertIn("未命中关键词", rendered)
        self.assertIn("saved_quick_note: notes\\inbox\\note.txt", rendered)
        self.assertNotIn("matched_rule:", rendered)
        self.assertNotIn("matched_keyword:", rendered)

    def test_model_commands_set_and_clear_manual_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            with contextlib.redirect_stdout(StringIO()):
                set_code = main(["--config", str(path), "model", "set", "sensevoice-small-onnx-int8"])

            output = StringIO()
            with contextlib.redirect_stdout(output):
                show_code = main(["--config", str(path), "model", "show"])

            with contextlib.redirect_stdout(StringIO()):
                auto_code = main(["--config", str(path), "model", "auto"])

            cleared = StringIO()
            with contextlib.redirect_stdout(cleared):
                clear_show_code = main(["--config", str(path), "model", "show"])

        self.assertEqual(set_code, 0)
        self.assertEqual(show_code, 0)
        self.assertEqual(auto_code, 0)
        self.assertEqual(clear_show_code, 0)
        self.assertEqual(json.loads(output.getvalue())["manual_model_id"], "sensevoice-small-onnx-int8")
        self.assertIsNone(json.loads(cleared.getvalue())["manual_model_id"])

    def test_model_set_rejects_unknown_model(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            stderr = StringIO()

            with contextlib.redirect_stderr(stderr):
                code = main(["--config", str(path), "model", "set", "missing-model"])

        self.assertEqual(code, 2)
        self.assertIn("unknown model", stderr.getvalue())

    def test_hotword_commands_update_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            with contextlib.redirect_stdout(StringIO()):
                add_code = main(["--config", str(path), "hotword", "add", "Codex", "语音输入"])
                disable_code = main(["--config", str(path), "hotword", "disable"])

            output = StringIO()
            with contextlib.redirect_stdout(output):
                list_code = main(["--config", str(path), "hotword", "list"])

        self.assertEqual(add_code, 0)
        self.assertEqual(disable_code, 0)
        self.assertEqual(list_code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["words"], ["Codex", "语音输入"])
        self.assertFalse(data["enabled"])

    def test_route_command_updates_task_route(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            with contextlib.redirect_stdout(StringIO()):
                set_code = main(
                    [
                        "--config",
                        str(path),
                        "route",
                        "set",
                        "file_transcription",
                        "--priority",
                        "accuracy",
                        "--background",
                        "true",
                        "--manual-model-id",
                        "vibevoice-asr-hf-8b",
                    ]
                )

            output = StringIO()
            with contextlib.redirect_stdout(output):
                show_code = main(["--config", str(path), "route", "show"])

        self.assertEqual(set_code, 0)
        self.assertEqual(show_code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["file_transcription"]["priority"], "accuracy")
        self.assertTrue(data["file_transcription"]["background"])
        self.assertEqual(data["file_transcription"]["manual_model_id"], "vibevoice-asr-hf-8b")

    def test_api_provider_command_updates_config_without_secret_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            with contextlib.redirect_stdout(StringIO()):
                set_code = main(
                    [
                        "--config",
                        str(path),
                        "api-provider",
                        "set",
                        "--provider",
                        "siliconflow",
                        "--base-url",
                        "https://api.siliconflow.cn/v1",
                        "--api-key-env",
                        "SILICONFLOW_API_KEY",
                        "--model",
                        "deepseek-ai/DeepSeek-V3",
                    ]
                )

            output = StringIO()
            with contextlib.redirect_stdout(output):
                show_code = main(["--config", str(path), "api-provider", "show"])

        self.assertEqual(set_code, 0)
        self.assertEqual(show_code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["provider"], "siliconflow")
        self.assertEqual(data["api_key_env"], "SILICONFLOW_API_KEY")
        self.assertNotIn("api_key", data)

    def test_api_provider_test_reports_missing_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            save_config(
                AppConfig(
                    api_provider=ApiProviderConfig(
                        provider="siliconflow",
                        base_url="https://api.siliconflow.cn/v1",
                        api_key_env="MISSING_API_KEY",
                        model="Qwen/Qwen3-8B",
                    )
                ),
                path,
            )
            stderr = StringIO()

            with contextlib.redirect_stderr(stderr):
                code = main(["--config", str(path), "api-provider", "test", "--text", "hello"])

        self.assertEqual(code, 2)
        self.assertIn("MISSING_API_KEY", stderr.getvalue())

    def test_sendto_install_writes_drag_and_drop_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = StringIO()
            script_path = Path(temp_dir) / "Voice.cmd"

            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "sendto",
                        "install",
                        "--output",
                        str(script_path),
                        "--cwd",
                        str(Path(temp_dir) / "project"),
                        "--language",
                        "zh",
                        "--text-out-dir",
                        "transcripts",
                        "--srt-out-dir",
                        "subtitles",
                        "--no-pause",
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(Path(output.getvalue().strip()), script_path)
            content = script_path.read_text(encoding="utf-8")
            self.assertIn("py -m local_voice_input transcribe %*", content)
            self.assertIn('--language "zh"', content)
            self.assertIn('--text-out-dir "transcripts"', content)
            self.assertIn('--srt-out-dir "subtitles"', content)

    def test_gui_command_can_print_json_state(self):
        class FakeState:
            def to_dict(self):
                return {"language": "zh", "recommended_model_id": "sensevoice-small-onnx-int8"}

        output = StringIO()
        with patch("local_voice_input.cli.build_gui_state", return_value=FakeState()):
            with contextlib.redirect_stdout(output):
                code = main(["gui", "--json"])

        self.assertEqual(code, 0)
        data = json.loads(output.getvalue())
        self.assertEqual(data["language"], "zh")
        self.assertEqual(data["recommended_model_id"], "sensevoice-small-onnx-int8")
