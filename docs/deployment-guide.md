# Critical Debater v3 — 项目介绍与部署运行指南 / Overview & Deployment Guide

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-08-30 | Claude | 初始创建：项目特点与部署运行指南 / Initial creation: features + deployment guide |

---

## 一、项目简介 / Introduction

**Critical Debater v3** 是一个多 Agent 对抗式辩论系统：给定一个辩题，正方（Pro）与反方（Con）并行多轮辩论，中立法官（Judge）对每条论点独立验证并裁定，编排器（Orchestrator）通过 **LangGraph 状态图**管理全流程——每轮按裁判反馈刷新证据、强制必答点闭环、对全部证据做确定性可信度评分，最终产出双语（中英）结构化报告与八维质量评估。

**Critical Debater v3** is a multi-agent adversarial debate system: given a topic, Pro and Con argue in parallel rounds, a neutral Judge independently verifies every claim, and the orchestrator — a **LangGraph state graph** — manages the full lifecycle: per-round evidence refresh driven by judge feedback, mandatory-response closure, deterministic credibility scoring of all evidence, and a bilingual structured report with an eight-dimension quality assessment.

v3 相比 v2（纯 Claude Code/Codex CLI 技能套件，保留于 `critical-debater-suite/`，完全兼容）完成了七阶段重构：LangGraph 架构迁移、多模型接入、中文信源适配、证据可信度优化、质量评估体系、Web 界面与集成测试。

---

## 二、架构总览 / Architecture

```
                        ┌────────────────────────────────────────┐
                        │  Web UI (React 18 + TS + MUI + RTK)    │
                        │  配置/进度/证据/轮次/质量/报告 6 模块      │
                        └───────────────▲────────────────────────┘
                     静态挂载 (SPA)     │ REST + WebSocket 实时事件
                        ┌───────────────┴────────────────────────┐
                        │  FastAPI  (src/critical_debater/api/)  │
                        │  后台线程运行辩论 · mtime 守卫事件流        │
                        └───────────────▲────────────────────────┘
                                invoke  │
                        ┌───────────────┴────────────────────────┐
                        │  LangGraph 状态图 (17 节点)              │
                        │  init → 证据门(重试环) → 每轮刷新 →       │
                        │  [正方 ∥ 反方] → 裁判 → 账本/评分/图谱 →   │
                        │  (轮次循环) → 综合 → 报告门 → 质量评估     │
                        └───────────────▲────────────────────────┘
                                dispatch│ AgentRunner (context 协议)
          ┌─────────────────────────────┼──────────────────────────────┐
          │ API 模型层 (Phase 2)         │ CLI 模型层 (Phase 1)          │ 搜索层
          │ OpenAICompatProvider        │ claude -p / codex exec       │ Tavily
          │ (DeepSeek/Kimi/GLM/Qwen/    │ (v2 原生运行时, 仍可用)        │ Bocha(博查)
          │  OpenAI/Ollama/vLLM)        │                              │ Null(诚实降级)
          │ AnthropicProvider           │                              │
          └─────────────────────────────┴──────────────────────────────┘
```

| 目录 / Directory | 职责 / Responsibility |
|---|---|
| `src/critical_debater/graph/` | LangGraph 状态图：`state.py`(DebateState)、`nodes.py`(17 节点)、`builder.py`(条件边/扇出)、`runner.py`(入口) |
| `src/critical_debater/models/` | 模型抽象层：`provider.py`(LLM Provider)、`api_runner.py`(进程内执行能力步骤)、`cli.py`(CLI runner)、`search.py`(搜索后端)、`registry.py`(配置/角色路由/传输选择) |
| `src/critical_debater/evidence/` | 证据系统：`merge.py`(合并去重)、`chinese.py`(中文信源)、`credibility.py`(五维评分+动态权重)、`relations.py`(关系图谱) |
| `src/critical_debater/claims/` | 论点账本一致性门(裁判裁定 ↔ 账本状态) |
| `src/critical_debater/synthesis/` | 最终综合：确定性双语渲染器 fallback |
| `src/critical_debater/quality/` | 八维质量评估 + 双语报告 + 自包含 SVG 仪表盘 |
| `src/critical_debater/api/` | FastAPI 后端：REST + WebSocket |
| `frontend/` | React 前端(Vite 构建，产物由后端挂载) |
| `config/` | `models.yaml`(模型/角色路由/搜索)、`chinese_sources.yaml`、`credibility_rules.yaml`、`quality_rules.yaml` |
| `critical-debater-suite/` | v2 技能套件(9 个 capability 文档 + bash 脚本)，v3 复用其能力指令与渲染器 |
| `tests/` | 119 个 pytest 用例(单元/图结构/全链路/API 集成) |

---

## 三、核心特点 / Key Features

### 1. LangGraph 图编排 / Graph orchestration
- 17 节点覆盖完整生命周期；条件边驱动证据门重试环与轮次循环；Pro/Con 在同一 superstep 内真正并行 fan-out
- 严格保留 v2 行为：能力提示词、步骤 ID、模型层级、重试次数、审计事件、`failed_*` 失败状态逐一对应，两代编排器可操作同一工作空间

### 2. 多模型接入 / Multi-model access
- **一个类覆盖大多数厂商**：`OpenAICompatProvider` 通吃 DeepSeek / Kimi / 智谱 GLM / 通义 Qwen / OpenAI / 本地 Ollama 与 vLLM(同为 OpenAI Chat Completions 协议);`AnthropicProvider` 覆盖 Claude
- **角色路由**：裁判可与辩手使用不同厂商(如 DeepSeek 辩、Anthropic 裁)
- **API key 只走环境变量**，配置文件仅存变量名；4xx 不重试、5xx/超时指数退避；JSON 输出稳健提取 + 一次修复重试

### 3. 中文信源适配 / Chinese source adaptation
- 中文辩题自动进入中文模式：中文多角度查询 + 1 条英文交叉验证查询；**权威站点限定搜索**(`site:gov.cn`/新华社/人民网)保证覆盖，语义优先由 LLM 掌握措辞
- 博查(Bocha)中文搜索后端；域名分级注册表(gov.cn→tier1、知乎/公众号→tier3、微博→tier4)**确定性覆盖** LLM 分级；每条证据标注 `source_language`

### 4. 证据可信度优化 / Evidence credibility (Phase 4)
- 五维加权评分：权威性 30% / 交叉验证 25% / 内容质量 20% / 时效性 15% / 透明度 10%,全程确定性计算
- 动态权重：红队模式、社媒占比过高、过期事实占比高、后期轮次 scrutiny 均触发调整并归一化
- 交叉验证接入裁判裁定(verified 加分/contested 减分)与同域复本稀释；**reasoning 轨证据永不衰减**
- 证据关系图谱：复本/同域/共引/支持/矛盾五类边

### 5. 八维质量评估 / Quality assessment (Phase 5)
- 证据质量、推理深度、论点多样性、反驳有效性(含必答点履行率)、裁判严谨性、交叉验证率、辩论平衡性、结论可靠性——每维 0-1 分 + 子分 + 双语注记
- 产出双语 `quality_report.md`、机器可读 `quality_metrics.json`、零依赖自包含 `quality_dashboard.html`(内联 SVG 雷达图)

### 6. Web 界面 / Web UI (Phase 6)
- 6 个模块：辩题配置 → 实时进度(Stepper + WebSocket 审计事件流)→ 证据浏览器 → 轮次视图 → 质量雷达 → 最终报告
- FastAPI 单进程同时提供 API 与 SPA;原生 WebSocket + 指数退避重连

### 7. 工程质量 / Engineering
- 119 个 pytest 用例，含 API 层全链路集成测试(HTTP + WebSocket + SPA 挂载)
- v3 流水线零 bash/jq 依赖(校验/审计/初始化均为纯 Python 移植)；图表/仪表盘零外部资源

---

## 四、环境要求 / Requirements

| 依赖 / Dependency | 版本 / Version | 用途 / Purpose |
|---|---|---|
| Python | ≥ 3.10 | 后端全部逻辑 |
| Node.js + npm | ≥ 18(建议 20+) | 仅构建前端时需要 |
| 可选:claude 或 codex CLI | — | 仅 `runtime=cli` 传输需要 |
| 网络 | — | 调用模型 API / 搜索 API |

Python 依赖(`pip install -e .` 自动安装):`langgraph`、`pyyaml`、`fastapi`、`uvicorn[standard]`。

---

## 五、部署与运行 / Deployment & Running

### 步骤 1:安装 / Install

```bash
git clone https://github.com/yufish-gaga/critical-debater.git
cd critical-debater

# 常规安装 / regular install
pip install -e .
# 开发(含 pytest)/ dev
pip install -e ".[dev]"
```

### 步骤 2:配置模型与搜索 / Configure models & search

编辑 `config/models.yaml`(或用环境变量 `CRITICAL_DEBATER_MODELS_CONFIG` 指向自定义文件)，核心字段：

```yaml
runtime: auto          # api | cli | auto(auto:有 key 走 API,否则找 claude/codex CLI)
role_models:           # 角色路由:每类角色用哪个厂商哪个层级
  judge: {provider: deepseek, tier: deep}
search:
  provider: tavily     # tavily | bocha | none(none 时证据门会诚实失败)
  api_key_env: TAVILY_API_KEY
```

然后导出密钥(只放环境变量，不要写进任何文件)：

```bash
export DEEPSEEK_API_KEY=sk-...        # 模型(按 role_models 实际引用的厂商配置)
# export ANTHROPIC_API_KEY=sk-ant-... # 若裁判/辩手指定了 anthropic
export TAVILY_API_KEY=tvly-...        # 搜索(或改用 bocha: export BOCHA_API_KEY=...)
```

### 步骤 3(方式 A):Web 界面运行 / Run with Web UI(推荐)

```bash
# 1. 构建前端(一次性)/ build the frontend once
cd frontend && npm install && npm run build && cd ..

# 2. 单进程启动 API + UI / serve API + UI in one process
PYTHONPATH=src uvicorn critical_debater.api.app:create_app --factory --port 8000
# 或 / or: PYTHONPATH=src python -m critical_debater.api [已有工作空间路径]

# 3. 浏览器打开 / open
#    http://127.0.0.1:8000
```

在「配置 / Setup」页输入辩题、轮数、深度、模式、语言后点击开始；「进度」页实时展示阶段与审计事件流；辩论完成后在「质量」「报告」页查看评估与双语报告。

开发模式(前端热更新)：终端 1 启动后端(`--port 8000`),终端 2 `cd frontend && npm run dev`,访问 `http://localhost:5173`(Vite 已代理 `/api` 与 `/ws`)。

### 步骤 3(方式 B):命令行运行 / Run via CLI

```bash
# 直接给辩题(自动初始化工作空间)/ topic only (workspace auto-created)
PYTHONPATH=src python -m critical_debater /tmp/my-debate "中国应如何平衡经济增长与碳排放目标" 3

# 或给 config.json(已有工作空间)/ or an existing workspace config
PYTHONPATH=src python -m critical_debater /tmp/my-debate /tmp/my-debate/config.json
```

### 步骤 3(方式 C):纯 API 调用 / API only

```bash
# 启动
curl -X POST http://127.0.0.1:8000/api/debates \
  -H "Content-Type: application/json" \
  -d '{"topic":"Should AGI development be slowed?","rounds":2,"mode":"balanced"}'
# → {"debate_id":"...","workspace":"...","status":"running"}

# 轮询状态 / poll
curl http://127.0.0.1:8000/api/debates/<debate_id>

# 读取工件 / artifacts(evidence_store / claim_ledger / quality_metrics /
# evidence_credibility / evidence_graph / round_1_pro_turn / final_report ...)
curl http://127.0.0.1:8000/api/debates/<debate_id>/artifacts/quality_metrics

# 实时事件 / live events
websocat ws://127.0.0.1:8000/ws/<debate_id>
```

### 传输层切换 / Transport selection

| 场景 / Scenario | 配置 / Setting |
|---|---|
| 有任意厂商 API key | 自动走 API 层(默认) |
| 强制 API / 强制 CLI | `CRITICAL_DEBATER_RUNTIME=api` 或 `cli` |
| 用 claude/codex CLI(v2 方式) | 卸载密钥后 `runtime: auto` 会自动回落;或 `DEBATER_RUNTIME=claude|codex` |

---

## 六、产出物 / Artifacts

每场辩论产生一个自包含工作空间：

| 路径 / Path | 内容 / Content |
|---|---|
| `config.json` | 辩论配置与实时状态(`initialized → in_progress → round_N_complete → complete` / `failed_*`) |
| `evidence/evidence_store.json` | 全部证据(含可信度分级、语言、来源、发现轮次) |
| `evidence/evidence_credibility.json` | 五维可信度评分明细 + 本轮动态权重 |
| `evidence/evidence_graph.json` | 证据关系图谱(复本/同域/共引/支持/矛盾) |
| `claims/claim_ledger.json` | 论点账本(状态机:unverified/verified/contested/stale) |
| `rounds/round_N/{pro,con}_turn.json` | 每轮双方论点、驳论、必答响应 |
| `rounds/round_N/judge_ruling.json` | 裁判裁定(验证结果/因果标记/必答点) |
| `reports/final_report.json` | 结构化最终报告(验证事实/争议点/情景展望/结论画像) |
| `reports/debate_report.md` | 双语 Markdown 报告(Section 8 格式校验) |
| `reports/quality_metrics.json` | 八维质量评估(机器可读) |
| `reports/quality_report.md` | 双语质量报告 |
| `reports/quality_dashboard.html` | 质量仪表盘(浏览器直接打开) |
| `logs/audit_trail.jsonl` | 全程审计(JSONL,幂等去重) |

---

## 七、测试 / Tests

```bash
pytest                        # 119 个用例:单元 + 图结构 + 全链路 + API 集成
pytest tests/test_api_integration.py -v   # 仅集成测试
cd frontend && npm run build  # 前端类型检查 + 构建
```

集成测试覆盖：HTTP 全链路(启动→轮询→工件→报告→404)、WebSocket 事件流(快照→审计→终态)、SPA 挂载与路由 fallback。测试使用脚本化 FakeProvider/FakeSearch,不产生任何真实 API 调用。

---

## 八、生产部署建议 / Production notes

- **进程**:`uvicorn critical_debater.api.app:create_app --factory --host 0.0.0.0 --port 8000`;前端构建产物随应用挂载，无需独立静态服务；如需多 worker,注意每 worker 的辩论线程相互独立、状态以工作空间文件为准(天然兼容)
- **反向代理**：置于 nginx/caddy 之后时，为 `/ws` 路径开启 WebSocket 升级(`proxy_set_header Upgrade/Connection`),并放宽 `proxy_read_timeout`
- **密钥管理**：密钥只经环境变量注入(systemd `EnvironmentFile` / Docker `--env-file` / K8s Secret),`config/models.yaml` 与镜像中永不落盘
- **辩论运行目录**:`DebateService(runs_root=...)` 控制 Web 启动的辩论工作空间位置；CLI 模式由调用方指定；建议挂载持久卷
- **成本控制**:`role_models` 可让裁判用更强(更贵)模型、辩手用经济模型;`rounds` 与 `depth` 直接决定调用量;`search.provider: none` 可完全关闭搜索费用(但证据门会因无证据而终止)
- **监控**:`logs/audit_trail.jsonl` 是结构化事件流，可直接对接日志采集;`/api/debates` 返回全部在途辩论状态

---

## 九、常见问题 / Troubleshooting

| 现象 / Symptom | 原因与处理 / Cause & fix |
|---|---|
| `No agent runtime found` | 无 API key 且无 claude/codex CLI:配置 `DEEPSEEK_API_KEY` 等,或安装 CLI |
| `provider '...' has no API key` | `role_models` 引用的厂商缺环境变量，按其 `api_key_env` 导出 |
| `insufficient_evidence` 失败 | 搜索后端未配置(`search.provider: none`)或搜索 key 无效——配置 Tavily/Bocha 后重试 |
| 辩论卡在 `failed_round_N` | 查看 `logs/audit_trail.jsonl` 的 `step_failed` 条目与 `config.json` 状态;CLI 模式下多为超时，可在 config 调大 `step_timeout_sec` |
| Web 界面空白 | `frontend/dist` 不存在：先执行 `cd frontend && npm install && npm run build` |
| WebSocket 无法连接 | 反向代理未放行 `/ws` 升级头，或直接访问了前端 dev 端口而后端未启动 |
| 中文辩题仍搜到英文源 | 确认 `config/chinese_sources.yaml` 存在且站点限定搜索未被禁用;辩题需含中文或 `language: zh` |

---

*文档版本 / Doc version: 1.0 · 对应代码 / code: v3.0.0 Phase 1-7 (`c3c451a`) · 2026-08-30*
