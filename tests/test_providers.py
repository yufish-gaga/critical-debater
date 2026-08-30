"""Unit tests for LLM providers and JSON extraction (Phase 2)."""

from __future__ import annotations

import json
import urllib.error

import pytest

from critical_debater.models.provider import (
    AnthropicProvider,
    OpenAICompatProvider,
    ProviderConfigError,
    ProviderError,
    extract_json_object,
)


class RecordingOpenAI(OpenAICompatProvider):
    def __init__(self, responses: list | None = None, **kwargs):
        super().__init__(**kwargs)
        self.requests: list[tuple[str, dict, dict, int]] = []
        self.responses = list(responses or [{"choices": [{"message": {"content": "ok"}}]}])

    def _http_post_json(self, url, headers, payload, timeout_sec):
        self.requests.append((url, headers, payload, timeout_sec))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make(**kwargs):
    defaults = dict(model="deepseek-chat", base_url="https://api.deepseek.com/v1/",
                    api_key="sk-test")
    defaults.update(kwargs)
    return RecordingOpenAI(**defaults)


def test_openai_request_shape():
    provider = make(max_tokens=512)
    text = provider.chat("be brief", "hello", timeout_sec=77)
    assert text == "ok"
    url, headers, payload, timeout = provider.requests[0]
    assert url == "https://api.deepseek.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert payload["model"] == "deepseek-chat"
    assert payload["messages"][0] == {"role": "system", "content": "be brief"}
    assert payload["max_tokens"] == 512
    assert timeout == 77


def test_openai_missing_key_raises():
    provider = make(api_key="", api_key_required=True)
    with pytest.raises(ProviderConfigError):
        provider.chat("s", "u")


def test_openai_keyless_local_runtime_allowed():
    provider = make(api_key="", api_key_required=False)
    assert provider.chat("s", "u") == "ok"


def test_openai_retries_transient_errors():
    provider = make(responses=[
        urllib.error.URLError("boom"),
        urllib.error.URLError("boom"),
        {"choices": [{"message": {"content": "recovered"}}]},
    ])
    assert provider.chat("s", "u") == "recovered"
    assert len(provider.requests) == 3


def test_openai_no_retry_on_client_error():
    provider = make(responses=[urllib.error.HTTPError("u", 401, "denied", None, None)])
    with pytest.raises(urllib.error.HTTPError):
        provider.chat("s", "u")
    assert len(provider.requests) == 1


def test_openai_bad_response_shape():
    provider = make(responses=[{"unexpected": 1}])
    with pytest.raises(ProviderError):
        provider.chat("s", "u")


class RecordingAnthropic(AnthropicProvider):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.requests: list[tuple[str, dict, dict]] = []

    def _http_post_json(self, url, headers, payload, timeout_sec):
        self.requests.append((url, headers, payload))
        return {"content": [{"type": "text", "text": "claude says "}, {"type": "text", "text": "hi"}]}


def test_anthropic_request_shape():
    provider = RecordingAnthropic(model="claude-sonnet-4-5", api_key="sk-ant")
    assert provider.chat("sys", "user") == "claude says hi"
    url, headers, payload = provider.requests[0]
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == "sk-ant"
    assert headers["anthropic-version"] == "2023-06-01"
    assert payload["system"] == "sys"
    assert payload["messages"] == [{"role": "user", "content": "user"}]
    assert payload["max_tokens"] == 8192


def test_anthropic_missing_key_raises():
    provider = RecordingAnthropic(model="claude-sonnet-4-5", api_key="")
    with pytest.raises(ProviderConfigError):
        provider.chat("s", "u")


# --- extract_json_object -----------------------------------------------------


def test_extract_plain_object():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_fenced_object():
    text = "```json\n{\"a\": 1, \"b\": [2]}\n```"
    assert extract_json_object(text) == {"a": 1, "b": [2]}


def test_extract_with_prose():
    text = 'Here you go:\n{"topic": "x", "n": 2}\nHope that helps!'
    assert extract_json_object(text) == {"topic": "x", "n": 2}


def test_extract_nested_braces():
    text = 'prefix {"a": {"b": "c}"}, "d": 1} suffix'
    assert extract_json_object(text) == {"a": {"b": "c}"}, "d": 1}


def test_extract_invalid_raises():
    with pytest.raises(ProviderError):
        extract_json_object("no json here at all")
    with pytest.raises(ProviderError):
        extract_json_object("{\"broken\": [}")


def test_extract_non_object_raises():
    with pytest.raises(ProviderError):
        extract_json_object("[1, 2, 3]")


def test_json_dumps_roundtrip_usable():
    payload = {"queries": ["a", "b"]}
    assert extract_json_object(json.dumps(payload)) == payload
