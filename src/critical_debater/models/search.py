"""Pluggable web-search backends (v3 Phase 2).

API-backed model providers have no built-in web access, so the
source-ingest capability needs an external search backend. The
:class:`SearchProvider` protocol keeps that pluggable:

- :class:`TavilySearchProvider` — Tavily API (``TAVILY_API_KEY``)
- :class:`NullSearchProvider` — returns nothing; ingest then honestly
  yields zero evidence (the evidence gate will fail rather than let the
  model fabricate sources)

Phase 3 (中文信源) can add Baidu/Bocha backends behind the same protocol.
"""

from __future__ import annotations

import os
from typing import Any, Optional, Protocol
from urllib.error import HTTPError, URLError

from .provider import ProviderConfigError, ProviderError, http_post_json


class SearchProvider(Protocol):
    """Search backends used by the source-ingest capability."""

    name: str

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        """Return results: [{title, url, snippet, published_date?}]."""
        ...


class NullSearchProvider:
    """No search backend configured."""

    name = "none"

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        return []


class TavilySearchProvider:
    """Tavily search API (https://api.tavily.com)."""

    name = "tavily"
    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str] = None, timeout_sec: int = 60,
                 search_depth: str = "basic"):
        self.api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")
        self.timeout_sec = timeout_sec
        self.search_depth = search_depth
        if not self.api_key:
            raise ProviderConfigError(
                "Tavily search requires an API key: pass api_key or export TAVILY_API_KEY"
            )

    def search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": self.search_depth,
            "include_answer": False,
        }
        try:
            data = http_post_json(self.ENDPOINT, {"Content-Type": "application/json"},
                                  payload, self.timeout_sec)
        except HTTPError as e:
            raise ProviderError(f"tavily search failed (HTTP {e.code}): {query!r}") from e
        except (URLError, TimeoutError, OSError) as e:
            raise ProviderError(f"tavily search failed: {query!r}: {e}") from e

        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "published_date": item.get("published_date") or None,
            })
        return results


def build_search_provider(config: dict | None) -> SearchProvider:
    """Build the search backend from the ``search:`` section of models.yaml.

    Supports ``provider: tavily`` (with optional ``api_key`` / ``api_key_env``)
    and ``provider: none``. Missing section → none.
    """
    config = config or {}
    name = (config.get("provider") or "none").lower()
    if name in ("none", "null", ""):
        return NullSearchProvider()
    if name == "tavily":
        api_key = config.get("api_key")
        if not api_key:
            env_name = config.get("api_key_env") or "TAVILY_API_KEY"
            api_key = os.environ.get(env_name, "")
        return TavilySearchProvider(api_key=api_key or None,
                                    search_depth=config.get("search_depth", "basic"))
    raise ProviderConfigError(f"unknown search provider: {name}")
