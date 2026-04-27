import json
import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.asr import TranscriptionResult
from local_voice_input.text_output import TextOutputResult
from local_voice_input.usage_log import TranscriptionLogEntry, append_transcription_log, entry_from_result


class UsageLogTests(unittest.TestCase):
    def test_append_transcription_log_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "log.jsonl"
            append_transcription_log(
                TranscriptionLogEntry(
                    command="transcribe",
                    audio_path="a.wav",
                    model_id="model",
                    language="zh",
                    text_length=2,
                    created_at="2026-04-23T00:00:00+00:00",
                ),
                path=path,
            )

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["command"], "transcribe")
        self.assertEqual(data["audio_path"], "a.wav")
        self.assertEqual(data["text_length"], 2)
        self.assertEqual(data["text"], "")

    def test_entry_from_result_uses_metadata_and_output_state(self):
        result = TranscriptionResult(
            text="你好",
            model_id="sensevoice",
            language="zh",
            metadata={"source_path": "capture.wav"},
        )
        output = TextOutputResult(
            text="你好",
            copied_to_clipboard=True,
            pasted_to_active_window=True,
            restored_clipboard=True,
            clipboard_restore_format_count=3,
            clipboard_restore_skipped_format_count=1,
            text_path=Path("out.txt"),
            srt_path=Path("out.srt"),
        )

        entry = entry_from_result(command="listen-once", result=result, text_output=output, elapsed_s=1.23456)

        self.assertEqual(entry.command, "listen-once")
        self.assertEqual(entry.audio_path, "capture.wav")
        self.assertEqual(entry.text_length, 2)
        self.assertEqual(entry.text, "你好")
        self.assertEqual(entry.elapsed_s, 1.235)
        self.assertTrue(entry.copied_to_clipboard)
        self.assertTrue(entry.pasted_to_active_window)
        self.assertTrue(entry.restored_clipboard)
        self.assertEqual(entry.clipboard_restore_format_count, 3)
        self.assertEqual(entry.clipboard_restore_skipped_format_count, 1)
        self.assertEqual(entry.text_path, "out.txt")
        self.assertEqual(entry.srt_path, "out.srt")
