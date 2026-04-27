import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.asr import TranscriptionResult
from local_voice_input.benchmark import (
    BenchmarkCase,
    result_to_dict,
    run_transcription_benchmark,
    summarize_benchmark_results,
    usage_advice,
)
from local_voice_input.model_selector import SelectionRequest


class FakeBenchmarkApp:
    def transcribe_file(self, path, request=None):
        return TranscriptionResult(
            text="hello",
            model_id=request.manual_model_id or "fake-model",
            language=request.language,
            metadata={"duration_s": "10.0"},
        )


class BenchmarkTests(unittest.TestCase):
    def test_run_transcription_benchmark_computes_rtf(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.wav"
            path.write_bytes(b"fake")

            results = run_transcription_benchmark(
                FakeBenchmarkApp(),
                (BenchmarkCase(path, "sample"),),
                request=SelectionRequest(language="zh", manual_model_id="manual"),
                repeat=2,
            )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].label, "sample#1")
        self.assertEqual(results[0].run_index, 1)
        self.assertEqual(results[1].run_index, 2)
        self.assertEqual(results[0].model_id, "manual")
        self.assertAlmostEqual(results[0].audio_duration_s, 10.0)
        self.assertIsNotNone(results[0].rtf)

    def test_summarize_benchmark_results_returns_overall_verdict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.wav"
            path.write_bytes(b"fake")

            results = run_transcription_benchmark(
                FakeBenchmarkApp(),
                (BenchmarkCase(path),),
                request=SelectionRequest(),
            )

        summary = summarize_benchmark_results(results)

        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["total_count"], 1)
        self.assertEqual(summary["discarded_first_count"], 0)
        self.assertIn(summary["verdict"], {"fast", "usable", "slow", "too_slow"})

    def test_summarize_benchmark_results_can_discard_first_runs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.wav"
            path.write_bytes(b"fake")

            results = run_transcription_benchmark(
                FakeBenchmarkApp(),
                (BenchmarkCase(path),),
                request=SelectionRequest(),
                repeat=3,
            )

        summary = summarize_benchmark_results(results, discard_first=True)

        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["total_count"], 3)
        self.assertEqual(summary["discarded_first_count"], 1)

    def test_result_to_dict_omits_text_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.wav"
            path.write_bytes(b"fake")
            result = run_transcription_benchmark(
                FakeBenchmarkApp(),
                (BenchmarkCase(path),),
                request=SelectionRequest(),
            )[0]

        data = result_to_dict(result)

        self.assertNotIn("text", data)
        self.assertEqual(data["text_length"], 5)
        self.assertEqual(data["phase"], "first")

    def test_usage_advice_reports_fast_dictation_as_short_phrase_ready(self):
        advice = usage_advice({"avg_rtf": 0.2, "worst_rtf": 0.24}, task="dictation")

        self.assertIn("热键短句输入", advice)

    def test_usage_advice_warns_against_long_class_when_too_slow(self):
        advice = usage_advice({"avg_rtf": 1.2, "worst_rtf": 1.3}, task="long_form")

        self.assertIn("不建议直接转整节长课", advice)


if __name__ == "__main__":
    unittest.main()
