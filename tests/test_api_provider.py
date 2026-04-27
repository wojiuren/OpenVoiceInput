import json
import os
import unittest
from unittest.mock import patch

import test_bootstrap  # noqa: F401

from local_voice_input.api_provider import (
    ApiProviderError,
    get_postprocess_prompt,
    call_chat_completion,
    normalize_chat_completions_endpoint,
)
from local_voice_input.config import ApiProviderConfig


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.data, ensure_ascii=False).encode("utf-8")


class ApiProviderTests(unittest.TestCase):
    def test_normalizes_base_url_variants(self):
        self.assertEqual(
            normalize_chat_completions_endpoint("https://api.example.com/v1"),
            "https://api.example.com/v1/chat/completions",
        )
        self.assertEqual(
            normalize_chat_completions_endpoint("https://api.example.com/v1/chat/completions"),
            "https://api.example.com/v1/chat/completions",
        )
        self.assertEqual(
            normalize_chat_completions_endpoint("https://api.example.com"),
            "https://api.example.com/v1/chat/completions",
        )

    def test_call_chat_completion_sends_openai_compatible_payload(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            seen["authorization"] = request.headers["Authorization"]
            seen["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse(
                {
                    "choices": [{"message": {"content": "整理后的文本"}}],
                    "usage": {"total_tokens": 12},
                }
            )

        config = ApiProviderConfig(
            provider="siliconflow",
            base_url="https://api.siliconflow.cn/v1/chat/completions",
            api_key_env="TEST_API_KEY",
            model="Qwen/Qwen3-8B",
        )

        with patch.dict(os.environ, {"TEST_API_KEY": "sk-test"}):
            result = call_chat_completion(config, "帮我整理这句话", urlopen_func=fake_urlopen)

        self.assertEqual(result.text, "整理后的文本")
        self.assertEqual(seen["url"], "https://api.siliconflow.cn/v1/chat/completions")
        self.assertEqual(seen["authorization"], "Bearer sk-test")
        self.assertEqual(seen["payload"]["model"], "Qwen/Qwen3-8B")
        self.assertEqual(seen["payload"]["messages"][1]["content"], "帮我整理这句话")
        self.assertEqual(result.usage["total_tokens"], 12)

    def test_missing_api_key_env_fails_clearly(self):
        config = ApiProviderConfig(
            provider="siliconflow",
            base_url="https://api.siliconflow.cn/v1",
            api_key_env="MISSING_API_KEY",
            model="Qwen/Qwen3-8B",
        )

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ApiProviderError):
                call_chat_completion(config, "hello")

    def test_postprocess_presets_are_available(self):
        self.assertIn("正式", get_postprocess_prompt("formal"))
        self.assertIn("待办", get_postprocess_prompt("todo"))
        self.assertIn("翻译", get_postprocess_prompt("translate"))

        with self.assertRaises(ApiProviderError):
            get_postprocess_prompt("missing")


if __name__ == "__main__":
    unittest.main()
