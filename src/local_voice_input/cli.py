"""Command line entry points for early framework validation."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from time import perf_counter
import sys
from dataclasses import asdict, dataclass, replace
from typing import Sequence

from .asr import BackendUnavailableError, TranscriptionError
from .api_provider import (
    DEFAULT_SYSTEM_PROMPT,
    DICTATION_POSTPROCESS_PROMPT,
    POSTPROCESS_PRESETS,
    ApiProviderError,
    call_chat_completion,
    get_postprocess_prompt,
)
from .api_context import build_api_context_package, format_api_context_user_text
from .app import VoiceInputApp
from .audio_capture import AudioCaptureError, list_input_devices, record_wav
from .benchmark import (
    BenchmarkCase,
    default_benchmark_cases,
    result_to_dict as benchmark_result_to_dict,
    run_transcription_benchmark,
    summarize_benchmark_results,
    usage_advice as benchmark_usage_advice,
)
from .config import (
    add_quick_capture_rule,
    add_hotwords,
    clear_quick_capture_rules,
    clear_hotwords,
    default_config_path,
    load_config,
    save_config,
    selection_for_task,
    set_hotwords_enabled,
    update_api_provider,
    update_config,
    update_task_route,
)
from .diagnostics import format_diagnostics, has_failures, run_diagnostics
from .gui import build_gui_state, launch_gui
from .hotkey import HotkeyError, HotkeyNames, PushToTalkHotkeyRunner, normalize_hotkey_name
from .model_selector import SelectionRequest, detect_hardware, get_model_profiles
from .quick_note import QuickNoteResult, save_quick_note
from .text_output import TextOutputError, apply_text_outputs
from .usage_log import append_transcription_log, entry_from_result
from .subtitles import write_srt_file
from .windows_entry import (
    DEFAULT_SENDTO_SCRIPT_NAME,
    TranscribeLauncherOptions,
    resolve_sendto_script_path,
    write_transcribe_launcher,
)


@dataclass(frozen=True)
class ApiProcessingSummary:
    enabled: bool
    processed: bool
    raw_text: str
    text: str
    provider: str | None = None
    model: str | None = None
    endpoint: str | None = None
    error: str | None = None
    context_mode: str = "off"
    context_recent_count: int = 0
    context_glossary_count: int = 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="open-voice-input")
    parser.add_argument("--config", help="Path to a JSON config file.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("detect", help="Print detected hardware.")
    subparsers.add_parser("models", help="List built-in model profiles.")
    subparsers.add_parser("devices", help="List available microphone input devices.")
    doctor_parser = subparsers.add_parser("doctor", help="Check dependencies, model files, and audio devices.")
    doctor_parser.add_argument("--run-transcribe-smoke", action="store_true")
    doctor_parser.add_argument("--json", action="store_true")
    gui_parser = subparsers.add_parser("gui", help="Open the minimal Tkinter launcher and settings panel.")
    gui_parser.add_argument("--json", action="store_true", help="Print the GUI state instead of opening a window.")

    benchmark_parser = subparsers.add_parser("benchmark", help="Run a small file transcription benchmark.")
    benchmark_parser.add_argument("paths", nargs="*", metavar="path")
    benchmark_parser.add_argument("--language", default=None)
    benchmark_parser.add_argument("--task", choices=["dictation", "file_transcription", "long_form"], default="file_transcription")
    benchmark_parser.add_argument("--repeat", type=int, default=1)
    benchmark_parser.add_argument("--manual-model-id", default=None)
    benchmark_parser.add_argument("--discard-first", action="store_true", help="Use only repeat runs after the first run in the main summary.")
    benchmark_parser.add_argument("--json", action="store_true")
    benchmark_parser.add_argument("--include-text", action="store_true")

    config_parser = subparsers.add_parser("config", help="Show or update the app config.")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("path", help="Print the config file path.")
    config_subparsers.add_parser("show", help="Print the current config.")
    config_subparsers.add_parser("init", help="Create a config file with default values.")
    config_set_parser = config_subparsers.add_parser("set", help="Update selected config values.")
    config_set_parser.add_argument("--language")
    config_set_parser.add_argument("--priority", choices=["auto", "speed", "balanced", "accuracy"])
    config_set_parser.add_argument("--device-policy", choices=["auto", "cpu", "nvidia"])
    config_set_parser.add_argument("--manual-model-id", default=None)
    config_set_parser.add_argument("--allow-experimental", choices=["true", "false"])
    config_set_parser.add_argument("--input-device", default=None)
    config_set_parser.add_argument("--sample-rate", type=int, default=None)
    config_set_parser.add_argument("--channels", type=int, default=None)
    config_set_parser.add_argument("--hold-to-talk")
    config_set_parser.add_argument("--submit-strategy", choices=["clipboard_paste", "clipboard_only", "type_text"])

    model_parser = subparsers.add_parser("model", help="Show or update the global manual model setting.")
    model_subparsers = model_parser.add_subparsers(dest="model_command", required=True)
    model_subparsers.add_parser("show", help="Print the global model setting and current recommendation.")
    model_set_parser = model_subparsers.add_parser("set", help="Force one model globally.")
    model_set_parser.add_argument("model_id")
    model_subparsers.add_parser("auto", help="Clear the global manual model and return to automatic selection.")

    quick_rule_parser = subparsers.add_parser("quick-rule", help="Manage quick note keyword routing rules.")
    quick_rule_subparsers = quick_rule_parser.add_subparsers(dest="quick_rule_command", required=True)
    quick_rule_subparsers.add_parser("list", help="Print quick note routing rules.")
    quick_rule_subparsers.add_parser("clear", help="Remove all quick note routing rules.")
    quick_rule_add_parser = quick_rule_subparsers.add_parser("add", help="Add a quick note routing rule.")
    quick_rule_add_parser.add_argument("--name", required=True)
    quick_rule_add_parser.add_argument("--keyword", action="append", required=True)
    quick_rule_add_parser.add_argument("--target-dir", required=True)
    quick_rule_add_parser.add_argument("--match-window", type=int, default=None)
    quick_rule_add_parser.add_argument("--keep-keyword", action="store_true")

    quick_note_parser = subparsers.add_parser("quick-note", help="Save text using quick note keyword routing.")
    quick_note_parser.add_argument("text", nargs="+")
    quick_note_parser.add_argument("--json", action="store_true")

    hotword_parser = subparsers.add_parser("hotword", help="Manage hotwords for supported ASR backends.")
    hotword_subparsers = hotword_parser.add_subparsers(dest="hotword_command", required=True)
    hotword_subparsers.add_parser("list", help="Print configured hotwords.")
    hotword_add_parser = hotword_subparsers.add_parser("add", help="Add one or more hotwords.")
    hotword_add_parser.add_argument("words", nargs="+")
    hotword_subparsers.add_parser("clear", help="Remove all hotwords.")
    hotword_subparsers.add_parser("enable", help="Enable hotword usage.")
    hotword_subparsers.add_parser("disable", help="Disable hotword usage.")

    route_parser = subparsers.add_parser("route", help="Manage task-specific model routing.")
    route_subparsers = route_parser.add_subparsers(dest="route_command", required=True)
    route_subparsers.add_parser("show", help="Print task routing config.")
    route_set_parser = route_subparsers.add_parser("set", help="Update a task route.")
    route_set_parser.add_argument("task", choices=["dictation", "file_transcription", "long_form"])
    route_set_parser.add_argument("--priority", choices=["auto", "speed", "balanced", "accuracy"])
    route_set_parser.add_argument("--background", choices=["true", "false"])
    route_set_parser.add_argument("--manual-model-id")
    route_set_parser.add_argument("--auto-model", action="store_true", help="Clear the task-specific manual model.")

    api_parser = subparsers.add_parser("api-provider", help="Manage optional API/custom provider config.")
    api_subparsers = api_parser.add_subparsers(dest="api_command", required=True)
    api_subparsers.add_parser("show", help="Print API provider config.")
    api_set_parser = api_subparsers.add_parser("set", help="Update API provider config.")
    api_set_parser.add_argument("--provider")
    api_set_parser.add_argument("--base-url")
    api_set_parser.add_argument("--api-key-env")
    api_set_parser.add_argument("--model")
    api_set_parser.add_argument("--timeout", type=float)
    api_test_parser = api_subparsers.add_parser("test", help="Send a text request to the configured API provider.")
    api_test_parser.add_argument("--text", nargs="+", required=True)
    api_test_parser.add_argument("--system-prompt", default=None)
    api_test_parser.add_argument("--preset", choices=sorted(POSTPROCESS_PRESETS), default=None)
    api_test_parser.add_argument("--temperature", type=float, default=0.2)
    api_test_parser.add_argument("--max-tokens", type=int, default=512)
    api_test_parser.add_argument("--json", action="store_true")

    sendto_parser = subparsers.add_parser("sendto", help="Create Windows Send To / drag-and-drop launchers.")
    sendto_subparsers = sendto_parser.add_subparsers(dest="sendto_command", required=True)
    sendto_subparsers.add_parser("path", help="Print the default Windows SendTo folder.")
    sendto_install_parser = sendto_subparsers.add_parser("install", help="Write a transcribe launcher .cmd file.")
    sendto_install_parser.add_argument("--output", help="Script path or directory. Defaults to the Windows SendTo folder.")
    sendto_install_parser.add_argument("--name", default=DEFAULT_SENDTO_SCRIPT_NAME)
    sendto_install_parser.add_argument("--cwd", default=str(Path.cwd()), help="Working directory used by the launcher.")
    sendto_install_parser.add_argument("--python", dest="python_command", default="py")
    sendto_install_parser.add_argument("--language", default=None)
    sendto_install_parser.add_argument("--text-out-dir", default="transcripts")
    sendto_install_parser.add_argument("--srt-out-dir", default=None)
    sendto_install_parser.add_argument("--quick-note", action="store_true")
    sendto_install_parser.add_argument("--api-process", action="store_true")
    sendto_install_parser.add_argument("--api-preset", choices=sorted(POSTPROCESS_PRESETS), default="clean")
    sendto_install_parser.add_argument("--api-fallback-raw", action="store_true")
    sendto_install_parser.add_argument("--no-log", action="store_true")
    sendto_install_parser.add_argument("--no-pause", action="store_true")
    sendto_install_parser.add_argument("--overwrite", action="store_true")

    recommend_parser = subparsers.add_parser("recommend", help="Recommend a model for this machine.")
    recommend_parser.add_argument("--task", choices=["dictation", "file_transcription", "long_form"], default=None)
    recommend_parser.add_argument("--priority", choices=["auto", "speed", "balanced", "accuracy"], default=None)
    recommend_parser.add_argument("--language", default=None)
    recommend_parser.add_argument("--device", choices=["auto", "cpu", "nvidia"], default=None)
    recommend_parser.add_argument("--manual-model-id", default=None)
    recommend_parser.add_argument("--stable-only", action="store_true")
    recommend_parser.add_argument("--json", action="store_true")

    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe one or more audio files.")
    transcribe_parser.add_argument("paths", nargs="+", metavar="path")
    transcribe_parser.add_argument("--language", default=None)
    transcribe_parser.add_argument("--json", action="store_true")
    transcribe_parser.add_argument("--copy", action="store_true", help="Copy recognized text to the clipboard.")
    transcribe_parser.add_argument("--paste", action="store_true", help="Paste recognized text into the active window and restore the previous clipboard text.")
    transcribe_parser.add_argument("--text-out", help="Write recognized text to a UTF-8 text file.")
    transcribe_parser.add_argument("--text-out-dir", help="Write each recognized text to this directory using the source file stem.")
    transcribe_parser.add_argument("--srt-out", help="Write a basic UTF-8 SRT subtitle file.")
    transcribe_parser.add_argument("--srt-out-dir", help="Write each basic SRT file to this directory using the source file stem.")
    transcribe_parser.add_argument("--quick-note", action="store_true", help="Save recognized text using keyword routing.")
    _add_api_processing_arguments(transcribe_parser)
    transcribe_parser.add_argument("--no-log", action="store_true", help="Do not append to the JSONL transcription log.")

    record_parser = subparsers.add_parser("record", help="Record microphone audio to a wav file.")
    record_parser.add_argument("output")
    record_parser.add_argument("--seconds", type=float, default=5.0)
    record_parser.add_argument("--sample-rate", type=int, default=None)
    record_parser.add_argument("--channels", type=int, default=None)
    record_parser.add_argument("--device", default=None, help="Input device index or name.")

    listen_parser = subparsers.add_parser("listen-once", help="Record once and transcribe the result.")
    listen_parser.add_argument("--seconds", type=float, default=5.0)
    listen_parser.add_argument("--output", default=str(Path("captures") / "listen-once.wav"))
    listen_parser.add_argument("--language", default=None)
    listen_parser.add_argument("--device", default=None, help="Input device index or name.")
    listen_parser.add_argument("--json", action="store_true")
    listen_parser.add_argument("--copy", action="store_true", help="Copy recognized text to the clipboard.")
    listen_parser.add_argument("--paste", action="store_true", help="Paste recognized text into the active window and restore the previous clipboard text.")
    listen_parser.add_argument("--text-out", help="Write recognized text to a UTF-8 text file.")
    listen_parser.add_argument("--srt-out", help="Write a basic UTF-8 SRT subtitle file.")
    listen_parser.add_argument("--quick-note", action="store_true", help="Save recognized text using keyword routing.")
    _add_api_processing_arguments(listen_parser)
    listen_parser.add_argument("--no-log", action="store_true", help="Do not append to the JSONL transcription log.")

    loop_parser = subparsers.add_parser("dictate-loop", help="Interactive repeated record-and-transcribe loop.")
    loop_parser.add_argument("--seconds", type=float, default=5.0)
    loop_parser.add_argument("--output-dir", default="captures")
    loop_parser.add_argument("--text-out-dir")
    loop_parser.add_argument("--srt-out-dir")
    loop_parser.add_argument("--language", default=None)
    loop_parser.add_argument("--device", default=None, help="Input device index or name.")
    loop_parser.add_argument("--copy", action="store_true", help="Deprecated; use --clipboard-only for copy-only mode.")
    loop_parser.add_argument("--clipboard-only", action="store_true", help="Copy text without auto-pasting.")
    loop_parser.add_argument("--no-paste", action="store_true", help="Print/save only; do not paste.")
    loop_parser.add_argument("--quick-note", action="store_true", help="Save each recognized text using keyword routing.")
    _add_api_processing_arguments(loop_parser)
    loop_parser.add_argument("--no-log", action="store_true", help="Do not append to the JSONL transcription log.")
    loop_parser.add_argument("--max-turns", type=int, default=None, help=argparse.SUPPRESS)

    hold_parser = subparsers.add_parser("hold-to-talk", help="Hold a global hotkey to record, release to transcribe.")
    hold_parser.add_argument("--hold-key", default=None)
    hold_parser.add_argument("--quit-key", default=None)
    hold_parser.add_argument("--output-dir", default="captures")
    hold_parser.add_argument("--text-out-dir")
    hold_parser.add_argument("--srt-out-dir")
    hold_parser.add_argument("--language", default=None)
    hold_parser.add_argument("--device", default=None, help="Input device index or name.")
    hold_parser.add_argument("--copy", action="store_true", help="Deprecated; use --clipboard-only for copy-only mode.")
    hold_parser.add_argument("--clipboard-only", action="store_true", help="Copy text without auto-pasting.")
    hold_parser.add_argument("--no-paste", action="store_true", help="Print/save only; do not paste.")
    hold_parser.add_argument("--quick-note", action="store_true", help="Save each recognized text using keyword routing.")
    _add_api_processing_arguments(hold_parser)
    hold_parser.add_argument("--no-log", action="store_true", help="Do not append to the JSONL transcription log.")

    args = parser.parse_args(argv)

    if args.command == "detect":
        print(json.dumps(_hardware_to_dict(detect_hardware()), ensure_ascii=False, indent=2))
        return 0

    if args.command == "models":
        for profile in get_model_profiles():
            marker = " experimental" if profile.experimental else ""
            print(
                f"{profile.model_id}\t{profile.backend}\t{','.join(profile.task_fit)}"
                f"\tRAM {profile.min_ram_gb:g}GB+{marker}"
            )
        return 0

    if args.command == "doctor":
        checks = run_diagnostics(run_transcribe_smoke=args.run_transcribe_smoke)
        if args.json:
            print(
                json.dumps(
                    [{"name": check.name, "ok": check.ok, "message": check.message} for check in checks],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(format_diagnostics(checks))
        return 1 if has_failures(checks) else 0

    config = load_config(args.config)
    app = VoiceInputApp(config=config)

    if args.command == "benchmark":
        return _run_benchmark_command(app, config, args)

    if args.command == "gui":
        config_path = Path(args.config) if args.config else default_config_path()
        if args.json:
            print(json.dumps(build_gui_state(app, config_path=config_path).to_dict(), ensure_ascii=False, indent=2))
            return 0
        try:
            launch_gui(app, config_path=config_path)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0

    if args.command == "config":
        path = Path(args.config) if args.config else default_config_path()
        if args.config_command == "path":
            print(str(path))
            return 0
        if args.config_command == "show":
            print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.config_command == "init":
            written = save_config(config, path)
            print(str(written))
            return 0
        if args.config_command == "set":
            updated = update_config(
                config,
                language=args.language,
                priority=args.priority,
                device_policy=args.device_policy,
                manual_model_id=args.manual_model_id,
                allow_experimental=_coerce_bool(args.allow_experimental),
                input_device=_coerce_device(args.input_device) if args.input_device is not None else None,
                sample_rate_hz=args.sample_rate,
                channels=args.channels,
                hold_to_talk=args.hold_to_talk,
                submit_strategy=args.submit_strategy,
            )
            written = save_config(updated, path)
            print(str(written))
            return 0

    if args.command == "model":
        path = Path(args.config) if args.config else default_config_path()
        if args.model_command == "show":
            recommendation = app.recommend_model(config.selection)
            print(
                json.dumps(
                    {
                        "manual_model_id": config.selection.manual_model_id,
                        "recommended_model_id": recommendation.profile.model_id,
                        "recommended_backend": recommendation.profile.backend,
                        "reason": recommendation.reason,
                        "warnings": list(recommendation.warnings),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.model_command == "set":
            if not _is_known_model_id(args.model_id):
                print(f"error: unknown model: {args.model_id}", file=sys.stderr)
                return 2
            written = save_config(update_config(config, manual_model_id=args.model_id), path)
            print(str(written))
            return 0
        if args.model_command == "auto":
            written = save_config(update_config(config, manual_model_id=""), path)
            print(str(written))
            return 0

    if args.command == "quick-rule":
        path = Path(args.config) if args.config else default_config_path()
        if args.quick_rule_command == "list":
            print(json.dumps([asdict(rule) for rule in config.quick_capture.rules], ensure_ascii=False, indent=2))
            return 0
        if args.quick_rule_command == "clear":
            written = save_config(clear_quick_capture_rules(config), path)
            print(str(written))
            return 0
        if args.quick_rule_command == "add":
            updated = add_quick_capture_rule(
                config,
                name=args.name,
                keywords=tuple(args.keyword),
                target_dir=args.target_dir,
                match_window_chars=args.match_window,
                remove_keyword=False if args.keep_keyword else None,
            )
            written = save_config(updated, path)
            print(str(written))
            return 0

    if args.command == "quick-note":
        result = save_quick_note(" ".join(args.text), config.quick_capture)
        if args.json:
            print(_quick_note_to_json(result))
        else:
            print(f"saved_quick_note: {result.path}")
            if result.matched_keyword:
                print(f"matched_keyword: {result.matched_keyword}")
        return 0

    if args.command == "hotword":
        path = Path(args.config) if args.config else default_config_path()
        if args.hotword_command == "list":
            print(json.dumps(asdict(config.hotwords), ensure_ascii=False, indent=2))
            return 0
        if args.hotword_command == "add":
            written = save_config(add_hotwords(config, tuple(args.words)), path)
            print(str(written))
            return 0
        if args.hotword_command == "clear":
            written = save_config(clear_hotwords(config), path)
            print(str(written))
            return 0
        if args.hotword_command in {"enable", "disable"}:
            written = save_config(set_hotwords_enabled(config, args.hotword_command == "enable"), path)
            print(str(written))
            return 0

    if args.command == "route":
        path = Path(args.config) if args.config else default_config_path()
        if args.route_command == "show":
            print(json.dumps(asdict(config.task_routes), ensure_ascii=False, indent=2))
            return 0
        if args.route_command == "set":
            if args.manual_model_id and not _is_known_model_id(args.manual_model_id):
                print(f"error: unknown model: {args.manual_model_id}", file=sys.stderr)
                return 2
            updated = update_task_route(
                config,
                args.task,
                priority=args.priority,
                background=_coerce_bool(args.background),
                manual_model_id=args.manual_model_id,
                clear_manual_model=args.auto_model,
            )
            written = save_config(updated, path)
            print(str(written))
            return 0

    if args.command == "api-provider":
        path = Path(args.config) if args.config else default_config_path()
        if args.api_command == "show":
            print(json.dumps(asdict(config.api_provider), ensure_ascii=False, indent=2))
            return 0
        if args.api_command == "set":
            updated = update_api_provider(
                config,
                provider=args.provider,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
                model=args.model,
                timeout_s=args.timeout,
            )
            written = save_config(updated, path)
            print(str(written))
            return 0
        if args.api_command == "test":
            try:
                api_result = call_chat_completion(
                    config.api_provider,
                    " ".join(args.text),
                    system_prompt=_api_system_prompt_from_args(args, provider_test=True),
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                )
            except ApiProviderError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            if args.json:
                print(
                    json.dumps(
                        {
                            "text": api_result.text,
                            "provider": api_result.provider,
                            "model": api_result.model,
                            "endpoint": api_result.endpoint,
                            "usage": api_result.usage,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(api_result.text)
            return 0

    if args.command == "sendto":
        try:
            if args.sendto_command == "path":
                print(str(resolve_sendto_script_path().parent))
                return 0
            if args.sendto_command == "install":
                destination = resolve_sendto_script_path(args.output, name=args.name)
                written = write_transcribe_launcher(
                    destination,
                    TranscribeLauncherOptions(
                        cwd=Path(args.cwd),
                        python_command=args.python_command,
                        language=args.language,
                        text_out_dir=args.text_out_dir,
                        srt_out_dir=args.srt_out_dir,
                        quick_note=args.quick_note,
                        api_process=args.api_process,
                        api_preset=args.api_preset,
                        api_fallback_raw=args.api_fallback_raw,
                        no_log=args.no_log,
                        pause=not args.no_pause,
                    ),
                    overwrite=args.overwrite,
                )
        except (FileExistsError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(str(written))
        return 0

    if args.command == "devices":
        try:
            devices = list_input_devices()
        except AudioCaptureError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        for device in devices:
            print(
                f"{device.index}\t{device.name}\t"
                f"channels={device.max_input_channels}\t"
                f"default_rate={device.default_sample_rate:g}"
            )
        return 0

    if args.command == "record":
        try:
            path = record_wav(
                args.output,
                seconds=args.seconds,
                sample_rate_hz=args.sample_rate or config.audio.sample_rate_hz,
                channels=args.channels or config.audio.channels,
                device=_coerce_device(args.device),
            )
        except (AudioCaptureError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print(str(path))
        return 0

    if args.command == "transcribe":
        return _run_transcribe_command(app, config, args)

    if args.command == "listen-once":
        request = selection_for_task(config, "dictation", language=args.language)
        try:
            started = perf_counter()
            result = app.listen_once(
                args.output,
                seconds=args.seconds,
                request=request,
                device=_coerce_device(args.device),
            )
            api_processing = _maybe_process_text_with_api(result.text, config, args)
            output_result = _result_for_output_text(result, api_processing)
            text_output = apply_text_outputs(
                output_result.text,
                copy=args.copy,
                paste=args.paste,
                text_path=args.text_out,
            )
            text_output = _maybe_write_srt(output_result, text_output, args.srt_out)
            quick_note_result = _maybe_save_quick_note(
                output_result.text,
                config,
                args.quick_note,
                route_text=result.text,
            )
            if not args.no_log:
                append_transcription_log(
                    entry_from_result(
                        command="listen-once",
                        result=output_result,
                        text_output=text_output,
                        elapsed_s=perf_counter() - started,
                    )
                )
        except TextOutputError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except ApiProviderError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except (AudioCaptureError, BackendUnavailableError, TranscriptionError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(_result_to_json(output_result, text_output, quick_note_result, api_processing))
        else:
            print(output_result.text)
            _print_text_output_status(text_output)
            _print_quick_note_status(quick_note_result)
        return 0

    if args.command == "dictate-loop":
        request = selection_for_task(config, "dictation", language=args.language)
        return _run_dictate_loop(app, request, args)

    if args.command == "hold-to-talk":
        request = selection_for_task(config, "dictation", language=args.language)
        return _run_hold_to_talk(app, request, args)

    requested_task = args.task or config.selection.task
    base_request = selection_for_task(config, requested_task)
    request = SelectionRequest(
        task=requested_task,
        priority=args.priority or base_request.priority,
        language=args.language or base_request.language,
        device_policy=args.device or base_request.device_policy,
        manual_model_id=args.manual_model_id or base_request.manual_model_id,
        allow_experimental=base_request.allow_experimental and not args.stable_only,
    )
    result = app.recommend_model(request)

    if args.json:
        print(
            json.dumps(
                {
                    "model_id": result.profile.model_id,
                    "backend": result.profile.backend,
                    "reason": result.reason,
                    "warnings": list(result.warnings),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"model: {result.profile.model_id}")
        print(f"backend: {result.profile.backend}")
        print(f"reason: {result.reason}")
        for warning in result.warnings:
            print(f"warning: {warning}")
    return 0


def _hardware_to_dict(hardware):
    return {
        "os_name": hardware.os_name,
        "cpu_threads": hardware.cpu_threads,
        "ram_gb": hardware.ram_gb,
        "gpus": [
            {"vendor": gpu.vendor, "name": gpu.name, "vram_gb": gpu.vram_gb}
            for gpu in hardware.gpus
        ],
    }


def _coerce_device(raw: str | None) -> int | str | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def _coerce_bool(raw: str | None) -> bool | None:
    if raw is None:
        return None
    return raw.lower() == "true"


def _is_known_model_id(model_id: str) -> bool:
    return model_id in {profile.model_id for profile in get_model_profiles()}


def _result_to_json(
    result,
    text_output,
    quick_note: QuickNoteResult | None = None,
    api_processing: ApiProcessingSummary | None = None,
) -> str:
    return json.dumps(
        _result_to_dict(result, text_output, quick_note, api_processing),
        ensure_ascii=False,
        indent=2,
    )


def _result_to_dict(
    result,
    text_output,
    quick_note: QuickNoteResult | None = None,
    api_processing: ApiProcessingSummary | None = None,
) -> dict:
    return {
        "text": result.text,
        "model_id": result.model_id,
        "language": result.language,
        "metadata": dict(result.metadata),
        "api_processing": _api_processing_to_dict(api_processing),
        "output": {
            "copied_to_clipboard": text_output.copied_to_clipboard,
            "pasted_to_active_window": text_output.pasted_to_active_window,
            "restored_clipboard": text_output.restored_clipboard,
            "clipboard_restore_format_count": text_output.clipboard_restore_format_count,
            "clipboard_restore_skipped_format_count": text_output.clipboard_restore_skipped_format_count,
            "text_path": str(text_output.text_path) if text_output.text_path else None,
            "srt_path": str(text_output.srt_path) if text_output.srt_path else None,
        },
        "quick_note": _quick_note_to_dict(quick_note),
    }


def _api_processing_to_dict(summary: ApiProcessingSummary | None):
    if summary is None:
        return None
    return {
        "enabled": summary.enabled,
        "processed": summary.processed,
        "raw_text": summary.raw_text if summary.processed else None,
        "provider": summary.provider,
        "model": summary.model,
        "endpoint": summary.endpoint,
        "error": summary.error,
        "context_mode": summary.context_mode,
        "context_recent_count": summary.context_recent_count,
        "context_glossary_count": summary.context_glossary_count,
    }


def _quick_note_to_json(result: QuickNoteResult) -> str:
    return json.dumps(_quick_note_to_dict(result), ensure_ascii=False, indent=2)


def _quick_note_to_dict(result: QuickNoteResult | None):
    if result is None:
        return None
    return {
        "path": str(result.path),
        "matched_rule": result.matched_rule,
        "matched_keyword": result.matched_keyword,
        "removed_keyword": result.removed_keyword,
        "saved_text": result.saved_text,
    }


def _print_text_output_status(text_output) -> None:
    if text_output.text_path:
        print(f"saved_text: {text_output.text_path}")
    if text_output.srt_path:
        print(f"saved_srt: {text_output.srt_path}")
    if text_output.copied_to_clipboard:
        print("copied_to_clipboard: true")
    if text_output.pasted_to_active_window:
        print("pasted_to_active_window: true")
    if text_output.restored_clipboard:
        print("restored_clipboard: true")


def _print_hold_to_talk_status(status: str) -> None:
    print(f"status: {status}")


def _print_hold_to_talk_startup_summary(args, submit_strategy: str) -> None:
    strategy_key = _effective_submit_strategy(args, submit_strategy)
    label = _submit_strategy_label(strategy_key)
    print(f"startup: submit_strategy={strategy_key} ({label})")


def _print_hold_to_talk_api_summary(args) -> None:
    if not getattr(args, "api_process", False):
        print("startup: api_processing=disabled (未启用，直接输出原始识别文本)")
        return
    fallback_raw = "true" if getattr(args, "api_fallback_raw", False) else "false"
    print(
        "startup: api_processing=enabled "
        f"({_api_prompt_source_summary(args)}, fallback_raw={fallback_raw})"
    )


def _print_hold_to_talk_quick_note_summary(args, config) -> None:
    enabled = "enabled" if getattr(args, "quick_note", False) else "disabled"
    note = "已启用 --quick-note" if enabled == "enabled" else "未启用 --quick-note"
    quick = config.quick_capture
    inbox = _display_quick_note_dir(quick.root_dir, quick.inbox_dir)
    print(f"startup: quick_note={enabled} ({note}；规则 {len(quick.rules)} 条；未命中目录={inbox})")


def _print_hold_to_talk_device_and_model_summary(
    app: VoiceInputApp,
    request: SelectionRequest,
    args,
) -> None:
    print(f"startup: language={_language_summary(request.language)}")
    effective_device_source = _effective_input_device_source(args, app.config.audio.input_device)
    print(f"startup: input_device_source={_input_device_source_summary(effective_device_source)}")
    effective_device = _effective_input_device(args, app.config.audio.input_device)
    print(f"startup: input_device={_input_device_summary(effective_device)}")
    recommendation = app.recommend_model(request)
    print(f"startup: recommended_model={recommendation.profile.model_id} ({recommendation.profile.backend})")


def _display_quick_note_dir(root_dir: str, configured_dir: str) -> str:
    root = Path(root_dir)
    directory = Path(configured_dir)
    if directory.is_absolute():
        return str(directory)
    if directory.parts and root.name and directory.parts[0].lower() == root.name.lower():
        return str(directory)
    return str(root / directory)


def _maybe_save_quick_note(
    text: str,
    config,
    enabled: bool,
    *,
    route_text: str | None = None,
) -> QuickNoteResult | None:
    if not enabled:
        return None
    return save_quick_note(text, config.quick_capture, route_text=route_text)


def _print_quick_note_status(result: QuickNoteResult | None) -> None:
    if result is None:
        return
    if result.matched_rule:
        print("quick_note_status: matched_rule (命中规则，已保存到规则目录)")
    else:
        print("quick_note_status: inbox (未命中关键词，已保存到 inbox)")
    print(f"saved_quick_note: {result.path}")
    if result.matched_rule:
        print(f"matched_rule: {result.matched_rule}")
    if result.matched_keyword:
        print(f"matched_keyword: {result.matched_keyword}")
        removed = "true" if result.removed_keyword else "false"
        print(f"removed_keyword: {removed}")


def _run_transcribe_command(app: VoiceInputApp, config, args) -> int:
    if len(args.paths) > 1 and (args.text_out or args.srt_out):
        print("error: --text-out and --srt-out can only be used with one input file.", file=sys.stderr)
        print("hint: use --text-out-dir or --srt-out-dir for multiple files.", file=sys.stderr)
        return 2

    request = selection_for_task(config, "file_transcription", language=args.language)
    json_results = []
    for index, source in enumerate(args.paths):
        source_path = Path(source)
        text_path = args.text_out
        if args.text_out_dir:
            text_path = _sidecar_output_path(source_path, args.text_out_dir, ".txt")
        srt_path = args.srt_out
        if args.srt_out_dir:
            srt_path = _sidecar_output_path(source_path, args.srt_out_dir, ".srt")

        try:
            started = perf_counter()
            result = app.transcribe_file(source_path, request=request)
            api_processing = _maybe_process_text_with_api(result.text, config, args)
            output_result = _result_for_output_text(result, api_processing)
            text_output = apply_text_outputs(
                output_result.text,
                copy=args.copy,
                paste=args.paste,
                text_path=text_path,
            )
            text_output = _maybe_write_srt(output_result, text_output, srt_path)
            quick_note_result = _maybe_save_quick_note(
                output_result.text,
                config,
                args.quick_note,
                route_text=result.text,
            )
            if not args.no_log:
                append_transcription_log(
                    entry_from_result(
                        command="transcribe",
                        result=output_result,
                        text_output=text_output,
                        elapsed_s=perf_counter() - started,
                    )
                )
        except TextOutputError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except ApiProviderError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except (BackendUnavailableError, TranscriptionError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if args.json:
            json_results.append(_result_to_dict(output_result, text_output, quick_note_result, api_processing))
        else:
            if len(args.paths) > 1:
                if index:
                    print()
                print(f"==> {source_path}")
            print(output_result.text)
            _print_text_output_status(text_output)
            _print_quick_note_status(quick_note_result)

    if args.json:
        payload = json_results[0] if len(json_results) == 1 else json_results
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _sidecar_output_path(source_path: Path, output_dir: str | Path, suffix: str) -> Path:
    return Path(output_dir) / f"{source_path.stem}{suffix}"


def _run_benchmark_command(app: VoiceInputApp, config, args) -> int:
    cases = tuple(BenchmarkCase(Path(path)) for path in args.paths) if args.paths else default_benchmark_cases()
    base_request = selection_for_task(config, args.task, language=args.language)
    request = SelectionRequest(
        task=base_request.task,
        priority=base_request.priority,
        language=base_request.language,
        device_policy=base_request.device_policy,
        manual_model_id=args.manual_model_id or base_request.manual_model_id,
        allow_experimental=base_request.allow_experimental,
    )
    try:
        results = run_transcription_benchmark(app, cases, request=request, repeat=args.repeat)
    except (BackendUnavailableError, FileNotFoundError, TranscriptionError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    all_summary = summarize_benchmark_results(results)
    warm_summary = summarize_benchmark_results(results, discard_first=True) if args.repeat > 1 else None
    summary = warm_summary if args.discard_first and warm_summary else all_summary
    advice = benchmark_usage_advice(summary, task=args.task)
    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "all_summary": all_summary,
                    "warm_summary": warm_summary,
                    "advice": advice,
                    "results": [
                        benchmark_result_to_dict(result, include_text=args.include_text)
                        for result in results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    for result in results:
        duration = _format_optional_seconds(result.audio_duration_s)
        rtf = _format_optional_float(result.rtf)
        phase = "first" if result.run_index == 1 else "repeat"
        print(
            f"{result.label}\tphase={phase}\tmodel={result.model_id}\tduration={duration}\t"
            f"elapsed={result.elapsed_s:.3f}s\trtf={rtf}\tverdict={result.verdict}"
        )
        if args.include_text:
            print(result.text)
    print(
        f"summary\tcount={summary['count']}\tavg_elapsed={_format_optional_seconds(summary['avg_elapsed_s'])}\t"
        f"avg_rtf={_format_optional_float(summary['avg_rtf'])}\tverdict={summary['verdict']}"
    )
    print(f"advice\t{advice}")
    if warm_summary and not args.discard_first:
        print(
            f"warm_summary\tcount={warm_summary['count']}\t"
            f"avg_elapsed={_format_optional_seconds(warm_summary['avg_elapsed_s'])}\t"
            f"avg_rtf={_format_optional_float(warm_summary['avg_rtf'])}\tverdict={warm_summary['verdict']}"
        )
    return 0


def _run_dictate_loop(app: VoiceInputApp, request: SelectionRequest, args) -> int:
    output_dir = Path(args.output_dir)
    text_out_dir = Path(args.text_out_dir) if args.text_out_dir else None
    srt_out_dir = Path(args.srt_out_dir) if args.srt_out_dir else None
    device = _coerce_device(args.device)
    copy, paste = _voice_output_mode(args, app.config.hotkey.submit_strategy)

    print("Press Enter to record once. Type q then Enter to quit.")
    turn = 0
    while True:
        if args.max_turns is not None and turn >= args.max_turns:
            return 0
        if args.max_turns is None:
            command = input("> ").strip().lower()
            if command in {"q", "quit", "exit"}:
                return 0

        turn += 1
        stem = _dictation_stem(turn)
        audio_path = output_dir / f"{stem}.wav"
        text_path = text_out_dir / f"{stem}.txt" if text_out_dir else None
        srt_path = srt_out_dir / f"{stem}.srt" if srt_out_dir else None
        print(f"recording: {audio_path}")
        try:
            started = perf_counter()
            result = app.listen_once(
                audio_path,
                seconds=args.seconds,
                request=request,
                device=device,
            )
            api_processing = _maybe_process_text_with_api(result.text, app.config, args)
            output_result = _result_for_output_text(result, api_processing)
            text_output = apply_text_outputs(output_result.text, copy=copy, paste=paste, text_path=text_path)
            text_output = _maybe_write_srt(output_result, text_output, srt_path)
            quick_note_result = _maybe_save_quick_note(
                output_result.text,
                app.config,
                args.quick_note,
                route_text=result.text,
            )
            if not args.no_log:
                append_transcription_log(
                    entry_from_result(
                        command="dictate-loop",
                        result=output_result,
                        text_output=text_output,
                        elapsed_s=perf_counter() - started,
                    )
                )
        except (
            ApiProviderError,
            AudioCaptureError,
            BackendUnavailableError,
            TextOutputError,
            TranscriptionError,
            ValueError,
        ) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        print(output_result.text)
        _print_text_output_status(text_output)
        _print_quick_note_status(quick_note_result)


def _run_hold_to_talk(app: VoiceInputApp, request: SelectionRequest, args) -> int:
    hold_key = normalize_hotkey_name(args.hold_key or app.config.hotkey.hold_to_talk)
    quit_key = normalize_hotkey_name(args.quit_key or app.config.hotkey.cancel)
    output_dir = Path(args.output_dir)
    text_out_dir = Path(args.text_out_dir) if args.text_out_dir else None
    srt_out_dir = Path(args.srt_out_dir) if args.srt_out_dir else None
    device = _coerce_device(args.device)
    copy, paste = _voice_output_mode(args, app.config.hotkey.submit_strategy)
    state = {"session": None, "turn": 0}

    print(f"Hold {hold_key!r} to record. Release to transcribe. Press {quit_key!r} to quit.")
    _print_hold_to_talk_startup_summary(args, app.config.hotkey.submit_strategy)
    _print_hold_to_talk_api_summary(args)
    _print_hold_to_talk_quick_note_summary(args, app.config)
    _print_hold_to_talk_device_and_model_summary(app, request, args)

    def on_press() -> None:
        if state["session"] is not None:
            return
        state["turn"] += 1
        stem = _dictation_stem(state["turn"])
        audio_path = output_dir / f"{stem}.wav"
        try:
            session = app.create_recording_session(audio_path, device=device)
            session.start()
        except (AudioCaptureError, ValueError) as exc:
            _print_hold_to_talk_status("failed")
            print(f"error: {exc}", file=sys.stderr)
            return
        state["session"] = (session, stem)
        _print_hold_to_talk_status("recording_started")
        print(f"recording: {audio_path}")

    def on_release() -> None:
        active = state["session"]
        if active is None:
            return
        session, stem = active
        state["session"] = None
        text_path = text_out_dir / f"{stem}.txt" if text_out_dir else None
        srt_path = srt_out_dir / f"{stem}.srt" if srt_out_dir else None
        try:
            started = perf_counter()
            audio_path = session.stop()
            _print_hold_to_talk_status("recording_stopped")
            _print_hold_to_talk_status("transcribing")
            result = app.transcribe_file(audio_path, request=request)
            api_processing = _maybe_process_text_with_api(result.text, app.config, args)
            output_result = _result_for_output_text(result, api_processing)
            text_output = apply_text_outputs(output_result.text, copy=copy, paste=paste, text_path=text_path)
            text_output = _maybe_write_srt(output_result, text_output, srt_path)
            quick_note_result = _maybe_save_quick_note(
                output_result.text,
                app.config,
                args.quick_note,
                route_text=result.text,
            )
            if not args.no_log:
                append_transcription_log(
                    entry_from_result(
                        command="hold-to-talk",
                        result=output_result,
                        text_output=text_output,
                        elapsed_s=perf_counter() - started,
                    )
                )
        except (
            ApiProviderError,
            AudioCaptureError,
            BackendUnavailableError,
            TextOutputError,
            TranscriptionError,
            ValueError,
        ) as exc:
            _print_hold_to_talk_status("failed")
            print(f"error: {exc}", file=sys.stderr)
            return
        print(output_result.text)
        _print_text_output_status(text_output)
        _print_quick_note_status(quick_note_result)
        _print_hold_to_talk_status("completed")

    try:
        PushToTalkHotkeyRunner(
            on_press=on_press,
            on_release=on_release,
            names=HotkeyNames(hold_to_talk=hold_key, quit=quit_key),
        ).run_until_quit()
    except (AudioCaptureError, HotkeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _dictation_stem(turn: int) -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"dictation-{timestamp}-{turn:03d}"


def _maybe_write_srt(result, text_output, srt_path):
    if not srt_path:
        return text_output
    try:
        written = write_srt_file(result, srt_path)
    except OSError as exc:
        raise TextOutputError(f"failed to write SRT to {srt_path}: {exc}") from exc
    return replace(text_output, srt_path=written)


def _add_api_processing_arguments(parser) -> None:
    parser.add_argument("--api-process", action="store_true", help="Process recognized text with the configured API provider before output.")
    parser.add_argument("--api-preset", choices=sorted(POSTPROCESS_PRESETS), default="clean")
    parser.add_argument("--api-system-prompt", default=None)
    parser.add_argument("--api-temperature", type=float, default=0.2)
    parser.add_argument("--api-max-tokens", type=int, default=512)
    parser.add_argument("--api-fallback-raw", action="store_true", help="If API processing fails, keep the raw ASR text instead of failing.")


def _maybe_process_text_with_api(text: str, config, args) -> ApiProcessingSummary:
    if not getattr(args, "api_process", False):
        return ApiProcessingSummary(enabled=False, processed=False, raw_text=text, text=text)
    context_package = build_api_context_package(config)
    api_text = format_api_context_user_text(text, context_package)
    try:
        result = call_chat_completion(
            config.api_provider,
            api_text,
            system_prompt=_api_system_prompt_from_args(args),
            temperature=args.api_temperature,
            max_tokens=args.api_max_tokens,
        )
    except ApiProviderError as exc:
        if getattr(args, "api_fallback_raw", False):
            return ApiProcessingSummary(
                enabled=True,
                processed=False,
                raw_text=text,
                text=text,
                error=str(exc),
                context_mode=context_package.mode,
                context_recent_count=len(context_package.recent_texts),
                context_glossary_count=len(context_package.glossary_terms),
            )
        raise
    return ApiProcessingSummary(
        enabled=True,
        processed=True,
        raw_text=text,
        text=result.text,
        provider=result.provider,
        model=result.model,
        endpoint=result.endpoint,
        context_mode=context_package.mode,
        context_recent_count=len(context_package.recent_texts),
        context_glossary_count=len(context_package.glossary_terms),
    )


def _result_for_output_text(result, api_processing: ApiProcessingSummary):
    if not api_processing.enabled:
        return result
    metadata = dict(result.metadata)
    metadata["api_process_enabled"] = "true"
    metadata["api_process_processed"] = "true" if api_processing.processed else "false"
    if api_processing.provider:
        metadata["api_provider"] = api_processing.provider
    if api_processing.model:
        metadata["api_model"] = api_processing.model
    if api_processing.error:
        metadata["api_process_error"] = api_processing.error
    metadata["api_context_mode"] = api_processing.context_mode
    metadata["api_context_recent_count"] = str(api_processing.context_recent_count)
    metadata["api_context_glossary_count"] = str(api_processing.context_glossary_count)
    return replace(result, text=api_processing.text, metadata=metadata)


def _api_system_prompt_from_args(args, *, provider_test: bool = False) -> str:
    preset_attr = "preset" if provider_test else "api_preset"
    prompt_attr = "system_prompt" if provider_test else "api_system_prompt"
    preset = getattr(args, preset_attr, None)
    prompt = getattr(args, prompt_attr, None)
    if prompt:
        return prompt
    if preset:
        return get_postprocess_prompt(preset)
    return DEFAULT_SYSTEM_PROMPT


def _api_prompt_source_summary(args) -> str:
    if getattr(args, "api_system_prompt", None):
        return "prompt_source=custom:--api-system-prompt"
    preset = getattr(args, "api_preset", None)
    if preset:
        return f"prompt_source=preset:{preset}"
    return "prompt_source=default"


def _voice_output_mode(args, submit_strategy: str) -> tuple[bool, bool]:
    strategy = _effective_submit_strategy(args, submit_strategy)
    if strategy == "clipboard_paste":
        return (False, True)
    if strategy == "clipboard_only":
        return (True, False)
    if getattr(args, "copy", False):
        return (True, False)
    return (False, False)


def _effective_submit_strategy(args, submit_strategy: str) -> str:
    if getattr(args, "no_paste", False):
        if getattr(args, "copy", False):
            return "clipboard_only"
        return "terminal_only"
    if getattr(args, "clipboard_only", False):
        return "clipboard_only"
    if submit_strategy == "clipboard_paste":
        return "clipboard_paste"
    if submit_strategy == "clipboard_only":
        return "clipboard_only"
    if submit_strategy == "type_text":
        return "type_text"
    if getattr(args, "copy", False):
        return "clipboard_only"
    return "terminal_only"


def _effective_input_device(args, configured_input_device: int | str | None) -> int | str | None:
    explicit = _coerce_device(getattr(args, "device", None))
    if explicit is not None:
        return explicit
    return configured_input_device


def _effective_input_device_source(args, configured_input_device: int | str | None) -> str:
    explicit = _coerce_device(getattr(args, "device", None))
    if explicit is not None:
        return "cli_override"
    if configured_input_device is not None:
        return "config_fixed"
    return "system_default"


def _input_device_source_summary(source: str) -> str:
    if source == "cli_override":
        return "cli_override (命令行临时指定)"
    if source == "config_fixed":
        return "config_fixed (配置里的固定设备)"
    if source == "system_default":
        return "system_default (系统默认设备)"
    return source


def _input_device_summary(device: int | str | None) -> str:
    if device is None:
        return "auto (自动/系统默认设备)"
    return f"{device} (固定设备)"


def _language_summary(language: str | None) -> str:
    if not language or language == "auto":
        return "auto (自动判断语言)"
    if language == "zh":
        return "zh (固定中文识别)"
    if language == "en":
        return "en (固定英文识别)"
    return f"{language} (固定识别语言)"


def _submit_strategy_label(strategy: str) -> str:
    if strategy == "clipboard_paste":
        return "自动粘贴到当前光标"
    if strategy == "clipboard_only":
        return "只复制到剪贴板"
    if strategy == "type_text":
        return "模拟键盘逐字输入"
    if strategy == "terminal_only":
        return "只在终端显示/调试"
    return strategy


def _format_optional_seconds(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.3f}s"


def _format_optional_float(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
