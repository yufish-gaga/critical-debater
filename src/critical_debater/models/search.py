"""Pluggable web-search backends (v3 Phase 2/3).

API-backed model providers have no built-in web access, so the
source-ingest capability needs an external search backend. The
:class:`SearchProvider` protocol keeps that pluggable:

- :class:`TavilySearchProvider` — Tavily API (``TAVILY_API_KEY``), handles
  Chinese queries as well
- :class:`BochaSearchProvider` — 博查 web-search API (``BOCHA_API_KEY``),
  a China-based search index with strong Chinese web coverage
- :class:`NullSearchProvider` — returns nothing; ingest then honestly
  yields zero evidence (the evidence gate will fail rather than let the
  model fabricate sources)

``include_domains`` restricts a search to given sites (Tavily natively;
Bocha via ``site:`` operators) — used by the Chinese query optimizer to
guarantee coverage of 权威信源 (gov.cn / 新华社 / 人民网).
"""

from __future__ import annotations

import os
from typing import Any, Optional, Protocol
from urllib.error import HTTPError, URLError

from .provider import ProviderConfigError, ProviderError, http_post_json


class SearchProvider(Protocol):
    """Search backends used by the source-ingest capability."""

    name: str

    def search(self, query: str, max_results: int = 5,
               include_domains: Optional[list[str]] = None) -> list[dict[str, Any]]:
        """Return results: [{title, url, snippet, published_date?, publisher?}]."""
        ...


class NullSearchProvider:
    """No search backend configured."""

    name = "none"

    def search(self, query: str, max_results: int = 5,
               include_domains: Optional[list[str]] = None) -> list[dict[str, Any]]:
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

    def search(self, query: str, max_results: int = 5,
               include_domains: Optional[list[str]] = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": self.search_depth,
            "include_answer": False,
        }
        if include_domains:
            payload["include_domains"] = list(include_domains)
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
                "publisher": item.get("source") or None,
            })
        return results


class BochaSearchProvider:
    """博查 web-search API (https://api.bochaai.com/v1/web-search).

    China-hosted search index with strong Chinese web coverage (gov sites,
    media, 微信公众号 articles surface in general web results). Site
    restrictions are expressed as ``site:`` operators inside the query.
    """

    name = "bocha"
    ENDPOINT = "https://api.bochaai.com/v1/web-search"

    def __init__(self, api_key: Optional[str] = None, timeout_sec: int = 60,
                 summary: bool = False):
        self.api_key = api_key if api_key is not None else os.environ.get("BOCHA_API_KEY", "")
        self.timeout_sec = timeout_sec
        self.summary = summary
        if not self.api_key:
            raise ProviderConfigError(
                "Bocha search requires an API key: pass api_key or export BOCHA_API_KEY"
            )

    def search(self, query: str, max_results: int = 5,
               include_domains: Optional[list[str]] = None) -> list[dict[str, Any]]:
        effective_query = query
        if include_domains:
            operators = " OR ".join(f"site:{d}" for d in include_domains)
            effective_query = f"{query} ({operators})"
        payload = {
            "query": effective_query,
            "count": max_results,
            "summary": self.summary,
        }
        try:
            data = http_post_json(self.ENDPOINT, self._headers(), payload, self.timeout_sec)
        except HTTPError as e:
            raise ProviderError(f"bocha search failed (HTTP {e.code}): {query!r}") from e
        except (URLError, TimeoutError, OSError) as e:
            raise ProviderError(f"bocha search failed: {query!r}: {e}") from e

        pages = ((data.get("data") or {}).get("webPages") or {}).get("value") or []
        results = []
        for item in pages:
            results.append({
                "title": item.get("name") or "",
                "url": item.get("url") or "",
                "snippet": item.get("summary") or item.get("snippet") or "",
                "published_date": item.get("datePublished") or None,
                "publisher": item.get("siteName") or None,
            })
        return results

    def _headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }


def build_search_provider(config: dict | None) -> SearchProvider:
    """Build the search backend from the ``search:`` section of models.yaml.

    Supports ``provider: tavily | bocha | none`` (with optional ``api_key`` /
    ``api_key_env``). Missing section → none.
    """
    config = config or {}
    name = (config.get("provider") or "none").lower()
    if name in ("none", "null", ""):
        return NullSearchProvider()

    def resolve_key(default_env: str) -> Optional[str]:
        api_key = config.get("api_key")
        if not api_key:
            env_name = config.get("api_key_env") or default_env
            api_key = os.environ.get(env_name, "")
        return api_key or None

    if name == "tavily":
        return TavilySearchProvider(api_key=resolve_key("TAVILY_API_KEY"),
                                    search_depth=config.get("search_depth", "basic"))
    if name == "bocha":
        return BochaSearchProvider(api_key=resolve_key("BOCHA_API_KEY"),
                                   summary=bool(config.get("summary", False)))
    raise ProviderConfigError(f"unknown search provider: {name}")
