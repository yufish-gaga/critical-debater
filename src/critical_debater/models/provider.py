"""LLM provider abstraction (v3 Phase 2).

Two concrete provider classes cover essentially every backend:

- :class:`OpenAICompatProvider` — any endpoint speaking the OpenAI Chat
  Completions protocol: DeepSeek, Moonshot Kimi, Zhipu GLM, Alibaba Qwen
  (DashScope), OpenAI itself, and local runtimes (Ollama, vLLM, llama.cpp).
  Only ``base_url``, ``api_key`` and the model names differ.
- :class:`AnthropicProvider` — the Claude Messages API.

API keys are resolved from (in order) the constructor argument, the
environment variable named in config (``api_key_env``), and never stored in
config files. Transport is stdlib ``urllib`` — no extra dependency — and is
isolated in ``_http_post_json`` so tests can stub it.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Optional


class ProviderError(RuntimeError):
    """Provider-level failure (config, HTTP, or unparseable response)."""


class ProviderConfigError(ProviderError):
    """Missing api key or malformed provider configuration."""


class BaseLLMProvider(ABC):
    """Minimal chat contract used by the API-backed agent runner."""

    name: str = "base"

    def __init__(self, model: str, api_key: str = "", timeout_sec: int = 300,
                 max_tokens: Optional[int] = None, temperature: float = 0.2):
        self.model = model
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.max_tokens = max_tokens
        self.temperature = temperature

    @abstractmethod
    def chat(self, system: str, user: str, timeout_sec: Optional[int] = None) -> str:
        """One completion; returns raw assistant text."""

    @abstractmethod
    def _http_post_json(self, url: str, headers: dict, payload: dict,
                        timeout_sec: int) -> dict:
        """Transport seam for tests."""

    # -- shared plumbing ---------------------------------------------------

    def _require_key(self) -> None:
        if not self.api_key:
            raise ProviderConfigError(
                f"provider '{self.name}' has no API key; set it in the constructor "
                f"or export the configured api_key_env variable"
            )

    def _post_with_retry(self, url: str, headers: dict, payload: dict,
                         retries: int = 2, timeout_sec: Optional[int] = None) -> dict:
        effective_timeout = timeout_sec or self.timeout_sec
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return self._http_post_json(url, headers, payload, effective_timeout)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as e:
                status = getattr(e, "code", None)
                # Client errors (4xx, except 429) are not retryable.
                if isinstance(e, urllib.error.HTTPError) and status and 400 <= status < 500 and status != 429:
                    raise
                last_error = e
                if attempt < retries:
                    time.sleep(2 ** attempt)
        raise ProviderError(f"{self.name} request failed after {retries + 1} attempts: {last_error}")


class OpenAICompatProvider(BaseLLMProvider):
    """DeepSeek / Kimi / GLM / Qwen / OpenAI / Ollama / vLLM — one class.

    ``base_url`` should include the version prefix, e.g.
    ``https://api.deepseek.com/v1`` or ``http://localhost:11434/v1``.
    """

    name = "openai_compatible"

    def __init__(self, model: str, base_url: str, api_key: str = "",
                 timeout_sec: int = 300, max_tokens: Optional[int] = None,
                 temperature: float = 0.2, api_key_required: bool = True):
        super().__init__(model, api_key, timeout_sec, max_tokens, temperature)
        self.base_url = base_url.rstrip("/")
        self.api_key_required = api_key_required

    def chat(self, system: str, user: str, timeout_sec: Optional[int] = None) -> str:
        if self.api_key_required:
            self._require_key()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.temperature,
        }
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        data = self._post_with_retry(
            f"{self.base_url}/chat/completions",
            self._headers(),
            payload,
            timeout_sec=timeout_sec,
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"{self.name}: unexpected response shape: {data!r:.400}") from e
        if not isinstance(content, str):
            raise ProviderError(f"{self.name}: non-text content in response")
        return content

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _http_post_json(self, url: str, headers: dict, payload: dict,
                        timeout_sec: int) -> dict:
        return http_post_json(url, headers, payload, timeout_sec)


class AnthropicProvider(BaseLLMProvider):
    """Claude Messages API (https://api.anthropic.com/v1/messages)."""

    name = "anthropic"
    DEFAULT_BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def __init__(self, model: str, api_key: str = "", base_url: str = "",
                 timeout_sec: int = 300, max_tokens: Optional[int] = None,
                 temperature: float = 0.2):
        super().__init__(model, api_key, timeout_sec, max_tokens, temperature)
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def chat(self, system: str, user: str, timeout_sec: Optional[int] = None) -> str:
        self._require_key()
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens or 8192,
            "temperature": self.temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        data = self._post_with_retry(
            f"{self.base_url}/v1/messages",
            self._headers(),
            payload,
            timeout_sec=timeout_sec,
        )
        try:
            blocks = data["content"]
            text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        except (KeyError, TypeError) as e:
            raise ProviderError(f"{self.name}: unexpected response shape") from e
        if not text:
            raise ProviderError(f"{self.name}: empty response content")
        return text

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
        }

    def _http_post_json(self, url: str, headers: dict, payload: dict,
                        timeout_sec: int) -> dict:
        return http_post_json(url, headers, payload, timeout_sec)


def http_post_json(url: str, headers: dict, payload: dict, timeout_sec: int) -> dict:
    """Stdlib JSON POST used by all providers (test stubbing seam)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:400]
        except OSError:
            pass
        raise urllib.error.HTTPError(url, e.code, f"{e.reason}: {detail}", e.headers, e.fp) from e


# --- structured output helpers --------------------------------------------


def extract_json_object(text: str) -> dict:
    """Robustly pull the first JSON object out of an LLM response.

    Handles markdown fences, leading prose, and trailing commentary.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    start = cleaned.find("{")
    if start == -1:
        raise ProviderError("no JSON object found in model response")
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(cleaned[start:])
    except json.JSONDecodeError as e:
        # Fall back to first '{' .. last '}' slice (handles trailing prose
        # after the object).
        end = cleaned.rfind("}")
        if end <= start:
            raise ProviderError(f"unparseable JSON in model response: {e}") from e
        try:
            obj = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e2:
            raise ProviderError(f"unparseable JSON in model response: {e2}") from e
    if not isinstance(obj, dict):
        raise ProviderError("model response JSON is not an object")
    return obj
