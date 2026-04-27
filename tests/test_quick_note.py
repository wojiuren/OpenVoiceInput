from datetime import datetime
import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.config import QuickCaptureConfig, QuickCaptureRule
from local_voice_input.quick_note import find_quick_note_match, save_quick_note


class QuickNoteTests(unittest.TestCase):
    def test_keyword_near_start_routes_to_rule_folder(self):
        config = QuickCaptureConfig(
            root_dir="notes",
            rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
        )

        match = find_quick_note_match("灵感 今天想到一个点子", config)

        self.assertTrue(match.matched)
        self.assertEqual(match.keyword, "灵感")
        self.assertEqual(match.target_dir, Path("notes") / "ideas")

    def test_keyword_too_far_from_start_does_not_route(self):
        config = QuickCaptureConfig(
            root_dir="notes",
            match_window_chars=4,
            rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
        )

        match = find_quick_note_match("这是一段很长的普通输入，最后才说灵感", config)

        self.assertFalse(match.matched)
        self.assertEqual(match.target_dir, Path("notes") / "inbox")

    def test_save_quick_note_can_remove_keyword_prefix(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = QuickCaptureConfig(
                root_dir=str(Path(temp_dir) / "notes"),
                rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
            )

            result = save_quick_note(
                "嗯，灵感：做一个关键词记录功能",
                config,
                now=datetime(2026, 4, 23, 20, 0, 0),
            )

            self.assertEqual(result.saved_text, "做一个关键词记录功能")
            self.assertEqual(result.matched_keyword, "灵感")
            self.assertTrue(result.removed_keyword)
            self.assertEqual(result.path.read_text(encoding="utf-8"), "做一个关键词记录功能")

    def test_rule_can_keep_keyword_in_saved_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = QuickCaptureConfig(
                root_dir=str(Path(temp_dir) / "notes"),
                rules=(
                    QuickCaptureRule(
                        name="materials",
                        keywords=("素材",),
                        target_dir="materials",
                        remove_keyword=False,
                    ),
                ),
            )

            result = save_quick_note(
                "素材 今天看到一段好句子",
                config,
                now=datetime(2026, 4, 23, 20, 0, 0),
            )

            self.assertEqual(result.saved_text, "素材 今天看到一段好句子")
            self.assertFalse(result.removed_keyword)

    def test_unmatched_text_goes_to_inbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = QuickCaptureConfig(root_dir=str(Path(temp_dir) / "notes"))

            result = save_quick_note("普通记录", config, now=datetime(2026, 4, 23, 20, 0, 0))

            self.assertEqual(result.path.parent, Path(temp_dir) / "notes" / "inbox")
            self.assertIsNone(result.matched_keyword)

    def test_route_text_can_differ_from_saved_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = QuickCaptureConfig(
                root_dir=str(Path(temp_dir) / "notes"),
                rules=(QuickCaptureRule(name="ideas", keywords=("灵感",), target_dir="ideas"),),
            )

            result = save_quick_note(
                "整理后的正文",
                config,
                route_text="灵感 原始识别文本",
                now=datetime(2026, 4, 23, 20, 0, 0),
            )

            self.assertEqual(result.path.parent, Path(temp_dir) / "notes" / "ideas")
            self.assertEqual(result.saved_text, "整理后的正文")
            self.assertEqual(result.original_text, "灵感 原始识别文本")


if __name__ == "__main__":
    unittest.main()
