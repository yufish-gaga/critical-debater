# Critical Debater v2

**Multi-agent adversarial debate system with real-time evidence verification.**
**多 Agent 对抗式辩论系统，实时证据验证。**

A structured 4-agent debate framework: Pro and Con argue in parallel, a neutral Judge independently verifies every claim, and an Orchestrator manages the lifecycle. Every argument requires a 5-element reasoning chain; every conclusion is profiled across 10 dimensions. Output is a bilingual (English + Chinese) Markdown report backed by verified evidence.

一个结构化的 4-Agent 辩论框架：正方和反方并行辩论，中立法官独立验证每个论点，编排器管理全流程。每个论点需要 5 要素推理链；每个结论经 10 维度画像。输出为双语（英文+中文）Markdown 报告，由经验证的证据支撑。

---

## Features / 特性

| Feature / 特性 | Description / 描述 |
|---|---|
| **4-Agent Architecture** | Pro, Con, Judge (independent verification), Orchestrator |
| **4-Agent 架构** | 正方、反方、法官（独立验证）、编排器 |
| **Parallel Pro/Con** | Both sides argue independently — no information asymmetry |
| **并行正反方** | 双方独立论述——无信息不对称 |
| **Per-Round Evidence Refresh** | Each round searches for new evidence driven by judge feedback |
| **每轮证据刷新** | 每轮根据法官反馈搜索新证据 |
| **5-Element Reasoning Chains** | observed_facts → mechanism → scenario_implication → trigger_conditions → falsification_conditions |
| **5 要素推理链** | 观察事实 → 机制 → 情景推演 → 触发条件 → 可证伪条件 |
| **10-Dimension Conclusion Profiles** | Probability, confidence, consensus, evidence coverage, reversibility, validity window, impact, causal clarity, actionability, falsifiability |
| **10 维度结论画像** | 概率、置信度、共识度、证据覆盖、可逆性、有效窗口、影响量级、因果清晰度、可操作性、可证伪性 |
| **Bilingual Reports** | Full English + Chinese Markdown reports |
| **双语报告** | 完整的英文 + 中文 Markdown 报告 |
| **Agent Skills Compatible** | Works with Claude Code, skills.sh, and other Agent Skills runtimes |
| **Agent Skills 兼容** | 兼容 Claude Code、skills.sh 及其他 Agent Skills 运行时 |

---

## Complete System Flow / 完整系统流程

```
PHASE 1: INITIALIZATION / 初始化阶段
══════════════════════════════════════════════════
  User provides: topic, rounds (default 3), options
  用户输入: 辩题、轮次（默认 3）、选项
         │
         ▼
  init-workspace.sh → creates directory structure + empty JSONs
  init-workspace.sh → 创建目录结构 + 空 JSON 文件
         │
         ▼
  SourceIngest(broad, round=0) — 3~8 diverse search queries
  源采集（广泛搜索，round=0）— 3~8 个多样化搜索查询
         │
         ▼
  FreshnessCheck — classify fact vs reasoning track
  新鲜度检查 — 分类事实轨道 vs 推理轨道
         │
         ▼
  config.json: status = "evidence_gathered"


PHASE 2: DEBATE ROUNDS (for each round N = 1..R) / 辩论轮次
══════════════════════════════════════════════════

  Step 2a: PER-ROUND EVIDENCE REFRESH / 每轮证据刷新
  ─────────────────────────────────────────────
  Read judge_ruling from round N-1:
    → mandatory_response_points → search gaps
    → causal_validity_flags → weak evidence areas
  读取上轮法官裁定 → 生成聚焦搜索查询 → 采集新证据

  Step 2b: PARALLEL PRO + CON / 并行正反方
  ─────────────────────────────────────
  ┌─────────────────────────┐  ┌─────────────────────────┐
  │      PRO-DEBATER        │  │      CON-DEBATER        │
  │      正方辩手            │  │      反方辩手            │
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
  Step 2c: VALIDATE OUTPUTS / 验证输出
  ─────────────────────────
  validate-json.sh pro_turn.json + con_turn.json
  Deep check: 5-element reasoning chain per argument

  Step 2d: JUDGE AUDIT / 法官审计
  ────────────────────
  Judge independently verifies claims via search
  法官通过独立搜索验证论点
  Writes: judge_ruling.json (verification_results, mandatory_response_points)

  Step 2e: POST-ROUND PROCESSING / 轮后处理
  ──────────────────────────────
  Extract claims → update claim_ledger
  Merge new_evidence from both turns → evidence_store
  Audit log + config update


PHASE 3: FINAL OUTPUT / 最终输出
══════════════════════════════════════════════════
  FinalSynthesis:
    → verified_facts, probable_conclusions, contested_points
    → scenario_outlook + watchlist_24h
    → conclusion_profiles (10 dimensions)
    → decision_matrix
    → reports/final_report.json + reports/debate_report.md
```

---

## Quick Start / 快速开始

### Via Claude Code / 通过 Claude Code

```
debate "Should central banks adopt digital currencies?" --rounds 3 --depth standard
```

### Via Python Orchestrator / 通过 Python 编排器

```bash
# Initialize workspace / 初始化工作空间
bash scripts/init-workspace.sh ./debates/cbdc "Should central banks adopt digital currencies?" 3

# Run orchestrator / 运行编排器
python3 scripts/debate_orchestrator_generic.py ./debates/cbdc "Should central banks adopt digital currencies?" 3
```

### Red Team Mode / 红队模式

```
red team this: "Our company should migrate all services to Kubernetes"
```

In red team mode, Con = Red Team (identifies risks), Pro = Blue Team (proposes mitigations).
红队模式中，反方 = 红队（识别风险），正方 = 蓝队（提出缓解措施）。

---

## Configuration / 配置

The `config.json` in each workspace controls debate behavior:

每个工作空间的 `config.json` 控制辩论行为：

| Field / 字段 | Type / 类型 | Description / 描述 |
|---|---|---|
| `topic` | string | The debate topic / 辩题 |
| `round_count` | int | Number of debate rounds (default: 3) / 辩论轮数 |
| `depth` | `quick \| standard \| deep` | Controls search breadth and argument rigor / 控制搜索广度和论证严格度 |
| `mode` | `balanced \| red_team` | Debate mode / 辩论模式 |
| `evidence_refresh` | `upfront_only \| per_round \| hybrid` | When to search for new evidence / 何时搜索新证据 |
| `language` | `en \| zh \| bilingual` | Output language / 输出语言 |
| `domain` | string | Topic domain (geopolitics, tech, health, finance, etc.) / 话题领域 |
| `speculation_level` | `conservative \| moderate \| exploratory` | How far to extrapolate / 推测程度 |
| `output_format` | `full_report \| executive_summary \| decision_matrix` | Report format / 报告格式 |
| `focus_areas` | string[] | User-defined dimensions to focus on / 用户定义的关注维度 |

### Depth Levels / 深度级别

| Depth / 深度 | Search Queries / 搜索查询 | Min Evidence / 最少证据 | Min Args / 最少论点 |
|---|---|---|---|
| `quick` | 3 | 5 | 2 |
| `standard` | 5 | 10 | 2 |
| `deep` | 8 | 15 | 3 |

---

## Outputs / 产出物

### Workspace Structure / 工作空间结构

```
workspace/
├── config.json              # Debate configuration / 辩论配置
├── evidence/
│   └── evidence_store.json  # All evidence items / 所有证据项
├── claims/
│   └── claim_ledger.json    # All claims with status / 所有论点及状态
├── rounds/
│   ├── round_1/
│   │   ├── pro_turn.json    # Pro's arguments / 正方论述
│   │   ├── con_turn.json    # Con's arguments / 反方论述
│   │   └── judge_ruling.json # Judge's ruling / 法官裁定
│   ├── round_2/
│   │   └── ...
│   └── round_3/
│       └── ...
├── reports/
│   ├── final_report.json    # Structured JSON report / 结构化 JSON 报告
│   └── debate_report.md     # Bilingual Markdown report / 双语 Markdown 报告
└── logs/
    └── audit_trail.jsonl    # Full audit trail / 完整审计日志
```

### Final Report Contents / 最终报告内容

The `final_report.json` includes:

| Section / 章节 | Description / 描述 |
|---|---|
| `executive_summary` | One-paragraph summary + top facts/points / 执行摘要 |
| `verified_facts` | Cross-source confirmed factual statements / 交叉验证的事实 |
| `probable_conclusions` | High-confidence conclusions with qualifiers / 高置信度结论 |
| `contested_points` | Points where Pro/Con disagree, with judge assessment / 争议焦点 |
| `decision_matrix` | Factor-by-factor comparison / 因素逐一对比 |
| `scenario_outlook` | Base case + upside/downside triggers / 基准情景 + 上行/下行触发 |
| `watchlist_24h` | What to monitor + reversal triggers / 24h 观察清单 |
| `conclusion_profiles` | 10-dimension profile per conclusion / 每个结论的 10 维画像 |
| `speculative_frontier` | Forward-looking scenarios / 前瞻性情景推演 |
| `historical_insights` | Key parallels + conflicting lessons / 历史洞察 |

### The Bilingual Report / 双语报告

`debate_report.md` is a human-readable Markdown document containing:

- Executive Summary (EN/ZH) / 执行摘要
- Verified Facts table / 已验证事实表
- Contested Points with pro/con positions / 争议焦点
- Decision Matrix table / 决策矩阵表
- Scenario Outlook / 情景展望
- 24h Watchlist / 24h 观察清单
- Evidence Inventory / 证据清单
- Conclusion Profiles (10 dimensions) / 结论画像

---

## Evidence System / 证据系统

### Two Evidence Tracks / 双轨证据

| Track / 轨道 | Description / 描述 | Freshness / 新鲜度 |
|---|---|---|
| **Fact** | Current-state claims, statistics, recent events / 时效性事实 | Can become `stale` / 可能过期 |
| **Reasoning** | Mechanisms, trends, historical patterns / 机制、趋势、历史规律 | Always `timeless` / 永不过期 |

### Credibility Tiers / 可信度分级

| Tier / 层级 | Sources / 来源 |
|---|---|
| `tier1_authoritative` | Government agencies, central banks, AP, Reuters |
| `tier2_reputable` | Major newspapers, research institutions, peer-reviewed journals |
| `tier3_general` | Blogs, industry reports, company press releases |
| `tier4_social` | Twitter/X, Reddit, forums |

### Claim Status State Machine / 论点状态机

```
unverified → verified       (judge confirms with evidence)
unverified → contested      (opposing side challenges)
verified   → contested      (new counter-evidence found)
contested  → verified       (resolution through evidence)
contested  → stale          (evidence expired, not renewed)
verified   → stale          (supporting evidence expired)
stale      → verified       (refreshed with current evidence)
stale      → contested      (refreshed but disputed)
```

---

## Agent Isolation / Agent 隔离

Each agent has strict read/write boundaries to prevent information leakage:

每个 Agent 有严格的读写边界以防止信息泄露：

| Agent | Reads / 可读 | Writes / 可写 |
|---|---|---|
| **Orchestrator** | All files / 全部 | All files / 全部 |
| **Pro-Debater** | evidence_store, claim_ledger, round N-1/* | round_N/pro_turn.json |
| **Con-Debater** | evidence_store, claim_ledger, round N-1/* | round_N/con_turn.json |
| **Neutral-Judge** | round_N/pro_turn + con_turn, evidence_store, claim_ledger | round_N/judge_ruling.json |

**Critical rule**: Pro and Con NEVER see each other's current round arguments.
**关键规则**：正反方永远看不到对方当前轮次的论述。

---

## 9 Capabilities / 9 项能力

| Capability / 能力 | File / 文件 | Description / 描述 |
|---|---|---|
| Debate Orchestration | `capabilities/debate.md` | Full lifecycle orchestration / 全生命周期编排 |
| Source Ingest | `capabilities/source-ingest.md` | Broad/focused evidence search / 广泛/聚焦证据搜索 |
| Freshness Check | `capabilities/freshness-check.md` | Fact vs reasoning track classification / 事实 vs 推理轨道分类 |
| Evidence Verify | `capabilities/evidence-verify.md` | Optional cross-source verification / 可选交叉验证 |
| Debate Turn | `capabilities/debate-turn.md` | Argument construction with reasoning chains / 含推理链的论点构建 |
| Judge Audit | `capabilities/judge-audit.md` | Independent verification + ruling / 独立验证 + 裁定 |
| Claim Ledger Update | `capabilities/claim-ledger-update.md` | Claim state machine transitions / 论点状态机转换 |
| Analogy Safeguard | `capabilities/analogy-safeguard.md` | Historical analogy validation / 历史类比验证 |
| Final Synthesis | `capabilities/final-synthesis.md` | Report generation with 10-dim profiles / 含 10 维画像的报告生成 |

---

## Scripts / 脚本

| Script / 脚本 | Usage / 用法 |
|---|---|
| `scripts/init-workspace.sh <dir> <topic> <rounds>` | Create workspace structure / 创建工作空间 |
| `scripts/validate-json.sh <file> <schema_type>` | Validate JSON against data contracts / 验证 JSON 数据合约 |
| `scripts/hash-snippet.sh <text>` | SHA-256 hash of evidence snippet / 证据摘要哈希 |
| `scripts/append-audit.sh <audit_file> <json_line>` | Atomic append to audit trail / 原子追加审计日志 |
| `scripts/debate_orchestrator_generic.py <workspace> <topic> [rounds]` | Python orchestrator / Python 编排器 |

---

## Installation / 安装

### Via skills.sh

```bash
npx skills add xwxga/critical-debater
```

### Manual / 手动

Clone and use directly with Claude Code:

```bash
git clone https://github.com/xwxga/critical-debater.git
cd critical-debater
# The skill is in critical-debater-suite/
```

### Requirements / 依赖

- `bash`, `jq`, `python3`, `shasum`
- Internet access for web search evidence gathering
- An agent runtime: Claude Code, Codex, or other Agent Skills-compatible runtime

---

## Examples / 示例

### Standard Debate / 标准辩论

```
debate "Will AI replace most white-collar jobs by 2030?" --rounds 3 --depth standard
```

### Deep Analysis / 深度分析

```
debate "Should the Federal Reserve raise interest rates?" --rounds 5 --depth deep
```

### Chinese Topic / 中文辩题

```
辩论 "央行是否应该采用数字货币" --rounds 3 --depth standard
```

### Multi-Perspective Analysis / 多视角分析

```
analyze from multiple perspectives: should we adopt microservices?
```

---

## Design Spec / 设计规范

Full system specification (17 sections, 1400+ lines): [docs/critical-debater-v2-spec.md](docs/critical-debater-v2-spec.md)

完整系统规范（17 章节，1400+ 行）：[docs/critical-debater-v2-spec.md](docs/critical-debater-v2-spec.md)

---

## License

MIT-0
