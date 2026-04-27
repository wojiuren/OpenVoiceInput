import unittest

import test_bootstrap  # noqa: F401

from local_voice_input.model_selector import (
    GpuInfo,
    HardwareInfo,
    SelectionRequest,
    select_model,
)


class ModelSelectorTests(unittest.TestCase):
    def test_cpu_only_dictation_prefers_small_model(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=8, ram_gb=8, gpus=())

        result = select_model(
            SelectionRequest(task="dictation", priority="auto", language="zh"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "sensevoice-small-onnx-int8")
        self.assertEqual(result.warnings, ())

    def test_nvidia_high_vram_prefers_larger_dictation_model(self):
        hardware = HardwareInfo(
            os_name="Windows",
            cpu_threads=16,
            ram_gb=32,
            gpus=(GpuInfo(vendor="nvidia", name="RTX", vram_gb=12),),
        )

        result = select_model(
            SelectionRequest(task="dictation", priority="accuracy"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "qwen3-asr-1.7b-q4")
        self.assertEqual(result.warnings, ())

    def test_long_form_on_large_gpu_prefers_vibevoice(self):
        hardware = HardwareInfo(
            os_name="Windows",
            cpu_threads=24,
            ram_gb=64,
            gpus=(GpuInfo(vendor="nvidia", name="RTX", vram_gb=24),),
        )

        result = select_model(
            SelectionRequest(task="long_form", priority="accuracy"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "vibevoice-asr-hf-8b")
        self.assertEqual(result.warnings, ())

    def test_manual_selection_returns_warnings_instead_of_overriding(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=4, ram_gb=8, gpus=())

        result = select_model(
            SelectionRequest(manual_model_id="vibevoice-asr-hf-8b"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "vibevoice-asr-hf-8b")
        self.assertTrue(result.warnings)

    def test_stable_only_excludes_experimental_profiles(self):
        hardware = HardwareInfo(
            os_name="Windows",
            cpu_threads=16,
            ram_gb=32,
            gpus=(GpuInfo(vendor="nvidia", name="RTX", vram_gb=12),),
        )

        result = select_model(
            SelectionRequest(task="dictation", priority="accuracy", allow_experimental=False),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "whisper-small-ctranslate2")

    def test_cpu_policy_allows_cpu_capable_profiles_with_optional_vram(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=12, ram_gb=16, gpus=())

        result = select_model(
            SelectionRequest(task="dictation", priority="accuracy", device_policy="cpu"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "funasr-nano-gguf")
        self.assertEqual(result.warnings, ())

    def test_fun_asr_15_dialect_profile_is_manual_special_project(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=12, ram_gb=16, gpus=())

        result = select_model(
            SelectionRequest(manual_model_id="fun-asr-1.5-dialect-api"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.backend, "aliyun-bailian-api")
        self.assertTrue(result.profile.experimental)
        self.assertIn("yue", result.profile.languages)

    def test_nemotron_profile_is_english_experiment(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=12, ram_gb=16, gpus=())

        result = select_model(
            SelectionRequest(manual_model_id="nemotron-speech-streaming-en-0.6b-foundry-local"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.backend, "foundry-local")
        self.assertEqual(result.profile.languages, ("en",))
        self.assertTrue(result.profile.experimental)

    def test_qwen3_06b_profile_tracks_gguf_7840hs_candidate(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=16, ram_gb=32, gpus=())

        result = select_model(
            SelectionRequest(manual_model_id="qwen3-asr-0.6b"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.backend, "qwen3-asr-gguf")
        self.assertEqual(result.profile.preferred_device, "auto")
        self.assertIn("7840HS", result.profile.notes)

    def test_remote_4090_profile_is_registered_as_experimental_asr_backend(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=16, ram_gb=32, gpus=())

        result = select_model(
            SelectionRequest(manual_model_id="remote-4090-qwen3-asr-1.7b"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.backend, "remote-asr")
        self.assertTrue(result.profile.experimental)
        self.assertIn("long_form", result.profile.task_fit)
        self.assertIn("remote_asr", result.profile.notes)

    def test_7840hs_default_still_keeps_stable_sensevoice_until_benchmarked(self):
        hardware = HardwareInfo(os_name="Windows", cpu_threads=16, ram_gb=32, gpus=())

        result = select_model(
            SelectionRequest(task="dictation", priority="auto", language="zh"),
            hardware=hardware,
        )

        self.assertEqual(result.profile.model_id, "sensevoice-small-onnx-int8")


if __name__ == "__main__":
    unittest.main()
