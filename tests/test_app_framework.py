import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_bootstrap  # noqa: F401

from local_voice_input.app import VoiceInputApp
from local_voice_input.asr import BackendUnavailableError, TranscriptionJob, TranscriptionResult
from local_voice_input.backends import BackendRegistry
from local_voice_input.backends import create_default_backend_registry
from local_voice_input.config import (
    AppConfig,
    AudioConfig,
    ApiContextConfig,
    ApiProcessingConfig,
    QuickCaptureConfig,
    QuickCaptureRule,
    RemoteAsrConfig,
    RemoteAsrProfileConfig,
    add_hotwords,
    load_config,
    save_config,
    selection_for_task,
    set_hotwords_enabled,
    update_api_provider,
    update_config,
    update_task_route,
)
from local_voice_input.model_selector import HardwareInfo, ModelProfile, SelectionRequest
from local_voice_input.model_selector import get_model_profiles


class FakeBackend:
    backend_id = "fake"

    def is_available(self):
        return True

    def transcribe_file(self, job: TranscriptionJob, profile: ModelProfile):
        return TranscriptionResult(text=f"ok:{job.source_path.name}", model_id=profile.model_id)


class AppFrameworkTests(unittest.TestCase):
    def test_app_delegates_file_transcription_to_registered_backend(self):
        profile = ModelProfile(
            model_id="fake-model",
            display_name="Fake Model",
            backend="fake",
            min_ram_gb=1,
            recommended_ram_gb=1,
            task_fit=("file_transcription",),
        )
        registry = BackendRegistry()
        registry.register("fake", lambda _profile: FakeBackend())
        app = VoiceInputApp(
            backend_registry=registry,
            model_profiles=(profile,),
            hardware_probe=lambda: HardwareInfo(os_name="Windows", cpu_threads=4, ram_gb=8),
        )

        result = app.transcribe_file(
            "sample.wav",
            request=SelectionRequest(task="file_transcription", manual_model_id="fake-model"),
        )

        self.assertEqual(result.text, "ok:sample.wav")
        self.assertEqual(result.model_id, "fake-model")

    def test_default_backend_registry_fails_clearly_until_integrations_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"OPEN_VOICE_INPUT_MODEL_DIR": temp_dir}):
                app = VoiceInputApp(hardware_probe=lambda: HardwareInfo(os_name="Windows", cpu_threads=4, ram_gb=8))

                with self.assertRaises(BackendUnavailableError):
                    app.transcribe_file("sample.wav")

    def test_remote_asr_backend_reports_disabled_config_without_http(self):
        profile = next(
            profile for profile in get_model_profiles() if profile.model_id == "remote-4090-qwen3-asr-1.7b"
        )
        backend = create_default_backend_registry(config=AppConfig()).create(profile)

        self.assertFalse(backend.is_available())
        self.assertIn("remote_asr is disabled", backend.unavailable_reason())

        with self.assertRaisesRegex(BackendUnavailableError, "remote_asr is disabled"):
            backend.transcribe_file(TranscriptionJob(Path("sample.wav")), profile)

    def test_remote_asr_backend_reports_missing_base_url(self):
        profile = next(
            profile for profile in get_model_profiles() if profile.model_id == "remote-4090-qwen3-asr-1.7b"
        )
        config = AppConfig(
            remote_asr=RemoteAsrConfig(
                enabled=True,
                profile="home_4090",
                profiles={"home_4090": RemoteAsrProfileConfig()},
            )
        )
        backend = create_default_backend_registry(config=config).create(profile)

        self.assertFalse(backend.is_available())
        self.assertIn("missing base_url", backend.unavailable_reason())

    def test_remote_asr_backend_reports_unimplemented_transport_after_configuration(self):
        profile = next(
            profile for profile in get_model_profiles() if profile.model_id == "remote-4090-qwen3-asr-1.7b"
        )
        config = AppConfig(
            remote_asr=RemoteAsrConfig(
                enabled=True,
                profile="home_4090",
                profiles={
                    "home_4090": RemoteAsrProfileConfig(
                        base_url="http://192.168.1.50:8765",
                    )
                },
            )
        )
        backend = create_default_backend_registry(config=config).create(profile)

        self.assertFalse(backend.is_available())
        self.assertIn("HTTP transport is not implemented", backend.unavailable_reason())

    def test_voice_input_app_uses_remote_asr_config_in_default_registry(self):
        config = AppConfig(
            selection=SelectionRequest(
                task="file_transcription",
                manual_model_id="remote-4090-qwen3-asr-1.7b",
                allow_experimental=True,
            ),
            remote_asr=RemoteAsrConfig(
                enabled=True,
                profile="home_4090",
                profiles={
                    "home_4090": RemoteAsrProfileConfig(
                        base_url="http://192.168.1.50:8765",
                    )
                },
            ),
        )
        app = VoiceInputApp(
            config=config,
            hardware_probe=lambda: HardwareInfo(os_name="Windows", cpu_threads=16, ram_gb=32),
        )

        with self.assertRaisesRegex(BackendUnavailableError, "HTTP transport is not implemented"):
            app.transcribe_file("sample.wav")

    def test_config_round_trip_preserves_nested_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            config = AppConfig(
                selection=SelectionRequest(language="zh", priority="speed"),
                audio=AudioConfig(sample_rate_hz=48000),
                api_processing=ApiProcessingConfig(enabled=True, preset="formal", fallback_raw=True),
                api_context=ApiContextConfig(
                    mode="lightweight",
                    recent_turns=3,
                    max_context_chars=1200,
                    glossary_enabled=True,
                    compression_enabled=False,
                    compressed_summary_chars=800,
                ),
                quick_capture=QuickCaptureConfig(
                    root_dir="notes",
                    rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
                ),
                remote_asr=RemoteAsrConfig(
                    enabled=True,
                    profile="home_4090",
                    profiles={
                        "home_4090": RemoteAsrProfileConfig(
                            base_url="http://192.168.1.50:8765",
                            api_key_env="REMOTE_ASR_KEY",
                            timeout_s=120,
                            connect_timeout_s=5,
                            fallback_model_id="sensevoice-small-onnx-int8",
                        )
                    },
                ),
            )

            save_config(config, path)
            loaded = load_config(path)

        self.assertEqual(loaded.selection.language, "zh")
        self.assertEqual(loaded.selection.priority, "speed")
        self.assertEqual(loaded.audio.sample_rate_hz, 48000)
        self.assertTrue(loaded.api_processing.enabled)
        self.assertEqual(loaded.api_processing.preset, "formal")
        self.assertTrue(loaded.api_processing.fallback_raw)
        self.assertEqual(loaded.api_context.mode, "lightweight")
        self.assertEqual(loaded.api_context.recent_turns, 3)
        self.assertEqual(loaded.api_context.max_context_chars, 1200)
        self.assertTrue(loaded.api_context.glossary_enabled)
        self.assertFalse(loaded.api_context.compression_enabled)
        self.assertEqual(loaded.api_context.compressed_summary_chars, 800)
        self.assertEqual(loaded.quick_capture.rules[0].keywords, ("灵感",))
        self.assertTrue(loaded.remote_asr.enabled)
        self.assertEqual(loaded.remote_asr.profile, "home_4090")
        self.assertEqual(loaded.remote_asr.profiles["home_4090"].base_url, "http://192.168.1.50:8765")
        self.assertEqual(loaded.remote_asr.profiles["home_4090"].api_key_env, "REMOTE_ASR_KEY")
        self.assertEqual(loaded.remote_asr.profiles["home_4090"].fallback_model_id, "sensevoice-small-onnx-int8")

    def test_config_loads_legacy_input_device_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                '{"audio": {"input_device_name": "Mic", "sample_rate_hz": 16000}}',
                encoding="utf-8",
            )

            loaded = load_config(path)

        self.assertEqual(loaded.audio.input_device, "Mic")

    def test_update_config_changes_nested_fields(self):
        config = update_config(
            AppConfig(),
            language="zh",
            input_device=1,
            sample_rate_hz=48000,
            keep_audio_files=True,
            hold_to_talk="f8",
            submit_strategy="clipboard_only",
            api_process_enabled=True,
            api_preset="todo",
            api_fallback_raw=True,
            api_context_mode="lightweight",
            api_context_recent_turns=5,
            api_context_max_chars=2000,
            api_context_glossary_enabled=False,
            api_context_compression_enabled=True,
            api_context_compressed_summary_chars=900,
        )

        self.assertEqual(config.selection.language, "zh")
        self.assertEqual(config.audio.input_device, 1)
        self.assertEqual(config.audio.sample_rate_hz, 48000)
        self.assertTrue(config.recording.keep_audio_files)
        self.assertEqual(config.hotkey.hold_to_talk, "f8")
        self.assertEqual(config.hotkey.submit_strategy, "clipboard_only")
        self.assertTrue(config.api_processing.enabled)
        self.assertEqual(config.api_processing.preset, "todo")
        self.assertTrue(config.api_processing.fallback_raw)
        self.assertEqual(config.api_context.mode, "lightweight")
        self.assertEqual(config.api_context.recent_turns, 5)
        self.assertEqual(config.api_context.max_context_chars, 2000)
        self.assertFalse(config.api_context.glossary_enabled)
        self.assertTrue(config.api_context.compression_enabled)
        self.assertEqual(config.api_context.compressed_summary_chars, 900)

    def test_api_context_config_defaults_and_clamps_loaded_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                (
                    '{"api_context": {'
                    '"mode": "surprise", '
                    '"recent_turns": -2, '
                    '"max_context_chars": 999999, '
                    '"compressed_summary_chars": "bad"'
                    '}}'
                ),
                encoding="utf-8",
            )

            loaded = load_config(path)

        self.assertEqual(loaded.api_context.mode, "off")
        self.assertEqual(loaded.api_context.recent_turns, 0)
        self.assertEqual(loaded.api_context.max_context_chars, 20000)
        self.assertEqual(loaded.api_context.compressed_summary_chars, 800)

    def test_remote_asr_config_defaults_and_clamps_loaded_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                (
                    '{"remote_asr": {'
                    '"enabled": "true", '
                    '"profile": " lab ", '
                    '"profiles": {'
                    '" lab ": {'
                    '"base_url": " https://asr.example.test/ ", '
                    '"api_key_env": " REMOTE_KEY ", '
                    '"timeout_s": 999999, '
                    '"connect_timeout_s": 0, '
                    '"upload_mode": "path", '
                    '"fallback_model_id": " sensevoice-small-onnx-int8 ", '
                    '"max_audio_mb": 999999, '
                    '"verify_tls": "false"'
                    '}, '
                    '"bad": "ignored"'
                    '}'
                    '}}'
                ),
                encoding="utf-8",
            )

            loaded = load_config(path)

        self.assertTrue(loaded.remote_asr.enabled)
        self.assertEqual(loaded.remote_asr.profile, "lab")
        self.assertIn("lab", loaded.remote_asr.profiles)
        profile = loaded.remote_asr.profiles["lab"]
        self.assertEqual(profile.base_url, "https://asr.example.test")
        self.assertEqual(profile.api_key_env, "REMOTE_KEY")
        self.assertEqual(profile.timeout_s, 3600.0)
        self.assertEqual(profile.connect_timeout_s, 1.0)
        self.assertEqual(profile.upload_mode, "multipart")
        self.assertEqual(profile.fallback_model_id, "sensevoice-small-onnx-int8")
        self.assertEqual(profile.max_audio_mb, 2048)
        self.assertFalse(profile.verify_tls)

    def test_remote_asr_config_creates_missing_selected_profile(self):
        loaded = AppConfig.from_dict({"remote_asr": {"profile": "lab", "profiles": {}}})

        self.assertEqual(loaded.remote_asr.profile, "lab")
        self.assertIn("lab", loaded.remote_asr.profiles)
        self.assertEqual(loaded.remote_asr.profiles["lab"].upload_mode, "multipart")

    def test_selection_for_task_uses_task_route_defaults(self):
        config = AppConfig(selection=SelectionRequest(language="zh", device_policy="auto"))

        dictation = selection_for_task(config, "dictation")
        file_transcription = selection_for_task(config, "file_transcription")

        self.assertEqual(dictation.task, "dictation")
        self.assertEqual(dictation.priority, "speed")
        self.assertEqual(file_transcription.task, "file_transcription")
        self.assertEqual(file_transcription.priority, "balanced")

    def test_update_task_route_can_set_task_specific_model(self):
        config = update_task_route(
            AppConfig(),
            "file_transcription",
            priority="accuracy",
            background=True,
            manual_model_id="vibevoice-asr-hf-8b",
        )

        request = selection_for_task(config, "file_transcription")

        self.assertEqual(request.priority, "accuracy")
        self.assertEqual(request.manual_model_id, "vibevoice-asr-hf-8b")
        self.assertTrue(config.task_routes.file_transcription.background)

    def test_hotword_helpers_dedupe_and_toggle(self):
        config = add_hotwords(AppConfig(), ("Codex", "Codex", "  语音输入  "))
        config = set_hotwords_enabled(config, False)

        self.assertEqual(config.hotwords.words, ("Codex", "语音输入"))
        self.assertFalse(config.hotwords.enabled)

    def test_update_api_provider_preserves_missing_fields(self):
        config = update_api_provider(
            AppConfig(),
            provider="siliconflow",
            base_url="https://api.siliconflow.cn/v1",
            api_key_env="SILICONFLOW_API_KEY",
            model="example-model",
        )

        self.assertEqual(config.api_provider.provider, "siliconflow")
        self.assertEqual(config.api_provider.api_key_env, "SILICONFLOW_API_KEY")
        self.assertEqual(config.api_provider.timeout_s, 30.0)
