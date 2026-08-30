# Critical Debater v2 — Project Instructions

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-03-12 | Claude | Review 修复: 补全 Changelog/Semantic/Hardcoded 规则 / Review fix: add missing rules |
| 2026-03-12 | Claude | 初始创建 / Initial creation |

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

## Document Changelog Rule / 文档变更日志规则

Every time you update a document file (`.md`, design docs, etc.), add a changelog entry at the **top of the file** (after the title).
每次更新文档文件时，在文件顶部添加变更日志条目。

- Same-day updates: precision to **minute** (e.g. `2026-03-12 15:30`)
- Cross-day updates: precision to **day** (e.g. `2026-03-13`)
- Newest entries first. Never remove old entries.

## Semantic First / 语义优先

When generating intermediate artifacts (subtitles, summaries, segments, etc.), ALWAYS use natural semantic understanding first — then apply constraints.
生成中间产物时先用语义理解，再施加约束。

- NEVER use mechanical numeric rules (e.g. "5-15 words per entry") to split/merge/chunk text.
- ALWAYS let LLM understand full meaning first, then break at natural boundaries.
- Numeric limits are soft guidelines for LLM, not hard rules for code.

## No Hardcoded Examples / 不要硬编码特例

Never put session-specific values into prompts or code as hardcoded examples. Write generic instructions that let LLM use context to figure it out.
不把当前会话特有值硬编码到 prompt/code 中。写通用指令让 LLM 根据上下文自行判断。

## Bilingual / 双语

All documents and outputs include both Chinese and English.
