import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_bootstrap  # noqa: F401

from local_voice_input.asr import TranscriptionJob
from local_voice_input.model_selector import ModelProfile
from local_voice_input.sherpa_backend import (
    SENSEVOICE_DIR_NAME,
    SENSEVOICE_INT8_DIR_NAME,
    SenseVoiceModelFiles,
    SherpaOnnxSenseVoiceBackend,
    default_model_root,
)


class SherpaBackendTests(unittest.TestCase):
    def test_discovers_sensevoice_model_files_in_default_archive_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / SENSEVOICE_DIR_NAME
            model_dir.mkdir()
            model = model_dir / "model.int8.onnx"
            tokens = model_dir / "tokens.txt"
            model.write_bytes(b"fake")
            tokens.write_text("a 0\n", encoding="utf-8")

            files = SenseVoiceModelFiles.discover(temp_dir)

            self.assertEqual(files.model, model)
            self.assertEqual(files.tokens, tokens)
            self.assertEqual(files.missing_paths(), ())

    def test_discovers_official_int8_archive_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / SENSEVOICE_INT8_DIR_NAME
            model_dir.mkdir()
            model = model_dir / "model.int8.onnx"
            tokens = model_dir / "tokens.txt"
            model.write_bytes(b"fake")
            tokens.write_text("a 0\n", encoding="utf-8")

            files = SenseVoiceModelFiles.discover(temp_dir)

            self.assertEqual(files.model, model)
            self.assertEqual(files.tokens, tokens)

    def test_backend_reports_missing_model_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = SherpaOnnxSenseVoiceBackend(model_root=temp_dir)

            reason = backend.unavailable_reason()

        self.assertIsNotNone(reason)
        self.assertIn("missing model files", reason)

    def test_default_model_root_prefers_existing_project_models_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_models = Path(temp_dir) / "project-models"
            cwd_models = Path(temp_dir) / "cwd-models"
            project_models.mkdir()

            with patch(
                "local_voice_input.sherpa_backend._default_model_root_candidates",
                return_value=(project_models, cwd_models),
            ):
                root = default_model_root()

        self.assertEqual(root, project_models)

    def test_transcribe_file_uses_model_filenames_from_model_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / SENSEVOICE_DIR_NAME
            model_dir.mkdir()
            (model_dir / "model.int8.onnx").write_bytes(b"fake")
            (model_dir / "tokens.txt").write_text("a 0\n", encoding="utf-8")
            audio_path = Path(temp_dir) / "sample.wav"
            audio_path.write_bytes(b"fake")
            calls = {}

            class FakeStream:
                def __init__(self):
                    self.result = types.SimpleNamespace(text="ok")

                def accept_waveform(self, sample_rate, samples):
                    calls["accept_waveform"] = (sample_rate, samples)

            class FakeRecognizer:
                @classmethod
                def from_sense_voice(cls, **kwargs):
                    calls["cwd"] = os.getcwd()
                    calls["kwargs"] = kwargs
                    return cls()

                def create_stream(self):
                    return FakeStream()

                def decode_stream(self, stream):
                    calls["decoded"] = True

            fake_sherpa = types.SimpleNamespace(OfflineRecognizer=FakeRecognizer)
            fake_soundfile = types.SimpleNamespace(read=lambda *_args, **_kwargs: ([0.1, 0.2], 16000))
            backend = SherpaOnnxSenseVoiceBackend(model_root=temp_dir)
            profile = ModelProfile(
                model_id="sensevoice-small-onnx-int8",
                display_name="SenseVoice Small",
                backend="sherpa-onnx",
                min_ram_gb=4,
                recommended_ram_gb=8,
            )
            previous_cwd = os.getcwd()

            with patch.dict(sys.modules, {"sherpa_onnx": fake_sherpa, "soundfile": fake_soundfile}):
                result = backend.transcribe_file(
                    TranscriptionJob(source_path=audio_path, language="zh"),
                    profile,
                )

        self.assertEqual(result.text, "ok")
        self.assertEqual(calls["kwargs"]["model"], "model.int8.onnx")
        self.assertEqual(calls["kwargs"]["tokens"], "tokens.txt")
        self.assertEqual(Path(calls["cwd"]), model_dir)
        self.assertEqual(os.getcwd(), previous_cwd)
