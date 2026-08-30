"""Chinese source adaptation (v3 Phase 3).

Three cooperating pieces per the refactoring plan's Phase 3:

- :class:`ChineseSourceRegistry` — deterministic domain → credibility-tier
  mapping for known Chinese sources (中国政府网/新华社/人民网 → tier1,
  专业媒体 → tier2, 知乎/微信公众号 → tier3, 微博/贴吧 → tier4), loaded from
  ``config/chinese_sources.yaml``.
- :class:`ChineseQueryOptimizer` — site-scoped supplement queries so
  authoritative Chinese domains are always covered, on top of the
  LLM-generated semantic queries (semantic-first: the optimizer guarantees
  source coverage, the LLM owns query wording).
- Language detection helpers for routing the ingest pipeline into Chinese
  mode and labelling each evidence item with ``source_language``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

ENV_CHINESE_SOURCES_CONFIG = "CRITICAL_CHINESE_SOURCES_CONFIG"
DEFAULT_CONFIG_REL_PATH = os.path.join("config", "chinese_sources.yaml")

_CJK_RANGES = (
    "\u4e00-\u9fff"    # CJK 统一表意文字
    "\u3400-\u4dbf"    # 扩展 A
    "\uf900-\ufaff"    # 兼容表意文字
)
_CJK_RE = re.compile(f"[{_CJK_RANGES}]")

# Levels the registry understands (mirrors the data contract's tiers).
KNOWN_TIERS = (
    "tier1_authoritative",
    "tier2_reputable",
    "tier3_general",
    "tier4_social",
)


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def domain_of(url: str) -> str:
    """Registrable hostname of a URL, lower-cased; '' when unparseable."""
    try:
        host = urlparse(url or "").hostname or ""
    except ValueError:
        return ""
    return host.strip().lower()


def _domain_matches(host: str, target: str) -> bool:
    """True when host equals target or is a subdomain of it.

    Suffix-safe: 'notgov.cn' does NOT match 'gov.cn' (label-boundary aware).
    """
    host = host.strip().lower()
    target = target.strip().lower()
    return host == target or host.endswith("." + target)


class ChineseSourceRegistry:
    """Domain → credibility tier mapping for Chinese sources."""

    def __init__(self, tier_domains: dict[str, list[str]],
                 authoritative_sites: Optional[list[str]] = None):
        self.tier_domains = {tier: list(domains) for tier, domains in tier_domains.items()}
        self.authoritative_sites = list(authoritative_sites or [])

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "ChineseSourceRegistry":
        path = config_path or os.environ.get(ENV_CHINESE_SOURCES_CONFIG) or DEFAULT_CONFIG_REL_PATH
        tier_domains: dict[str, list[str]] = {}
        authoritative: list[str] = []
        if os.path.exists(path):
            try:
                import yaml

                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                for tier in KNOWN_TIERS:
                    entries = data.get(tier) or []
                    if isinstance(entries, list):
                        tier_domains[tier] = [str(d).strip().lower() for d in entries if d]
                sites = data.get("authoritative_sites") or []
                if isinstance(sites, list):
                    authoritative = [str(s).strip().lower() for s in sites if s]
            except (OSError, yaml.YAMLError):
                pass
        return cls(tier_domains, authoritative)

    def classify(self, url: str) -> Optional[str]:
        """Credibility tier for a URL's domain, or None when unknown."""
        host = domain_of(url)
        if not host:
            return None
        for tier in KNOWN_TIERS:
            for target in self.tier_domains.get(tier, []):
                if _domain_matches(host, target):
                    return tier
        return None

    def is_known_chinese_source(self, url: str) -> bool:
        return self.classify(url) is not None


def detect_source_language(item: dict, registry: Optional[ChineseSourceRegistry] = None) -> str:
    """Best-effort language label for an evidence item: zh | en."""
    snippet = str(item.get("snippet") or "")
    publisher = str(item.get("publisher") or "")
    host = domain_of(item.get("url") or "")

    if contains_cjk(snippet) or contains_cjk(publisher):
        return "zh"
    if host.endswith(".cn") or host.endswith(".com.cn") or host.endswith(".中国"):
        return "zh"
    if registry is not None and registry.is_known_chinese_source(item.get("url") or ""):
        return "zh"
    return "en"


@dataclass
class QueryRequest:
    """One search execution: query text plus optional site restriction."""

    query: str
    include_domains: Optional[list[str]] = None
    purpose: str = "general"


class ChineseQueryOptimizer:
    """Site-scoped supplement queries for authoritative Chinese sources.

    The LLM keeps ownership of semantic query wording (语义优先); this
    optimizer deterministically guarantees coverage of 权威信源 so a Chinese
    debate never leans only on English sources or self-media.
    """

    def __init__(self, registry: ChineseSourceRegistry, max_site_scoped: int = 2):
        self.registry = registry
        self.max_site_scoped = max_site_scoped

    def enabled_for(self, topic: str, language: str) -> bool:
        """Chinese mode when the topic is Chinese, or language asks for zh."""
        lang = (language or "").strip().lower()
        if lang == "zh":
            return True
        if contains_cjk(topic):
            return True
        return False  # bilingual/en with an English topic stays on English sources

    def site_scoped_queries(self, topic: str) -> list[QueryRequest]:
        """Authoritative-domain searches appended to the LLM's own queries."""
        sites = self.registry.authoritative_sites[: self.max_site_scoped]
        requests = []
        for site in sites:
            requests.append(QueryRequest(
                query=topic,
                include_domains=[site],
                purpose=f"authoritative:{site}",
            ))
        return requests

    def query_plan(self, topic: str, num_queries: int, depth: str) -> dict:
        """Everything the ingest step needs to run a Chinese-aware search."""
        authoritative = self.registry.authoritative_sites
        return {
            "chinese_mode": True,
            "llm_query_guidance": (
                f"The topic is Chinese-language: write {num_queries} search queries in "
                f"Chinese (简体中文), each from a distinct angle (政策/数据/行业/争议点). "
                f"Add one final query in English for cross-language verification of the "
                f"core entities. Prefer authoritative sources: {', '.join(authoritative[:5])}."
            ),
            "site_scoped": [q.__dict__ for q in self.site_scoped_queries(topic)],
        }
