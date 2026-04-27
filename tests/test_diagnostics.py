import unittest
from unittest.mock import patch

import test_bootstrap  # noqa: F401

from local_voice_input.diagnostics import (
    DiagnosticCheck,
    _sensevoice_model_check,
    format_diagnostics,
    has_failures,
    run_diagnostics,
)


class DiagnosticsTests(unittest.TestCase):
    def test_format_diagnostics_marks_ok_and_fail(self):
        text = format_diagnostics(
            (
                DiagnosticCheck(name="a", ok=True, message="ready"),
                DiagnosticCheck(name="b", ok=False, message="missing"),
            )
        )

        self.assertIn("OK\ta\tready", text)
        self.assertIn("FAIL\tb\tmissing", text)

    def test_has_failures_detects_failed_check(self):
        checks = (
            DiagnosticCheck(name="a", ok=True, message="ready"),
            DiagnosticCheck(name="b", ok=False, message="missing"),
        )

        self.assertTrue(has_failures(checks))

    def test_run_diagnostics_can_skip_transcribe_smoke(self):
        with patch("local_voice_input.diagnostics._transcribe_smoke_check") as smoke:
            checks = run_diagnostics(run_transcribe_smoke=False)

        smoke.assert_not_called()
        self.assertTrue(checks)

    def test_missing_sensevoice_model_check_suggests_download_command(self):
        class FakeBackend:
            def unavailable_reason(self):
                return "missing model files: model.int8.onnx, tokens.txt"

        with patch("local_voice_input.diagnostics.SherpaOnnxSenseVoiceBackend", return_value=FakeBackend()):
            check = _sensevoice_model_check()

        self.assertFalse(check.ok)
        self.assertIn("download-model sensevoice-small-onnx-int8", check.message)
