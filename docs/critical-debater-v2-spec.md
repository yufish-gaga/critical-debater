# Critical Debater v2.0 — Complete System Specification
# Critical Debater v2.0 — 完整系统规范

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-03-12 | Claude | 初始创建：v2.0 完整规范文档，含 per-round evidence、并行 Pro/Con、显式报告格式、generic skill 结构 / Initial creation: v2.0 full spec with per-round evidence, parallel Pro/Con, explicit report format, generic skill structure |

---

**Purpose / 目的**: This is a self-contained rebuild specification. A new Claude Code session reads ONLY this file to build the entire Critical Debater system from scratch.
这是一份自包含的重建规范。新 Claude Code 会话只需读这一个文件即可从零构建整个 Critical Debater 系统。

**Version / 版本**: v2.0.0

---

# Section 1: Project Overview & Philosophy
# 第一章：项目概述与设计哲学

## What This Is / 这是什么

Multi-agent adversarial debate system: 4 agents, 1 suite skill, file-based state management. Produces structured bilingual Markdown reports with traceable conclusions.
多 agent 对抗式辩论系统：4 个 agent、1 个套件 skill、基于文件的状态管理。产出结构化双语 Markdown 报告，结论可追溯。

## Decision Order / 决策序

For every task, follow this priority:
每个任务按此优先级：

1. **LLM first / LLM 优先** — Reading, judging, summarizing, classifying, extracting, argument construction, causal audit → all LLM. Do NOT write regex, thresholds, or rule trees.
2. **Existing skill second / 现有 skill 其次** — Reuse the suite skill's 9 capabilities. Compose, don't reinvent.
3. **Deterministic code last / 确定性代码最后** — Only for: file I/O, binary tool calls, timestamp math, hash computation, directory ops. Lives in `scripts/`.

## Success Criteria / 成功标准

- **Traceable conclusions / 可追溯结论**: Every conclusion traces back to evidence_ids → source URLs
- **Real-time capability / 实时能力**: Can fetch information from the last 24 hours
- **Cross-source verification / 交叉验证**: Critical claims require 2+ independent sources
- **Independent Judge / 独立 Judge**: Judge re-verifies claims independently, never trusts debater citations
- **Per-round evidence refresh / 每轮证据刷新**: Each round can search for new evidence driven by judge feedback

## Non-Goals / 不包含

- No frontend / 无前端
- No distributed orchestration / 无分布式编排
- No auto-execution of conclusions / 不自动执行结论

---

# Section 2: Agent Roles & Definitions
# 第二章：Agent 角色与定义

## Architecture Pattern / 架构模式

**SubAgent + File State Machine** — Orchestrator is the hub; all communication between agents happens through JSON files in the workspace. This is NOT Agent Teams (no parallel worktrees, no direct peer communication).
Orchestrator 是中心；agent 之间通过 workspace 中的 JSON 文件通信。

## Agent Definitions / Agent 定义

### 2.1 Debate Orchestrator / 辩论编排器

| Field | Value |
|---|---|
| Role / 角色 | Workflow controller, state manager, quality gatekeeper / 工作流控制器、状态管理器、质量守门人 |
| Model tier | `balanced` |
| Tools | search, fetch, read, write, bash, spawn_role, glob, grep, todo |
| Writes | All files / 所有文件 |
| Reads | All files / 所有文件 |

Does NOT argue or verify. Delegates argument construction to Pro/Con and verification to Judge.
不参与论证或验证。

### 2.2 Pro-Debater / 正方辩手

| Field | Value |
|---|---|
| Role / 角色 | Skilled advocate who ALWAYS supports the motion / 始终支持议题的辩手 |
| Model tier | `balanced` |
| Tools | search, fetch, read, write, bash |
| Writes | `rounds/round_N/pro_turn.json` |
| Reads | evidence_store, claim_ledger, previous round's judge_ruling + con_turn |

Core responsibilities / 核心职责:
1. Address ALL mandatory response points from Judge FIRST (non-negotiable) / 首先处理所有 Judge 必答点
2. Build arguments with complete 5-element reasoning chains / 构建完整 5 要素推理链
3. Every factual claim MUST reference evidence_ids / 每个事实性声明必须引用证据
4. Rebut opponent's strongest arguments — target causal chain weaknesses / 反驳对手最强论点的因果链弱点
5. Search for additional evidence if evidence store is insufficient / 证据不足则搜索补充

### 2.3 Con-Debater / 反方辩手

| Field | Value |
|---|---|
| Role / 角色 | Skilled advocate who ALWAYS opposes the motion / 始终反对议题的辩手 |
| Model tier | `balanced` |
| Tools | search, fetch, read, write, bash |
| Writes | `rounds/round_N/con_turn.json` |
| Reads | evidence_store, claim_ledger, previous round's judge_ruling + pro_turn |

Same responsibilities as Pro but argues AGAINST the motion. Identical rules for reasoning chains, evidence, and rebuttals.
与正方职责相同但论证反对议题。推理链、证据、反驳规则完全一致。

### 2.4 Neutral Judge / 中立裁判

| Field | Value |
|---|---|
| Role / 角色 | Impartial arbiter — evaluates reasoning quality, NOT which side is "right" / 评估推理质量，不判定谁"对" |
| Model tier | `deep` |
| Tools | search, fetch, read, write, bash, grep |
| Writes | `rounds/round_N/judge_ruling.json` |
| Reads | current round's pro_turn + con_turn, evidence_store, claim_ledger |

Core workflow / 核心工作流:
1. **Independent source verification (CRITICAL)** — Re-verify EACH factual claim using search. Do NOT rely on debaters' citations alone. / 独立重新验证每个事实性声明
2. **Causal chain audit** — Flag: correlation!=causation, reverse causality, confounding variables, unstated assumptions / 审计因果链
3. **Analogy audit** — Check: >=2 similarities, >=1 difference, <15% content share / 检查类比合规
4. **Mandatory response points** — Identify 2-5 points that MUST be addressed next round / 生成下轮必答点
5. **Round summary** — Neutral, no scoring, no preference / 中立回合总结

**IMPARTIALITY RULES (NON-NEGOTIABLE) / 公正规则:**
- NEVER express preference for either side
- Evaluate REASONING QUALITY, not which conclusion you favor
- Apply IDENTICAL standards to both sides
- If one side is clearly stronger, state it neutrally with evidence

---

# Section 3: Evidence System
# 第三章：证据系统

## v2 Evidence Model: Shared Base + Private Supplements
## v2 证据模型：共享底层 + 私有补充

```
evidence_store.json ← Orchestrator 初始搜索的公共底层 (Round 0)
                    ← Per-round focused ingest (Round 1+, judge-driven)

new_evidence[] in pro_turn.json ← Pro 独立搜索的私有补充
new_evidence[] in con_turn.json ← Con 独立搜索的私有补充

Judge reads: evidence_store + BOTH sides' new_evidence (全部)
Post-round: Orchestrator merges new_evidence → evidence_store
            (tagged with discovered_by field)
```

## Two Evidence Tracks / 双轨道

| Track / 轨道 | Freshness Rule / 时效规则 | Example / 示例 |
|---|---|---|
| **Fact** | Can become `stale` when source expires / 来源过期 → stale | "BTC is at $70,000" / 当前价格 |
| **Reasoning** | NEVER auto-degraded, always `timeless` / 永不自动降级 | "Leverage unwinds cause cascading sell-offs" / 机制解释 |

## Twitter/X Policy / Twitter 政策

Signal layer ONLY. Twitter-only claims can NEVER become `verified` — requires at least one independent non-social source.
仅信号层。Twitter 独有声明永远不能成为 `verified`。

LLM pre-screens Twitter sources for fake news patterns (`social_credibility_flag`). High-risk sources get elevated `verification_priority`.

## Cross-Source Verification / 交叉验证

Critical claims require 2+ independent sources. Judge independently re-verifies — does NOT trust debaters' single-citation claims.
关键声明需 2+ 独立来源。Judge 独立重新验证。

## Real-Time Capability / 实时能力

The system MUST be able to fetch information from the last 24 hours. This is a capability requirement, not an evidence age restriction.
系统必须能获取最近 24h 内的信息。

---

# Section 4: Reasoning Model
# 第四章：推理模型

## 5-Element Mandatory Reasoning Chain / 5 要素强制推理链

Every argument MUST contain all 5 elements. Use semantic understanding, not mechanical templates.
每个论点必须包含全部 5 个要素。用语义理解构建，不要机械填模板。

```
Observed facts → Mechanism → Scenario implication → Trigger conditions → Falsification conditions
观察事实    →    机制    →    场景推演        →    触发条件        →    证伪条件
```

1. **Observed facts / 观察事实**: Concrete data, events, or statistics
2. **Mechanism / 机制**: Causal explanation (WHY A leads to B)
3. **Scenario implication / 场景推演**: What follows IF the mechanism holds
4. **Trigger conditions / 触发条件**: What would ACTIVATE this scenario
5. **Falsification conditions / 证伪条件**: What would DISPROVE this argument

**Attack causal chains, not just stances.** Update assumption states each round.
攻击因果链，不仅攻击立场。每轮更新假设状态。

## Historical Analogies / 历史类比

- Explanation layer ONLY, not proof / 仅解释层，不作为证据
- Must include >=2 similarities AND >=1 structural difference / 需相似+差异
- Keep under ~15% of total content / 占比 <15%
- Historical wisdom section uses `weight: "advisory"` — not subject to verified/contested status
- Judge evaluates quality of historical reasoning, not whether it supports pro/con

---

# Section 5: Data Contracts — JSON Schemas
# 第五章：数据契约 — JSON Schema

All agents and skills reference these schemas as the single source of truth.
所有 agent 和 skill 引用这些 schema 作为唯一真相来源。

---

## 5.1 EvidenceItem

An individual piece of evidence from a source. / 来自来源的单条证据。

```json
{
  "evidence_id": "evi_<hash_first8>",
  "source_type": "web | twitter | academic | government | other",
  "url": "https://...",
  "publisher": "Publisher Name",
  "published_at": "2026-03-09T12:00:00Z",
  "retrieved_at": "2026-03-09T12:30:00Z",
  "snippet": "Relevant excerpt from source...",
  "hash": "<SHA-256 of snippet>",
  "credibility_tier": "tier1_authoritative | tier2_reputable | tier3_general | tier4_social",
  "freshness_status": "current | stale | timeless",
  "evidence_track": "fact | reasoning",
  "social_credibility_flag": "likely_reliable | needs_verification | likely_unreliable | null",
  "verification_priority": "high | medium | low",
  "corroboration_status": "corroborated | uncorroborated | contradicted | null",
  "discovered_by": "orchestrator | pro | con",
  "discovered_at_round": 0,
  "search_context": "initial_broad | judge_feedback_round_N | pro_supplement | con_supplement"
}
```

**[v2 NEW] Fields:**
- `discovered_by`: Who found this evidence — `"orchestrator"` (initial/per-round ingest), `"pro"`, or `"con"` (private supplement)
- `discovered_at_round`: 0 = initial ingest, N = found during round N
- `search_context`: What drove this search — tracks the debate's epistemic evolution

### Credibility Tiers / 可信度分级
- `tier1_authoritative`: Government agencies, central banks, major wire services (AP, Reuters) / 政府、央行、主要通讯社
- `tier2_reputable`: Major newspapers, established research institutions, peer-reviewed journals / 主要报纸、知名研究机构
- `tier3_general`: Blogs, smaller publications, industry reports, company press releases / 博客、小型出版物
- `tier4_social`: Twitter/X, Reddit, forums, personal posts / Twitter、Reddit、论坛

### Freshness Status / 时效状态
- `current`: Source is recent enough to support current-state claims
- `stale`: Source was used for a current-state claim but is now outdated
- `timeless`: Historical/mechanism/trend evidence; NEVER auto-downgraded

### Social Credibility Flag / 社交可信度标记
- Only set for `source_type = "twitter"`. LLM pre-screens for fake news patterns. Non-Twitter → `null`.
- `verification_priority`: Derived from flag. `likely_unreliable` → `high`, `needs_verification` → `medium`, otherwise `low`.
- `corroboration_status`: Set during EvidenceVerify. Tracks whether independent non-social sources confirm. Non-Twitter → `null`.

---

## 5.2 ClaimItem

A factual or inferential claim made by a debater. / 辩手提出的声明。

```json
{
  "claim_id": "clm_<round>_<side>_<seq>",
  "round": 1,
  "speaker": "pro | con",
  "claim_type": "fact | inference | analogy",
  "claim_text": "The claim statement...",
  "evidence_ids": ["evi_abc12345", "evi_def67890"],
  "status": "verified | contested | unverified | stale",
  "last_verified_at": "2026-03-09T12:00:00Z",
  "judge_note": "Judge's assessment...",
  "mandatory_response": false,
  "conflict_details": [
    {
      "source_a": {"evidence_id": "evi_xxx", "position": "Source A claims..."},
      "source_b": {"evidence_id": "evi_yyy", "position": "Source B claims..."},
      "divergence_point": "The specific point of disagreement...",
      "judge_assessment": "Judge's evaluation of the conflict..."
    }
  ]
}
```

### Claim Status State Machine / 声明状态机

```
                  ┌──────────┐
                  │unverified│
                  └────┬─────┘
                       │
            ┌──────────┼──────────┐
            ▼          ▼          ▼
       ┌────────┐ ┌─────────┐ ┌─────┐
       │verified│ │contested│ │stale│
       └───┬────┘ └────┬────┘ └──┬──┘
           │           │         │
           ├───►contested◄───────┤
           │           │         │
           ├───►stale   │        │
           │           ├───►verified
           │           ├───►stale
           └───────────┘
```

Transitions / 转换 (8 total):
- `unverified → verified`: Cross-source confirmed / 跨来源确认
- `unverified → contested`: Sources conflict / 来源冲突
- `unverified → stale`: Current-state source expired / 来源过期
- `verified → contested`: New contradicting evidence / 新矛盾证据
- `verified → stale`: Fact-track source expired / 事实轨道来源过期
- `contested → verified`: Resolution with new evidence / 新证据解决争议
- `contested → stale`: All sources expired / 所有来源过期
- `stale → verified`: Fresh confirming source found / 找到新鲜确认来源

**Critical rule / 关键规则**: Reasoning-track claims (claim_type=analogy or evidence_track=reasoning) are NEVER auto-transitioned to `stale`.

### Conflict Details / 冲突明细

Populated by Judge during verification when sources conflict. Allows FinalReport to explain WHY a claim is contested, not just THAT it is.

---

## 5.3 DebateTurn (Pro/Con Turn Output)

Structured output from a single debate turn. / 单次辩论回合的结构化输出。

```json
{
  "round": 1,
  "side": "pro | con",
  "arguments": [
    {
      "claim_text": "Main argument statement...",
      "claim_type": "fact | inference | analogy",
      "evidence_ids": ["evi_abc12345"],
      "reasoning_chain": {
        "observed_facts": "What data/events support this...",
        "mechanism": "Why does this cause that...",
        "scenario_implication": "What follows from this...",
        "trigger_conditions": "What would make this scenario happen...",
        "falsification_conditions": "What would prove this wrong..."
      }
    }
  ],
  "rebuttals": [
    {
      "target_claim_id": "clm_1_con_1",
      "rebuttal_text": "Counter-argument...",
      "evidence_ids": ["evi_def67890"]
    }
  ],
  "mandatory_responses": [
    {
      "point_id": "mrp_1_1",
      "response_text": "Addressing judge's point..."
    }
  ],
  "new_evidence": [],
  "historical_wisdom": {
    "weight": "advisory",
    "references": [
      {
        "historical_event": "Name/description of historical event",
        "era_context": "Historical context and background",
        "parallel_to_current": "How this parallels the current debate topic",
        "key_differences": "Critical structural differences from current situation",
        "lesson_extracted": "The insight or lesson drawn",
        "applicability_caveat": "Limitations of this historical reference"
      }
    ]
  },
  "speculative_scenarios": {
    "weight": "exploratory",
    "scenarios": [
      {
        "scenario_name": "Short descriptive name",
        "premise": "The 'what if' starting condition",
        "chain_of_events": "A -> B -> C sequence of consequences",
        "probability_estimate": "low (<10%) | medium (10-40%) | high (>40%)",
        "impact_if_realized": "Severity and scope of impact",
        "early_warning_signals": ["Observable precursors to watch for"],
        "what_would_falsify": "What would invalidate this scenario"
      }
    ]
  }
}
```

### Reasoning Chain — MANDATORY for every argument
### Historical Wisdom — `weight: "advisory"`, must include `key_differences` + `applicability_caveat`
### Speculative Scenarios — controlled by `config.speculation_level`:
- `conservative` → section OMITTED entirely
- `moderate` → 1-2 evidence-grounded scenarios
- `exploratory` → 2-4 scenarios including black swans
- Every scenario MUST include `what_would_falsify`

---

## 5.4 JudgeRuling

Judge's structured output after auditing a round. / 裁判审计回合后的输出。

```json
{
  "round": 1,
  "verification_results": [
    {
      "claim_id": "clm_1_pro_1",
      "original_status": "unverified",
      "new_status": "verified",
      "reasoning": "Cross-source confirmed by Reuters and Bloomberg..."
    }
  ],
  "causal_validity_flags": [
    {
      "claim_id": "clm_1_con_2",
      "issue": "correlation presented as causation",
      "severity": "critical | moderate | minor"
    }
  ],
  "mandatory_response_points": [
    {
      "point_id": "mrp_1_1",
      "target": "pro | con | both",
      "point": "What must be addressed...",
      "reason": "Why this needs response..."
    }
  ],
  "historical_wisdom_assessment": [
    {
      "side": "pro | con",
      "historical_event": "...",
      "relevance_grade": "strong_parallel | moderate_parallel | weak_parallel",
      "honesty_grade": "honest | partially_honest | misleading",
      "note": "..."
    }
  ],
  "round_summary": "Neutral summary of key developments..."
}
```

---

## 5.5 FinalReport

Final synthesis output after all debate rounds. / 所有辩论回合后的最终综合输出。

```json
{
  "topic": "The debate topic",
  "total_rounds": 3,
  "generated_at": "2026-03-09T18:00:00Z",
  "verdict_summary": "One-sentence overall judgment",
  "report_path": "reports/debate_report.md",
  "verified_facts": ["Cross-source confirmed factual statements..."],
  "probable_conclusions": ["High-confidence conclusions with qualifiers..."],
  "contested_points": [
    {
      "point": "The contested claim or issue",
      "claim_ids": ["clm_1_pro_2", "clm_2_con_1"],
      "pro_position": "Pro's strongest argument with evidence summary",
      "con_position": "Con's strongest argument with evidence summary",
      "key_rebuttals": [
        {
          "from": "pro | con",
          "target": "What they're rebutting",
          "argument": "The rebuttal content",
          "evidence_ids": ["evi_xxx"]
        }
      ],
      "judge_assessment": "Judge's evaluation of which side has stronger support",
      "resolution_status": "unresolved | leaning_pro | leaning_con | partially_resolved"
    }
  ],
  "to_verify": ["Claims needing further verification with suggested methods..."],
  "scenario_outlook": {
    "base_case": "Most likely scenario based on verified facts...",
    "upside_triggers": ["Conditions that would improve outlook..."],
    "downside_triggers": ["Conditions that would worsen outlook..."],
    "falsification_conditions": ["What would invalidate base case..."]
  },
  "watchlist_24h": [
    {
      "item": "What to monitor...",
      "reversal_trigger": "What would change conclusions...",
      "monitoring_source": "Where to watch..."
    }
  ],
  "evidence_diversity_assessment": {
    "source_type_distribution": {"web": 15, "academic": 3, "twitter": 8},
    "credibility_tier_distribution": {"tier1": 2, "tier2": 8, "tier3": 10, "tier4": 8},
    "geographic_diversity": "assessment text...",
    "perspective_balance": "assessment text...",
    "diversity_warning": "warning text or null"
  },
  "speculative_frontier": [
    {
      "scenario_name": "...",
      "proposed_by": "pro | con",
      "premise": "...",
      "chain_of_events": "...",
      "probability": "...",
      "impact": "...",
      "early_warnings": ["..."],
      "judge_quality_note": "..."
    }
  ],
  "historical_insights": {
    "key_parallels": ["Most relevant historical parallels..."],
    "conflicting_lessons": ["Where historical evidence points both ways..."],
    "meta_pattern": "Overarching historical pattern, if any..."
  },
  "executive_summary": {
    "summary_paragraph": "One-paragraph executive summary...",
    "top_verified_facts": ["..."],
    "top_contested_points": ["..."],
    "base_case_outlook": "...",
    "top_watchlist_items": ["..."]
  },
  "decision_matrix": {
    "dimensions": [
      {
        "factor": "Factor name",
        "pro_position": "Pro's strongest point on this factor",
        "con_position": "Con's strongest point on this factor",
        "evidence_strength": "strong | moderate | weak",
        "judge_note": "..."
      }
    ],
    "overall_lean": "Slightly favors pro/con because...",
    "key_uncertainty": "The factor most likely to change the conclusion...",
    "recommendation": "Based on current evidence..."
  },
  "conclusion_profiles": [
    {
      "conclusion_id": "concl_1",
      "conclusion_text": "Conclusion description",
      "source_claims": ["clm_1_pro_1", "clm_2_con_3"],
      "profile": {
        "probability": {
          "value": "high (>70%) | medium (30-70%) | low (<30%)",
          "rationale": "Basis for probability judgment"
        },
        "confidence": {
          "value": "high | medium | low",
          "rationale": "How evidence quality affects certainty"
        },
        "consensus": {
          "value": "high | partial | low",
          "rationale": "Degree of disagreement between sides"
        },
        "evidence_coverage": {
          "value": "complete | partial | sparse",
          "gaps": "Key missing links in the evidence chain"
        },
        "reversibility": {
          "value": "high | medium | low",
          "reversal_trigger": "What could overturn this conclusion"
        },
        "validity_window": {
          "value": "hours | days | weeks | months | indefinite",
          "expiry_condition": "What would invalidate this conclusion"
        },
        "impact_magnitude": {
          "value": "extreme | high | medium | low",
          "scope": "Scope and depth of impact"
        },
        "causal_clarity": {
          "value": "clear_chain | partial_chain | correlation_only",
          "weakest_link": "Weakest link in the causal chain"
        },
        "actionability": {
          "value": "directly_actionable | informational | requires_more_data",
          "suggested_action": "Suggested action if actionable"
        },
        "falsifiability": {
          "value": "easily_testable | testable_with_effort | hard_to_test",
          "test_method": "How to verify this conclusion"
        }
      }
    }
  ]
}
```

### Conclusion Profiles — 10 Dimensions / 结论画像 10 维度

| Dimension / 维度 | What it measures / 衡量什么 |
|---|---|
| Probability / 概率 | Likelihood of event occurring |
| Confidence / 置信度 | Certainty of the probability judgment itself |
| Consensus / 共识度 | Degree of disagreement between sides |
| Evidence Coverage / 证据完整度 | Completeness of evidence chain |
| Reversibility / 可逆性 | How easily new evidence could overturn |
| Validity Window / 时效窗口 | How long the conclusion remains valid |
| Impact Magnitude / 影响幅度 | Severity if realized |
| Causal Clarity / 因果清晰度 | Completeness of causal chain |
| Actionability / 可操作性 | Whether it can guide decisions |
| Falsifiability / 可证伪性 | How easily it can be tested |

**Key rule**: Each dimension uses LLM semantic judgment, NOT mechanical scoring.

> All FinalReport JSON fields are English-only. Chinese translation appears in debate_report.md as an appended section.

---

## 5.6 DebateConfig

Configuration for a debate session. Written to `config.json` in the workspace root.

```json
{
  "topic": "The debate topic",
  "rounds": 3,
  "round_count": 3,
  "pro_model": "balanced",
  "con_model": "balanced",
  "judge_model": "deep",
  "created_at": "2026-03-09T12:00:00Z",
  "domain": "geopolitics | tech | health | finance | philosophy | culture | general",
  "depth": "quick | standard | deep",
  "evidence_scope": "web_only | academic_included | user_provided | mixed",
  "output_format": "full_report | executive_summary | decision_matrix",
  "speculation_level": "conservative | moderate | exploratory",
  "language": "en | zh | bilingual",
  "focus_areas": ["user-defined dimensions to focus on"],
  "mode": "balanced | red_team",
  "evidence_refresh": "upfront_only | per_round | hybrid",
  "status": "initialized | in_progress | complete"
}
```

### Field Documentation / 字段说明

- `depth`: Controls search and argument intensity
  - `quick`: 3 search queries, 2 arguments per turn, lighter verification
  - `standard`: 5 search queries, 2-4 arguments per turn, standard verification
  - `deep`: 8 search queries, 3-5 arguments per turn, thorough verification
- `domain`: Defaults to `"general"`. When general, LLM infers from topic text.
- `mode`:
  - `balanced`: Standard pro/con debate
  - `red_team`: Con = Red Team (risks), Pro = Blue Team (mitigations)
- **[v2 NEW]** `evidence_refresh`:
  - `upfront_only`: SourceIngest runs once before Round 1 (v1 behavior)
  - `per_round`: SourceIngest runs before EACH round, driven by judge feedback
  - `hybrid` (default): Broad ingest before Round 1, focused ingest before subsequent rounds

---

## 5.7 Audit Trail Entry (JSONL)

Each line in `logs/audit_trail.jsonl` is an independent JSON object.

```json
{"timestamp": "2026-03-09T12:00:00Z", "action": "workspace_initialized | round_started | pro_turn_complete | con_turn_complete | judge_ruling_complete | claim_status_changed | evidence_added | report_generated | refresh_triggered | per_round_evidence_ingest | evidence_merged_from_turn", "details": {}}
```

**[v2 NEW] Actions:**
- `per_round_evidence_ingest`: Orchestrator's per-round focused evidence search
- `evidence_merged_from_turn`: Orchestrator merged Pro/Con's new_evidence into evidence_store

---

# Section 6: Orchestration Flow — v2 Per-Round Evidence + Parallel Pro/Con
# 第六章：编排流程 — v2 每轮证据刷新 + 并行正反方

## Complete Flow Diagram / 完整流程图

```
PHASE 1: INITIALIZATION
──────────────────────────────────────────────────
  User provides: topic, rounds (default 3), options
         │
         ▼
  init-workspace.sh → creates directory structure + empty JSONs
         │
         ▼
  Write config.json (DebateConfig schema)
         │
         ▼
  SourceIngest(broad, round=0)
    - Generate 3-8 diverse search queries (based on depth)
    - WebSearch + WebFetch for each query
    - Normalize to EvidenceItem format
    - Hash via hash-snippet.sh, dedupe by url+hash
    - Tag: discovered_by="orchestrator", discovered_at_round=0
    - Write evidence_store.json
         │
         ▼
  FreshnessCheck
    - Classify each item's evidence_track (fact vs reasoning)
    - Apply freshness rules
    - Update evidence_store.json
         │
         ▼
  config.json: status = "evidence_gathered"


PHASE 2: DEBATE ROUNDS (for each round N = 1..R)
──────────────────────────────────────────────────

  Step 2a [v2 NEW]: PER-ROUND EVIDENCE REFRESH
  ─────────────────────────────────────────────
  If evidence_refresh == "per_round" OR ("hybrid" AND N > 1):
    │
    ├─ Read judge_ruling from round N-1 (if exists):
    │   - mandatory_response_points → search gaps
    │   - causal_validity_flags → weak evidence areas
    │   - contested claims → need more authoritative sources
    │
    ├─ Generate focused search queries driven by:
    │   1. Judge's unresolved questions
    │   2. Contested claims needing stronger evidence
    │   3. Gaps in evidence_diversity_assessment
    │
    ├─ SourceIngest(focused, round=N)
    │   - Tag: discovered_by="orchestrator", discovered_at_round=N
    │   - search_context = "judge_feedback_round_{N-1}"
    │   - Dedupe against existing evidence_store (url+hash)
    │
    ├─ FreshnessCheck (re-evaluate ALL evidence)
    │
    └─ Audit log: per_round_evidence_ingest

  Step 2b [v2 NEW]: PARALLEL PRO + CON
  ─────────────────────────────────────
  Round 1: Pro and Con execute IN PARALLEL
    - Neither sees the other's current round arguments
    - Both read: evidence_store, claim_ledger
    - Both independently search for private supplement evidence

  Round 2+: Pro and Con execute IN PARALLEL
    - Both read: evidence_store, claim_ledger,
      round N-1 pro_turn, con_turn, judge_ruling
    - Neither sees the other's CURRENT round arguments
    - Both independently search for private supplement evidence

  ┌─────────────────────────┐  ┌─────────────────────────┐
  │      PRO-DEBATER        │  │      CON-DEBATER        │
  │                         │  │                         │
  │ Read: evidence_store    │  │ Read: evidence_store    │
  │ Read: claim_ledger      │  │ Read: claim_ledger      │
  │ [N>1] Read: round N-1/* │  │ [N>1] Read: round N-1/* │
  │                         │  │                         │
  │ Build arguments         │  │ Build arguments         │
  │ Search new evidence     │  │ Search new evidence     │
  │ Write: pro_turn.json    │  │ Write: con_turn.json    │
  └─────────────────────────┘  └─────────────────────────┘
              │                            │
              └───────────┬────────────────┘
                          ▼

  Step 2c: VALIDATE OUTPUTS
  ─────────────────────────
  validate-json.sh pro_turn.json pro_turn
  validate-json.sh con_turn.json con_turn
  [N>1] Check mandatory response points addressed
  If validation fails: re-prompt agent (max 2 retries)

  Step 2d: JUDGE AUDIT
  ────────────────────
  Judge reads: BOTH pro_turn + con_turn + evidence_store + claim_ledger
  Judge writes: judge_ruling.json
  CRITICAL: Judge independently verifies claims via search
  validate-json.sh judge_ruling.json judge_ruling

  Step 2e: POST-ROUND PROCESSING
  ──────────────────────────────
  1. Extract new claims from pro_turn + con_turn → update claim_ledger
  2. Apply judge's verification_results → update claim statuses
  3. [v2 NEW] Merge new_evidence from BOTH turns → evidence_store
     - Tag: discovered_by="pro"/"con", discovered_at_round=N
     - Dedupe by url+hash
     - Audit log: evidence_merged_from_turn
  4. Append round summary to audit_trail.jsonl
  5. config.json: current_round=N, status="round_N_complete"


PHASE 3: FINAL OUTPUT
──────────────────────────────────────────────────
  FinalSynthesis:
    - Read all rounds' data, claim ledger, full evidence store
    - Categorize: verified_facts, probable_conclusions, contested_points
    - Build scenario_outlook + watchlist_24h
    - Generate conclusion_profiles (10 dimensions)
    - Write: reports/final_report.json
    - Write: reports/debate_report.md (bilingual, Section 8 format)
    - validate-json.sh final_report.json final_report
    - config.json: status = "complete"


PHASE 4: SCHEDULED REFRESH (OPTIONAL)
──────────────────────────────────────────────────
  If user agrees:
    - Create scheduled task (6-hour cron)
    - On trigger: re-run SourceIngest + FreshnessCheck
    - If evidence states changed: regenerate report
```

---

# Section 7: Agent Isolation / Read-Write Matrix
# 第七章：Agent 隔离 / 读写矩阵

## v2 Access Matrix (Parallel Model) / v2 访问矩阵（并行模式）

| Agent | Reads / 读 | Writes / 写 |
|---|---|---|
| **Orchestrator** | All files / 全部 | All files / 全部 |
| **Pro-Debater** | evidence_store, claim_ledger, round N-1/{pro_turn, con_turn, judge_ruling} | round_N/pro_turn.json |
| **Con-Debater** | evidence_store, claim_ledger, round N-1/{pro_turn, con_turn, judge_ruling} | round_N/con_turn.json |
| **Neutral-Judge** | round_N/{pro_turn, con_turn}, evidence_store, claim_ledger | round_N/judge_ruling.json |

### v2 Key Change: Parallel Symmetry / v2 关键变更：并行对称

In v1, Con could read Pro's CURRENT round turn (asymmetric). In v2:
- **Round 1**: Neither Pro nor Con sees the other's arguments (both parallel, fresh start)
- **Round 2+**: Both see PREVIOUS round's full picture (pro+con+judge), but NEVER current round opponent

This means:
- Pro and Con have **identical information** at the start of each round
- Arguments must be **proactive**, not just reactive
- Rebuttals target **previous round** arguments, forcing deeper engagement

---

# Section 8: debate_report.md Format Specification
# 第八章：debate_report.md 格式规范

This format is EXPLICIT, not emergent. FinalSynthesis MUST produce a report matching this structure.
此格式是显式的，不是 LLM 自由发挥。FinalSynthesis 必须产出匹配此结构的报告。

```markdown
# Debate Report: {Topic}

## Executive Summary
One paragraph: what was debated, key findings, overall assessment, probability distribution.

## Decision Matrix
| Factor | Assessment | Confidence | Key Evidence |
|---|---|---|---|
| ... | ... | ... | evi_xxx |
**Overall lean**: ...
**Key uncertainty**: ...

## Verified Facts
| # | Claim | Status | Sources | Track |
|---|---|---|---|---|
| 1 | ... | Verified | evi_xxx, evi_yyy | fact/reasoning |

## Contested Points

### CP-{N}: {Point Title}
**Status**: unresolved | leaning_pro | leaning_con | partially_resolved

**Pro Position**: ... (Evidence: evi_xxx)

**Con Position**: ... (Evidence: evi_yyy)

**Key Rebuttals**:
- **[Side -> Side]** Description (Evidence: evi_zzz)

**Judge Assessment**: Neutral evaluation of which side has stronger support.

---
(Repeat for each contested point)

## Key Arguments by Round
### Round {N}
| Side | Core Argument | Strength | Key Evidence |
|---|---|---|---|
| Pro | ... | Strong/Moderate/Weak | evi_xxx |
| Con | ... | Strong/Moderate/Weak | evi_yyy |

## Scenario Outlook
| Scenario | Probability | Trigger | Timeframe |
|---|---|---|---|
| Base case | ... | ... | ... |
| Upside | ... | ... | ... |
| Downside | ... | ... | ... |

## Watchlist
| # | Item | Why It Matters | Monitor How |
|---|---|---|---|
| 1 | ... | ... | ... |

## Evidence Inventory
| ID | Source | Type | Tier | Freshness | Track | Discovered By | Round |
|---|---|---|---|---|---|---|---|
| evi_xxx | ... | web | tier2 | current | fact | orchestrator | 0 |
**Diversity Warning**: (if applicable from evidence_diversity_assessment)

## Methodology
- Rounds: N, Mode: balanced/red_team
- Evidence items: N, Credibility distribution: tier1=X, tier2=Y...
- Evidence refresh: per_round/hybrid/upfront_only
- Speculation level: conservative/moderate/exploratory
- Generated: ISO timestamp

---

# 中文翻译 / Chinese Translation
(Complete translation of ALL above sections in Chinese)
```

---

# Section 9: Generic Skill Structure (Agent Skills Standard)
# 第九章：通用 Skill 结构（Agent Skills 标准）

## Day-1 Compatibility / 第一天兼容

The skill structure follows the [Agent Skills open standard](https://agentskills.io/specification) from day 1. Compatible with Claude Code, GPT/OpenClaw, Codex, and skills.sh.

## SKILL.md Frontmatter / 前置元数据

```yaml
---
name: critical-debater-suite
description: >
  Multi-agent adversarial debate system with 4 roles (Pro, Con, Judge, Orchestrator),
  per-round evidence refresh, 5-element reasoning chains, and structured bilingual
  Markdown report output. Use this skill when the user says "debate", "start a debate",
  "red team this", "analyze from multiple perspectives", or provides a topic for
  critical examination.
license: MIT-0
compatibility: Requires bash, jq, python3, shasum, and internet access for web search.
metadata:
  author: xwxga
  version: "2.0.0"
  homepage: "https://github.com/xwxga/critical-debater"
  tags: debate, evidence, reasoning, multi-agent, report
---
```

## Directory Structure / 目录结构

```
critical-debater-suite/
├── SKILL.md              # Frontmatter + routing instructions
├── capabilities/         # 9 capability modules
│   ├── debate.md           # Full debate orchestration
│   ├── source-ingest.md    # Search + normalize evidence
│   ├── freshness-check.md  # Tag evidence freshness
│   ├── evidence-verify.md  # Cross-source verification
│   ├── debate-turn.md      # Construct structured arguments
│   ├── judge-audit.md      # Independent audit + ruling
│   ├── claim-ledger-update.md  # Claim state machine
│   ├── analogy-safeguard.md    # Historical analogy validation
│   └── final-synthesis.md      # Report generation
├── references/
│   └── data-contracts.md   # All JSON schemas (this Section 5)
├── scripts/
│   ├── init-workspace.sh
│   ├── validate-json.sh
│   ├── hash-snippet.sh
│   ├── append-audit.sh
│   └── debate_orchestrator_generic.py
├── evals/
│   └── evals.json          # Trigger/no-trigger test cases
└── examples/
    └── quickstart.md       # One-command smoke test
```

## Routing / 路由

SKILL.md routes user intent to one capability:
- `debate` / `start debate` → `capabilities/debate.md`
- `search evidence` / `build evidence store` → `capabilities/source-ingest.md`
- `judge round` / `audit round` → `capabilities/judge-audit.md`
- `final report` / `synthesis` → `capabilities/final-synthesis.md`
- Mixed request → pick primary intent, chain capabilities in required order

## Generic Capability Names / 通用能力名称

Use provider-agnostic names in prompts:
- `search` (maps to WebSearch on Claude Code, web_search on Codex)
- `fetch` (maps to WebFetch on Claude Code)
- `spawn_role` (maps to Agent tool on Claude Code)
- Model tiers: `fast`, `balanced`, `deep` (not sonnet/opus)

## Fallback Chains / 回退链

- search: native → adapter → `evidence_gap` soft-failure
- fetch: native → adapter → `fetch_skipped` soft-failure
- spawn_role: native → adapter → serial role emulation

---

# Section 10: Workspace Directory Structure
# 第十章：Workspace 目录结构

```
debates/<topic-slug>-<YYYYMMDD-HHMMSS>/
├── config.json                          # DebateConfig schema
├── evidence/
│   └── evidence_store.json              # EvidenceItem[] (cumulative)
├── claims/
│   └── claim_ledger.json                # ClaimItem[]
├── rounds/
│   ├── round_1/
│   │   ├── pro_turn.json                # DebateTurn (pro)
│   │   ├── con_turn.json                # DebateTurn (con)
│   │   └── judge_ruling.json            # JudgeRuling
│   ├── round_2/
│   │   └── ...
│   └── round_N/
│       └── ...
├── reports/
│   ├── final_report.json                # FinalReport schema
│   └── debate_report.md                 # Bilingual Markdown report
├── logs/
│   └── audit_trail.jsonl                # Append-only audit log
```

---

# Section 11: Shell Scripts (Complete Source)
# 第十一章：Shell 脚本（完整源码）

These are the deterministic code layer. Preserve exactly.
这些是确定性代码层，必须精确保留。

## 11.1 init-workspace.sh

```bash
#!/bin/bash
# init-workspace.sh — Create debate workspace directory structure
set -euo pipefail

WORKSPACE_DIR="${1:?Usage: $0 <workspace_dir> <topic> <rounds>}"
TOPIC="${2:?Usage: $0 <workspace_dir> <topic> <rounds>}"
ROUNDS="${3:-3}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

mkdir -p "$WORKSPACE_DIR"/{evidence,claims,rounds,reports,logs}

for i in $(seq 1 "$ROUNDS"); do
  mkdir -p "$WORKSPACE_DIR/rounds/round_$i"
done

cat > "$WORKSPACE_DIR/config.json" <<EOF
{
  "topic": $(printf '%s' "$TOPIC" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))'),
  "round_count": $ROUNDS,
  "current_round": 0,
  "status": "initialized",
  "created_at": "$TIMESTAMP",
  "updated_at": "$TIMESTAMP"
}
EOF

echo '[]' > "$WORKSPACE_DIR/evidence/evidence_store.json"
echo '[]' > "$WORKSPACE_DIR/claims/claim_ledger.json"
touch "$WORKSPACE_DIR/logs/audit_trail.jsonl"

AUDIT_LINE=$(cat <<EOF
{"timestamp":"$TIMESTAMP","action":"workspace_initialized","topic":$(printf '%s' "$TOPIC" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))'),"rounds":$ROUNDS}
EOF
)
echo "$AUDIT_LINE" >> "$WORKSPACE_DIR/logs/audit_trail.jsonl"

echo "Workspace initialized at $WORKSPACE_DIR"
```

## 11.2 validate-json.sh

```bash
#!/bin/bash
# validate-json.sh — Validate JSON files against data contract schemas
set -euo pipefail

FILE="${1:?Usage: $0 <file> <schema_type>}"
SCHEMA="${2:?Usage: $0 <file> <schema_type>}"

if [ ! -f "$FILE" ]; then
  echo "ERROR: File not found: $FILE" >&2
  exit 1
fi

if ! jq empty "$FILE" 2>/dev/null; then
  echo "ERROR: Invalid JSON in $FILE" >&2
  exit 1
fi

case "$SCHEMA" in
  config)
    REQUIRED='["topic", "round_count", "current_round", "status", "created_at"]'
    ;;
  evidence_item)
    REQUIRED='["evidence_id", "source_type", "url", "snippet", "hash", "credibility_tier", "freshness_status", "evidence_track"]'
    ;;
  claim_item)
    REQUIRED='["claim_id", "round", "speaker", "claim_type", "claim_text", "evidence_ids", "status"]'
    ;;
  judge_ruling)
    REQUIRED='["round", "verification_results", "mandatory_response_points", "round_summary"]'
    ;;
  final_report)
    REQUIRED='["topic", "total_rounds", "verified_facts", "probable_conclusions", "contested_points", "to_verify", "scenario_outlook", "watchlist_24h"]'
    ;;
  pro_turn|con_turn)
    REQUIRED='["round", "side", "arguments", "rebuttals"]'
    ;;
  *)
    echo "ERROR: Unknown schema type: $SCHEMA" >&2
    exit 1
    ;;
esac

ERRORS=0
for field in $(echo "$REQUIRED" | jq -r '.[]'); do
  IS_ARRAY=$(jq 'type == "array"' "$FILE")
  if [ "$IS_ARRAY" = "true" ]; then
    HAS_ELEMENTS=$(jq 'length > 0' "$FILE")
    if [ "$HAS_ELEMENTS" = "true" ]; then
      HAS_FIELD=$(jq --arg f "$field" '.[0] | has($f)' "$FILE")
      if [ "$HAS_FIELD" = "false" ]; then
        echo "ERROR: Missing required field '$field' in first element of $FILE" >&2
        ERRORS=$((ERRORS + 1))
      fi
    fi
  else
    HAS_FIELD=$(jq --arg f "$field" 'has($f)' "$FILE")
    if [ "$HAS_FIELD" = "false" ]; then
      echo "ERROR: Missing required field '$field' in $FILE" >&2
      ERRORS=$((ERRORS + 1))
    fi
  fi
done

if [ $ERRORS -gt 0 ]; then
  echo "FAILED: $ERRORS missing field(s) in $FILE (schema: $SCHEMA)" >&2
  exit 1
fi

echo "OK: $FILE validates against $SCHEMA"
exit 0
```

## 11.3 hash-snippet.sh

```bash
#!/bin/bash
# hash-snippet.sh — Compute SHA-256 hash of text input
set -euo pipefail

TEXT="${1:?Usage: $0 <text>}"

echo -n "$TEXT" | shasum -a 256 | cut -d' ' -f1
```

## 11.4 append-audit.sh

```bash
#!/bin/bash
# append-audit.sh — Atomically append a JSONL line to audit trail
set -euo pipefail

AUDIT_FILE="${1:?Usage: $0 <audit_file> <json_line>}"
JSON_LINE="${2:?Usage: $0 <audit_file> <json_line>}"

if ! echo "$JSON_LINE" | jq empty 2>/dev/null; then
  echo "ERROR: Invalid JSON: $JSON_LINE" >&2
  exit 1
fi

touch "$AUDIT_FILE"

TEMP_FILE=$(mktemp "${AUDIT_FILE}.XXXXXX")
cp "$AUDIT_FILE" "$TEMP_FILE"
echo "$JSON_LINE" >> "$TEMP_FILE"
mv "$TEMP_FILE" "$AUDIT_FILE"
```

---

# Section 12: Orchestrator Implementation Blueprint
# 第十二章：编排器实现蓝图

This is an architectural blueprint, not complete source code. The pattern is proven in the v1 Python orchestrator (633 lines).

## Core Pattern / 核心模式

```python
# Options dataclass — all config fields
@dataclass
class Options:
    topic: str
    rounds: int
    output_format: str       # full_report | executive_summary | decision_matrix
    language: str             # en | zh | bilingual
    domain: str               # geopolitics | tech | health | finance | ...
    depth: str                # quick | standard | deep
    mode: str                 # balanced | red_team
    speculation: str          # conservative | moderate | exploratory
    evidence_refresh: str     # upfront_only | per_round | hybrid [v2 NEW]
    focus: list[str]
    allow_fallback: bool
    min_evidence: int         # minimum evidence items required
    source_retries: int       # retry count for SourceIngest
    min_args: int             # minimum arguments per turn
    min_rebuttals: int        # minimum rebuttals per turn
    step_timeout_sec: int

# Execution pattern — dispatch steps with completion markers
def dispatch_agent(step_id: str, prompt: str):
    # 1. Build prompt with all context (file paths, schemas)
    # 2. Execute via detected runtime (claude -p, codex -p, etc.)
    # 3. Check for completion marker: "DONE:{step_id}"
    # 4. Log output to logs/{step_id}.log
    # 5. If failed: retry up to 2 times, then raise

# v2 Per-round flow additions:
def run_per_round_ingest(round_num: int):
    # 1. Read judge_ruling from round N-1
    # 2. Extract search focus from mandatory_response_points + contested claims
    # 3. dispatch_agent("source_ingest_round_{N}", focused_ingest_prompt)
    # 4. dispatch_agent("freshness_check_round_{N}", freshness_prompt)
    # 5. Audit log: per_round_evidence_ingest

def run_parallel_debate_turn(round_num: int):
    # 1. Launch Pro and Con in parallel (both read same evidence + previous round)
    # 2. Wait for both to complete
    # 3. Validate both outputs
    # 4. If validation fails: re-prompt (max 2 retries)

def merge_new_evidence(round_num: int):
    # 1. Read new_evidence[] from pro_turn and con_turn
    # 2. Dedupe against evidence_store (url + hash)
    # 3. Tag: discovered_by, discovered_at_round
    # 4. Append to evidence_store.json
    # 5. Audit log: evidence_merged_from_turn
```

## Quality Gates / 质量门

- JSON validation via `validate-json.sh` after every step
- Minimum evidence count check after SourceIngest
- Minimum arguments + rebuttals per turn
- Mandatory response points addressed check
- Completion marker verification (`DONE:{step_id}`)

---

# Section 13: Error Handling & Fallbacks
# 第十三章：错误处理与回退

| Scenario / 场景 | Action / 处理 |
|---|---|
| Search returns no results / 搜索无结果 | Broaden keywords, try alternative angles; if still empty, note "insufficient evidence" / 扩关键词，仍无则标注 |
| All current-state sources stale / 所有当前来源过期 | Mark affected claims stale, note in report that conclusions are provisional / 标 stale，报告标注为暂定 |
| Agent produces invalid JSON / Agent 产出无效 JSON | Re-prompt with explicit JSON structure (max 2 retries) / 重试 2 次 |
| Agent skips mandatory response point / Agent 跳过必答点 | Re-prompt with specific missed point (max 2 retries), then log "unaddressed" / 重试后记录未回应 |
| WebFetch fails on JS-heavy page / 抓取失败 | Retry once, skip source, never block debate for one source / 重试一次后跳过 |
| Hash script fails / Hash 脚本失败 | Fall back to first 8 chars of URL as evidence_id / 使用 URL 前 8 字符 |
| Hallucinated citation / 幻觉引用 | Judge catches via independent verification / Judge 独立验证兜底 |

---

# Section 14: Cost & Model Strategy
# 第十四章：成本与模型策略

## Model Tier Assignment / 模型层级分配

| Agent | Tier | Rationale / 理由 |
|---|---|---|
| Orchestrator | `balanced` | Workflow control, no deep reasoning needed / 工作流控制 |
| Pro-Debater | `balanced` | Good reasoning at reasonable cost / 性价比好 |
| Con-Debater | `balanced` | Same as Pro / 同正方 |
| Neutral-Judge | `deep` | Requires best reasoning for verification + causal audit / 需要最强推理能力 |

## Token Budget Guidelines / Token 预算指导

| Step | Estimated Tokens |
|---|---|
| SourceIngest (per query) | ~2K input + ~1K output |
| DebateTurn (per side) | ~8K input + ~4K output |
| JudgeRuling | ~12K input + ~4K output |
| FinalSynthesis | ~20K input + ~8K output |
| **Total 3-round debate** | **~150-200K tokens** |

---

# Section 15: Acceptance Criteria
# 第十五章：验收标准

- [ ] At least 3 rounds end-to-end without manual intervention / 至少 3 轮端到端无手动干预
- [ ] Valid JSON matching data contracts every round / 每轮 JSON 符合数据契约
- [ ] No critical claim `verified` without cross-source validation / 关键声明无交叉验证不能 verified
- [ ] Reasoning-track claims NEVER auto-degraded to `stale` / 推理轨道永不降级为 stale
- [ ] Twitter-only claims NEVER become `verified` / Twitter 独有声明永不 verified
- [ ] Per-round evidence refresh works when `evidence_refresh = "per_round"` / 每轮证据刷新正常
- [ ] Pro and Con execute in parallel (neither sees other's current round) / 并行执行
- [ ] `debate_report.md` matches Section 8 format exactly / 报告格式匹配第八章
- [ ] Report is bilingual (English + Chinese) / 报告双语
- [ ] All agent interactions logged in audit trail / 全部操作有审计日志
- [ ] Generic skill structure validates against Agent Skills spec / Skill 结构通过验证
- [ ] Evidence items tagged with `discovered_by` and `discovered_at_round` / 证据带来源标记
- [ ] Conclusion profiles contain all 10 dimensions / 结论画像包含全部 10 维度

---

# Section 16: CLAUDE.md Template
# 第十六章：CLAUDE.md 模板

Use this as the `.claude/CLAUDE.md` for the new project:

```markdown
# Critical Debater v2 — Project Instructions

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| {DATE} | {Author} | 初始创建 / Initial creation |

## Project Overview / 项目概述

Multi-agent adversarial debate system: 4 agents, 1 suite skill (v2.0.0), file-based state.
Per-round evidence refresh, parallel Pro/Con, structured bilingual reports.

Design spec: `docs/critical-debater-v2-spec.md`

## Working Approach / 工作方式

1. **LLM first** — 阅读、判断、总结、分类、提取、论证构建、因果审计 → 全部用 LLM
2. **Existing skill second** — 复用 critical-debater-suite 的 9 个 capability
3. **Deterministic code last** — 仅用于 scripts/ 中的操作

## Evidence Rules / 证据规则

- Two tracks: Fact (ages to stale) vs Reasoning (timeless)
- Twitter: signal only, never verified without independent source
- Cross-source: critical claims need 2+ independent sources
- Judge verifies independently, never trusts debater citations

## Agent Isolation / Agent 隔离

| Agent | Read | Write |
|---|---|---|
| Orchestrator | 全部 | 全部 |
| Pro-Debater | evidence_store, claim_ledger, round N-1/* | round_N/pro_turn.json |
| Con-Debater | evidence_store, claim_ledger, round N-1/* | round_N/con_turn.json |
| Neutral-Judge | round_N/pro_turn + con_turn, evidence_store, claim_ledger | round_N/judge_ruling.json |

## Scripts Reference / 脚本引用

| Script | Usage |
|---|---|
| scripts/init-workspace.sh <dir> <topic> <rounds> | 创建 workspace |
| scripts/validate-json.sh <file> <schema_type> | 验证 JSON |
| scripts/hash-snippet.sh <text> | SHA-256 hash |
| scripts/append-audit.sh <audit_file> <json_line> | 原子追加 JSONL |

## Bilingual / 双语

All documents and outputs include both Chinese and English.
```

---

# Section 17: README.md Template
# 第十七章：README.md 模板

Use this as the `README.md` for the new project:

```markdown
# Critical Debater v2

Multi-agent adversarial debate system with real-time evidence verification, per-round evidence refresh, and structured bilingual report output.

## Features

- **4-Agent Architecture**: Pro, Con, Judge (independent verification), Orchestrator
- **Per-Round Evidence Refresh**: Each round searches for new evidence driven by judge feedback
- **Parallel Pro/Con**: Both sides argue independently each round — no information asymmetry
- **5-Element Reasoning Chains**: Every argument requires observed facts, mechanism, scenario, triggers, falsification
- **10-Dimension Conclusion Profiles**: Probability, confidence, consensus, evidence coverage, reversibility, validity window, impact, causal clarity, actionability, falsifiability
- **Bilingual Reports**: Full English + Chinese Markdown reports
- **Agent Skills Compatible**: Works with Claude Code, GPT/OpenClaw, Codex, skills.sh

## Quick Start

    debate "Should central banks adopt digital currencies?" --rounds 3 --depth standard

## Architecture

SubAgent pattern with file-based state machine. Orchestrator dispatches Pro/Con/Judge through sequential rounds with JSON file communication.

    Phase 1: Init → SourceIngest(broad) → FreshnessCheck
    Phase 2: Per round: [Evidence Refresh] → Pro || Con → Judge → ClaimLedger
    Phase 3: FinalSynthesis → debate_report.md

## Output

- `reports/final_report.json` — Structured JSON with all conclusions
- `reports/debate_report.md` — Bilingual Markdown report

## Spec

Full system specification: [docs/critical-debater-v2-spec.md](docs/critical-debater-v2-spec.md)

## License

MIT-0
```

---

# End of Specification
# 规范文档结束

This document is self-contained. A new Claude Code session reading ONLY this file has everything needed to build the complete Critical Debater v2 system.
此文档自包含。新 Claude Code 会话只读此文件即可构建完整的 Critical Debater v2 系统。
