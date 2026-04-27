import unittest
from unittest.mock import patch

import test_bootstrap  # noqa: F401

from local_voice_input.diagnostics import DiagnosticCheck, format_diagnostics, has_failures, run_diagnostics


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
