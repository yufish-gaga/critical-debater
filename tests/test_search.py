"""Unit tests for the pluggable search layer (Phase 2)."""

from __future__ import annotations

import pytest

from critical_debater.models import search as search_module
from critical_debater.models.search import (
    NullSearchProvider,
    ProviderConfigError,
    ProviderError,
    TavilySearchProvider,
    build_search_provider,
)


def test_null_search_returns_nothing():
    assert NullSearchProvider().search("anything") == []


def test_tavily_request_and_mapping(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload, timeout_sec):
        captured.update(url=url, payload=payload)
        return {
            "results": [
                {"title": "T1", "url": "https://a.example/1", "content": "snippet one",
                 "published_date": "2026-08-01"},
                {"title": "T2", "url": "https://a.example/2", "content": "snippet two"},
            ]
        }

    monkeypatch.setattr(search_module, "http_post_json", fake_post)
    provider = TavilySearchProvider(api_key="tvly-test")
    results = provider.search("debate topic", max_results=2)

    assert captured["url"] == TavilySearchProvider.ENDPOINT
    assert captured["payload"]["api_key"] == "tvly-test"
    assert captured["payload"]["query"] == "debate topic"
    assert captured["payload"]["max_results"] == 2
    assert results[0] == {"title": "T1", "url": "https://a.example/1",
                          "snippet": "snippet one", "published_date": "2026-08-01",
                          "publisher": None}
    assert results[1]["published_date"] is None


def test_tavily_requires_key():
    with pytest.raises(ProviderConfigError):
        TavilySearchProvider(api_key="")


def test_build_search_provider_config(monkeypatch):
    assert isinstance(build_search_provider(None), NullSearchProvider)
    assert isinstance(build_search_provider({"provider": "none"}), NullSearchProvider)

    provider = build_search_provider({"provider": "tavily", "api_key": "explicit"})
    assert isinstance(provider, TavilySearchProvider)

    monkeypatch.setenv("CUSTOM_SEARCH_KEY", "from-env")
    provider = build_search_provider({"provider": "tavily", "api_key_env": "CUSTOM_SEARCH_KEY"})
    assert isinstance(provider, TavilySearchProvider)

    with pytest.raises(ProviderConfigError):
        build_search_provider({"provider": "bogus"})


def test_tavily_wraps_transport_errors(monkeypatch):
    def boom(url, headers, payload, timeout_sec):
        raise ProviderError("network down")

    monkeypatch.setattr(search_module, "http_post_json", boom)
    provider = TavilySearchProvider(api_key="k")
    with pytest.raises(ProviderError):
        provider.search("q")
