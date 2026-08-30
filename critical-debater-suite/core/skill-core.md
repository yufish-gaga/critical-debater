# Critical Debater Skill Core Spec

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-03-13 17:40 | Codex | 新增平台无关 Core 规范，供多平台适配层生成 / Add platform-agnostic core spec for multi-platform adapter generation |

## Purpose / 目标

Build a multi-agent adversarial debate workflow with strict evidence handling, judge re-verification, and bilingual final reporting.
构建多 Agent 对抗式辩论流程，要求严格证据处理、法官独立复核、双语最终报告。

## Trigger Intents / 触发意图

- debate / start a debate / red team this / analyze from multiple perspectives
- final report / synthesis
- source ingest / freshness check / judge round

## Inputs / 输入

- topic
- rounds (default 3)
- depth (quick / standard / deep)
- mode (balanced / red_team)
- workspace path

## Required Outputs / 必需输出

- `reports/final_report.json` (schema-valid)
- `reports/debate_report.md` (must match Section 8 format exactly)
- `logs/audit_trail.jsonl` with step-level events

## Capability Routing / 能力路由

- `capabilities/debate.md`
- `capabilities/source-ingest.md`
- `capabilities/freshness-check.md`
- `capabilities/evidence-verify.md`
- `capabilities/debate-turn.md`
- `capabilities/judge-audit.md`
- `capabilities/claim-ledger-update.md`
- `capabilities/analogy-safeguard.md`
- `capabilities/final-synthesis.md`

## Safety Boundaries / 安全边界

- No path traversal (`../`) outside configured root.
- Report completion must be blocked on validation failures.
- Judge does independent verification and does not trust debater citations alone.

## Completion Contract / 完成契约

Only emit `DONE:final_synthesis` after:
1. `final_report.json` schema validation passes.
2. `debate_report.md` Section 8 format validation passes.
3. Files are atomically finalized.
