import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.asr import TranscriptionResult, TranscriptionSegment
from local_voice_input.subtitles import format_srt, format_srt_timestamp, write_srt_file


class SubtitleTests(unittest.TestCase):
    def test_format_srt_timestamp(self):
        self.assertEqual(format_srt_timestamp(3661.234), "01:01:01,234")

    def test_format_srt_uses_existing_segments(self):
        result = TranscriptionResult(
            text="ignored",
            model_id="model",
            segments=(
                TranscriptionSegment(text="hello", start_s=0.0, end_s=1.2),
                TranscriptionSegment(text="world", start_s=1.2, end_s=2.4, speaker="A"),
            ),
        )

        srt = format_srt(result)

        self.assertIn("1\n00:00:00,000 --> 00:00:01,200\nhello", srt)
        self.assertIn("2\n00:00:01,200 --> 00:00:02,400\nA: world", srt)

    def test_format_srt_falls_back_to_single_full_duration_segment(self):
        result = TranscriptionResult(
            text="整段文本",
            model_id="model",
            metadata={"duration_s": "5.5"},
        )

        srt = format_srt(result)

        self.assertEqual(srt, "1\n00:00:00,000 --> 00:00:05,500\n整段文本\n")

    def test_write_srt_file(self):
        result = TranscriptionResult(text="hello", model_id="model", metadata={"duration_s": "1.0"})
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "out.srt"

            written = write_srt_file(result, path)

            self.assertEqual(written, path)
            self.assertTrue(path.read_text(encoding="utf-8").startswith("1\n"))
