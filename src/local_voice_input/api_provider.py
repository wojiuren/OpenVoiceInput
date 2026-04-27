"""OpenAI-compatible text API provider client."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ApiProviderConfig


DEFAULT_SYSTEM_PROMPT = "你是一个简洁、可靠的中文文本处理助手。"
DICTATION_POSTPROCESS_PROMPT = (
    "请整理下面这段语音识别文本：修正常见错字，补全标点，去掉明显口头填充词。"
    "不要扩写，不要总结，不要解释，只输出整理后的正文。"
)
FORMAL_REWRITE_PROMPT = (
    "请把下面这段口语化文本改写成正式、清楚、自然的中文。"
    "保留原意，不要扩写事实，不要解释，只输出改写后的正文。"
)
TODO_EXTRACT_PROMPT = (
    "请从下面这段文本中提取待办事项。"
    "如果有待办，每条一行，用“- ”开头；如果没有明确待办，只输出“无待办”。"
)
TRANSLATE_TO_CHINESE_PROMPT = (
    "请把下面文本翻译成自然、准确的简体中文。"
    "如果原文已经是中文，请只做轻微润色。不要解释，只输出译文。"
)

POSTPROCESS_PRESETS = {
    "clean": DICTATION_POSTPROCESS_PROMPT,
    "formal": FORMAL_REWRITE_PROMPT,
    "todo": TODO_EXTRACT_PROMPT,
    "translate": TRANSLATE_TO_CHINESE_PROMPT,
}


class ApiProviderError(RuntimeError):
    """Raised when a configured API provider cannot process a request."""


@dataclass(frozen=True)
class ApiTextResult:
    text: str
    provider: str
    model: str
    endpoint: str
    usage: dict[str, Any] = field(default_factory=dict)


UrlOpen = Callable[[Request, float], Any]


def call_chat_completion(
    config: ApiProviderConfig,
    text: str,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    temperature: float = 0.2,
    max_tokens: int = 512,
    urlopen_func: UrlOpen = urlopen,
) -> ApiTextResult:
    """Send text to an OpenAI-compatible chat completions endpoint."""

    endpoint = normalize_chat_completions_endpoint(config.base_url)
    api_key = _read_api_key(config)
    if not config.model:
        raise ApiProviderError("API provider model is not configured.")

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen_func(request, timeout=config.timeout_s) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body = _read_error_body(exc)
        raise ApiProviderError(f"API provider returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise ApiProviderError(f"failed to reach API provider: {exc.reason}") from exc
    except OSError as exc:
        raise ApiProviderError(f"failed to call API provider: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiProviderError(f"API provider returned invalid JSON: {exc}") from exc

    content = _extract_message_content(data)
    usage = data.get("usage", {})
    return ApiTextResult(
        text=content,
        provider=config.provider,
        model=config.model,
        endpoint=endpoint,
        usage=usage if isinstance(usage, dict) else {},
    )


def get_postprocess_prompt(preset: str) -> str:
    try:
        return POSTPROCESS_PRESETS[preset]
    except KeyError as exc:
        available = ", ".join(sorted(POSTPROCESS_PRESETS))
        raise ApiProviderError(f"unknown API postprocess preset: {preset}. Available: {available}") from exc


def normalize_chat_completions_endpoint(base_url: str) -> str:
    value = base_url.strip().rstrip("/")
    if not value:
        raise ApiProviderError("API provider base_url is not configured.")
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return f"{value}/v1/chat/completions"


def _read_api_key(config: ApiProviderConfig) -> str:
    if not config.api_key_env:
        raise ApiProviderError("API provider api_key_env is not configured.")
    value = os.environ.get(config.api_key_env)
    if not value:
        raise ApiProviderError(f"environment variable {config.api_key_env!r} is not set.")
    return value


def _extract_message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ApiProviderError("API provider response does not contain choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ApiProviderError("API provider response choice is invalid.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ApiProviderError("API provider response choice does not contain a message.")
    content = message.get("content")
    if not isinstance(content, str):
        raise ApiProviderError("API provider response message does not contain text content.")
    return content


def _read_error_body(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""
    body = body.strip()
    if len(body) > 500:
        return f"{body[:500]}..."
    return body or exc.reason
