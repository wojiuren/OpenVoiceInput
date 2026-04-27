import tarfile
import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.model_download import (
    DEFAULT_SENSEVOICE_MODEL_ID,
    DEFAULT_SENSEVOICE_DOWNLOAD_URL,
    download_sensevoice_model,
    sensevoice_install_plan,
    sensevoice_setup_command,
)
from local_voice_input.sherpa_backend import SENSEVOICE_DIR_NAME, SENSEVOICE_INT8_DIR_NAME, SenseVoiceModelFiles


class ModelDownloadTests(unittest.TestCase):
    def test_sensevoice_install_plan_uses_default_target_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = sensevoice_install_plan(model_root=temp_dir)

        self.assertEqual(plan.model_id, DEFAULT_SENSEVOICE_MODEL_ID)
        self.assertEqual(plan.url, DEFAULT_SENSEVOICE_DOWNLOAD_URL)
        self.assertEqual(plan.target_dir.name, SENSEVOICE_DIR_NAME)
        self.assertTrue(str(plan.required_files[0]).endswith("model.int8.onnx"))
        self.assertIn(DEFAULT_SENSEVOICE_MODEL_ID, sensevoice_setup_command())

    def test_download_sensevoice_model_from_local_archive_installs_expected_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            archive = temp / "sensevoice.tar.bz2"
            source_dir = temp / SENSEVOICE_INT8_DIR_NAME
            source_dir.mkdir()
            (source_dir / "model.int8.onnx").write_bytes(b"fake-model")
            (source_dir / "tokens.txt").write_text("a 0\n", encoding="utf-8")

            with tarfile.open(archive, "w:bz2") as tar:
                tar.add(source_dir, arcname=SENSEVOICE_INT8_DIR_NAME)

            model_root = temp / "models"
            result = download_sensevoice_model(model_root=model_root, url=archive.as_uri())

            installed = SenseVoiceModelFiles.discover(model_root)

            self.assertEqual(result.status, "installed")
            self.assertEqual(installed.model, model_root / SENSEVOICE_DIR_NAME / "model.int8.onnx")
            self.assertEqual(installed.tokens, model_root / SENSEVOICE_DIR_NAME / "tokens.txt")
            self.assertEqual(installed.missing_paths(), ())
