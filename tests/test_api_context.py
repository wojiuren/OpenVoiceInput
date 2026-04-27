import json
import tempfile
import unittest
from pathlib import Path

import test_bootstrap  # noqa: F401

from local_voice_input.api_context import (
    build_api_context_package,
    format_api_context_user_text,
    read_recent_transcription_texts,
)
from local_voice_input.config import ApiContextConfig, AppConfig, HotwordConfig


class ApiContextTests(unittest.TestCase):
    def test_reads_recent_texts_from_jsonl_and_skips_legacy_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transcriptions.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"audio_path": "old.wav", "text_length": 4}, ensure_ascii=False),
                        json.dumps({"text": "第一条语音"}, ensure_ascii=False),
                        "not json",
                        json.dumps({"text": "第二条语音"}, ensure_ascii=False),
                        json.dumps({"text": "第三条语音"}, ensure_ascii=False),
                    ]
                ),
                encoding="utf-8",
            )

            texts = read_recent_transcription_texts(path, limit=2, max_chars=100)

        self.assertEqual(texts, ("第三条语音", "第二条语音"))

    def test_build_package_uses_hotwords_as_glossary_and_text_only_recent_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transcriptions.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"audio_path": "secret.wav", "text": "上一句在说 Qwen"}, ensure_ascii=False),
                        json.dumps({"audio_path": "secret2.wav", "text": "刚才提到了 K7 麦克风"}, ensure_ascii=False),
                    ]
                ),
                encoding="utf-8",
            )
            config = AppConfig(
                api_context=ApiContextConfig(mode="lightweight", recent_turns=2, max_context_chars=1200),
                hotwords=HotwordConfig(words=("Qwen3-ASR", "K7"), enabled=True),
            )

            package = build_api_context_package(config, log_path=path)
            rendered = format_api_context_user_text("当前这句话需要整理。", package)

        self.assertTrue(package.enabled)
        self.assertEqual(package.glossary_terms, ("Qwen3-ASR", "K7"))
        self.assertEqual(package.recent_texts, ("刚才提到了 K7 麦克风", "上一句在说 Qwen"))
        self.assertIn("术语表", rendered)
        self.assertIn("最近上下文", rendered)
        self.assertIn("当前文本", rendered)
        self.assertNotIn("secret.wav", rendered)

    def test_off_mode_returns_current_text_without_wrapper(self):
        package = build_api_context_package(AppConfig())

        self.assertFalse(package.enabled)
        self.assertEqual(format_api_context_user_text("只处理当前句子。", package), "只处理当前句子。")

    def test_context_budget_prioritizes_glossary_before_recent_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transcriptions.jsonl"
            path.write_text(json.dumps({"text": "这是一段会被预算截断的较长上下文"}, ensure_ascii=False), encoding="utf-8")
            config = AppConfig(
                api_context=ApiContextConfig(mode="lightweight", recent_turns=1, max_context_chars=12),
                hotwords=HotwordConfig(words=("Qwen3-ASR", "K7"), enabled=True),
            )

            package = build_api_context_package(config, log_path=path)

        self.assertEqual(package.glossary_terms, ("Qwen3-ASR", "K7"))
        self.assertLessEqual(package.used_chars, 12)
