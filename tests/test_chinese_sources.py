"""Tests for Chinese source adaptation (v3 Phase 3)."""

from __future__ import annotations

import os

import pytest

from critical_debater.evidence.chinese import (
    ChineseQueryOptimizer,
    ChineseSourceRegistry,
    contains_cjk,
    detect_source_language,
    domain_of,
)
from critical_debater.models.search import BochaSearchProvider, ProviderConfigError
from critical_debater.workspace import read_json

from fake_provider import FakeRegistry, FakeSearch, fresh_queries, search_result_payload


@pytest.fixture(scope="module")
def registry():
    return ChineseSourceRegistry.load()


# --- CJK / domain helpers ----------------------------------------------------


def test_contains_cjk():
    assert contains_cjk("中国新能源汽车产业政策")
    assert contains_cjk("mixed 中国 english")
    assert not contains_cjk("china EV policy 2026")


def test_domain_of():
    assert domain_of("https://www.gov.cn/zhengce/2026/x.htm") == "www.gov.cn"
    assert domain_of("not a url") == ""
    assert domain_of("") == ""


# --- source registry ---------------------------------------------------------


def test_tier_classification(registry):
    assert registry.classify("https://www.gov.cn/zhengce.htm") == "tier1_authoritative"
    assert registry.classify("https://pbc.gov.cn/") == "tier1_authoritative"
    assert registry.classify("https://www.xinhuanet.com/politics/x.htm") == "tier1_authoritative"
    assert registry.classify("https://people.com.cn/") == "tier1_authoritative"
    assert registry.classify("https://www.caixin.com/2026/x.html") == "tier2_reputable"
    assert registry.classify("https://thepaper.cn/news/x") == "tier2_reputable"
    assert registry.classify("https://zhuanlan.zhihu.com/p/123") == "tier3_general"
    assert registry.classify("https://mp.weixin.qq.com/s/abc") == "tier3_general"
    assert registry.classify("https://baijiahao.baidu.com/s?id=1") == "tier3_general"
    assert registry.classify("https://weibo.com/123/abc") == "tier4_social"
    assert registry.classify("https://tieba.baidu.com/p/1") == "tier4_social"


def test_suffix_matching_is_label_safe(registry):
    # 'notgov.cn' must NOT match 'gov.cn' (label-boundary suffix check).
    assert registry.classify("https://notgov.cn/") is None
    assert registry.classify("https://example.com/") is None
    assert registry.classify("") is None


def test_authoritative_sites_loaded(registry):
    assert "gov.cn" in registry.authoritative_sites
    assert "xinhuanet.com" in registry.authoritative_sites


def test_custom_registry_config(tmp_path):
    cfg = tmp_path / "zh.yaml"
    cfg.write_text(
        "tier1_authoritative:\n  - example.gov.cn\n"
        "authoritative_sites:\n  - example.gov.cn\n",
        encoding="utf-8",
    )
    reg = ChineseSourceRegistry.load(str(cfg))
    assert reg.classify("https://a.example.gov.cn/x") == "tier1_authoritative"
    assert reg.classify("https://www.gov.cn/") is None


# --- source language detection -----------------------------------------------


def test_detect_source_language(registry):
    assert detect_source_language({"snippet": "国务院发布新的政策文件"}, registry) == "zh"
    assert detect_source_language({"snippet": "english text", "url": "https://www.gov.cn/x"}, registry) == "zh"
    assert detect_source_language({"snippet": "english text", "url": "https://a.com.cn/x"}, registry) == "zh"
    assert detect_source_language({"snippet": "english text", "url": "https://example.com/x"}, registry) == "en"


# --- query optimizer ---------------------------------------------------------


def test_optimizer_enabled_for(registry):
    optimizer = ChineseQueryOptimizer(registry)
    assert optimizer.enabled_for("中国新能源汽车产业政策分析", "bilingual")
    assert optimizer.enabled_for("any english topic", "zh")
    assert not optimizer.enabled_for("any english topic", "bilingual")
    assert not optimizer.enabled_for("any english topic", "en")


def test_site_scoped_queries_cover_authoritative_domains(registry):
    optimizer = ChineseQueryOptimizer(registry)
    requests = optimizer.site_scoped_queries("中国新能源汽车产业政策分析")
    assert len(requests) == optimizer.max_site_scoped
    domains = [req.include_domains for req in requests]
    assert ["gov.cn"] in domains
    assert all(req.include_domains for req in requests)
    assert all(req.query == "中国新能源汽车产业政策分析" for req in requests)


def test_query_plan_structure(registry):
    optimizer = ChineseQueryOptimizer(registry)
    plan = optimizer.query_plan("中国芯片产业", 5, "standard")
    assert plan["chinese_mode"] is True
    assert "简体中文" in plan["llm_query_guidance"]
    assert plan["site_scoped"]


# --- Bocha search provider ---------------------------------------------------


class TestBocha:
    def test_request_shape_and_mapping(self, monkeypatch):
        captured = {}

        def fake_post(url, headers, payload, timeout_sec):
            captured.update(url=url, headers=headers, payload=payload)
            return {
                "data": {
                    "webPages": {
                        "value": [
                            {"name": "国务院政策", "url": "https://www.gov.cn/x",
                             "snippet": "官方发布", "datePublished": "2026-08-01",
                             "siteName": "中国政府网"},
                        ]
                    }
                }
            }

        import critical_debater.models.search as search_module

        monkeypatch.setattr(search_module, "http_post_json", fake_post)
        provider = BochaSearchProvider(api_key="bocha-key")
        results = provider.search("新能源汽车政策", max_results=3)

        assert captured["url"] == BochaSearchProvider.ENDPOINT
        assert captured["headers"]["Authorization"] == "Bearer bocha-key"
        assert captured["payload"]["query"] == "新能源汽车政策"
        assert captured["payload"]["count"] == 3
        assert results == [{
            "title": "国务院政策",
            "url": "https://www.gov.cn/x",
            "snippet": "官方发布",
            "published_date": "2026-08-01",
            "publisher": "中国政府网",
        }]

    def test_include_domains_become_site_operators(self, monkeypatch):
        captured = {}

        def fake_post(url, headers, payload, timeout_sec):
            captured["payload"] = payload
            return {"data": {"webPages": {"value": []}}}

        import critical_debater.models.search as search_module

        monkeypatch.setattr(search_module, "http_post_json", fake_post)
        provider = BochaSearchProvider(api_key="k")
        provider.search("政策", include_domains=["gov.cn", "people.com.cn"])
        assert "site:gov.cn OR site:people.com.cn" in captured["payload"]["query"]

    def test_requires_key(self):
        with pytest.raises(ProviderConfigError):
            BochaSearchProvider(api_key="")


def test_build_search_provider_bocha(monkeypatch):
    from critical_debater.models.search import build_search_provider

    provider = build_search_provider({"provider": "bocha", "api_key": "k"})
    assert isinstance(provider, BochaSearchProvider)


# --- ingest pipeline in Chinese mode -----------------------------------------


def test_chinese_ingest_adds_language_and_overrides_tier(workspace):
    search = FakeSearch()
    # LLM structuring "mislabels" gov.cn as tier3 — registry must override.
    zh_evidence = {
        "evidence": [
            {"url": "https://www.gov.cn/zhengce/2026/x.htm",
             "publisher": "中国政府网",
             "snippet": "国务院发布关于新能源汽车产业的政策文件，明确补贴退坡时间表。",
             "source_type": "government",
             "credibility_tier": "tier3_general",   # wrong on purpose
             "freshness_status": "current",
             "evidence_track": "fact"},
            {"url": "https://zhuanlan.zhihu.com/p/999",
             "publisher": "知乎用户",
             "snippet": "知乎专栏对芯片产业的分析文章。",
             "source_type": "web",
             "credibility_tier": "tier3_general",
             "freshness_status": "current",
             "evidence_track": "fact"},
            {"url": "https://example.com/english-report",
             "publisher": "Example News",
             "snippet": "An English cross-check report on the same topic.",
             "source_type": "web",
             "credibility_tier": "tier2_reputable",
             "freshness_status": "current",
             "evidence_track": "fact"},
        ]
    }
    scripts = {"ingest": [fresh_queries(), zh_evidence]}
    from critical_debater.models.api_runner import LLMAgentRunner

    runner = LLMAgentRunner(FakeRegistry(scripts), search)
    result = runner.run(
        "source_ingest_round_0",
        f"Execute source-ingest.md. Workspace: {workspace}",
        context={"workspace": workspace, "topic": "中国新能源汽车产业政策分析",
                 "mode": "broad", "round": 0, "num_queries": 2, "language": "bilingual"},
    )
    assert result.success, result.reason

    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    by_url = {e["url"]: e for e in store}
    assert len(store) == 3

    gov = by_url["https://www.gov.cn/zhengce/2026/x.htm"]
    assert gov["credibility_tier"] == "tier1_authoritative"  # deterministic override
    assert gov["source_language"] == "zh"

    zhihu = by_url["https://zhuanlan.zhihu.com/p/999"]
    assert zhihu["credibility_tier"] == "tier3_general"
    assert zhihu["source_language"] == "zh"

    english = by_url["https://example.com/english-report"]
    assert english["source_language"] == "en"

    # Chinese mode executed site-scoped searches against authoritative domains.
    scoped = [domains for _, domains in search.scoped_queries if domains]
    assert ["gov.cn"] in scoped
    assert ["xinhuanet.com"] in scoped or ["people.com.cn"] in scoped


def test_english_ingest_has_no_site_scoping(workspace):
    search = FakeSearch()
    scripts = {"ingest": [fresh_queries(), search_result_payload(0, 2)]}
    from critical_debater.models.api_runner import LLMAgentRunner

    runner = LLMAgentRunner(FakeRegistry(scripts), search)
    result = runner.run(
        "source_ingest_round_0",
        f"Execute source-ingest.md. Workspace: {workspace}",
        context={"workspace": workspace, "topic": "chip export controls",
                 "mode": "broad", "round": 0, "num_queries": 2, "language": "en"},
    )
    assert result.success
    store = read_json(os.path.join(workspace, "evidence", "evidence_store.json"))
    assert all(e["source_language"] == "en" for e in store)
    # All searches unscoped: queries come from the LLM only.
    assert all("site:" not in q for q in search.queries)
