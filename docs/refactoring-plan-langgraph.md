# Critical Debater v3.0 重构方案

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-08-30 | Claude | 封装 v3 技能库：`critical-debater-v3-suite/`（core 规范 + 生成式 SKILL.md/三平台适配层 + 能力文档复制 + check-install），`paths.py` 支持多套件发现与渲染器回退，142 测试 / v3 skill suite packaged |
| 2026-08-30 | Claude | v3.1 加固（提前落地 Phase 8 安全项）：API Token 鉴权中间件 + WS `?token=`、工作空间围栏（403）、`POST /cancel` 协作式取消（AgentRunner 接缝步骤间终止）、断点恢复（`--resume`/`resume:true`，config 检查点→resume_router 入口路由），修复 sync_status 终态复活竞态，133 测试 / v3.1 security + resume |
| 2026-08-30 | Claude | Phase 6-7 完成：FastAPI 后端（REST + WebSocket 实时事件流）+ React 18/TS/MUI/Redux Toolkit/Recharts 前端（6 模块，Vite 构建，SPA 由后端挂载），集成测试 119 个 / Phase 6-7 frontend + integration done |
| 2026-08-30 | Claude | Phase 5 完成质量评估体系：`DebateQualityAssessor` 8 维确定性评分（等权可配 `config/quality_rules.yaml`），双语 `quality_report.md` + 自包含 SVG 仪表盘 `quality_dashboard.html`（零依赖零外部资源）/ Phase 5 quality assessment done |
| 2026-08-30 | Claude | Phase 4 完成证据可信度优化：`EvidenceCredibilityScorer` 五维加权评分（权威30%/时效15%/交叉验证25%/内容20%/透明10%），`config/credibility_rules.yaml` 规则外置，语境动态权重调整（红队/社媒占比/过期占比/后期轮次），证据关系图谱（复本/同域/共引/矛盾边），post_round 落盘 + final_synthesis 注入 / Phase 4 evidence credibility done |
| 2026-08-30 | Claude | Phase 3 完成中文信源适配：`config/chinese_sources.yaml` 域名分级注册表（gov.cn/新华社/人民网→tier1），`ChineseQueryOptimizer` 权威站点限定搜索，Bocha 中文搜索后端，证据 `source_language` 标注与可信度确定性覆盖 / Phase 3 Chinese source adaptation done |
| 2026-08-30 | Claude | Phase 2 完成多模型接入：`OpenAICompatProvider` 一类覆盖 DeepSeek/Kimi/GLM/Qwen/OpenAI/Ollama，`AnthropicProvider`，`LLMAgentRunner` 进程内执行能力步骤，Tavily 可插拔搜索，`config/models.yaml` 角色路由 / Phase 2 multi-model access done |
| 2026-08-30 | Claude | Phase 1 完成核心架构迁移：LangGraph 状态图落地于 `src/critical_debater/`，17 节点 + 条件边 + Pro/Con fan-out，4-agent 逻辑与 v2 工作空间/审计完全兼容 / Phase 1 core migration done: LangGraph state graph in `src/critical_debater/` |
| 2026-08-30 | Claude | 初始创建 / Initial creation |

## 📋 文档信息

| 项目 | 内容 |
|---|---|
| **版本** | v3.0.0-plan |
| **创建日期** | 2026-08-30 |
| **状态** | Phase 1-7 已完成；Phase 8（生产部署/监控）进行中 |
| **目标框架** | LangGraph |

---

## 🎯 重构目标

### 核心目标

1. **框架迁移**
   - 从自定义编排系统迁移到 LangGraph 框架
   - 利用 LangGraph 的状态管理和图编排能力
   - 保持现有 4-agent 辩论逻辑不变

2. **多模型支持**
   - 支持多家 LLM 提供商（OpenAI, Anthropic, 本地模型等）
   - 统一模型接入接口
   - 模型配置动态切换

3. **中文信源适配**
   - 优化中文搜索查询生成
   - 支持中文证据来源（百度、微信公众号、知乎等）
   - 中文证据可信度评估体系

4. **证据可信度优化**
   - 引入证据加权算法
   - 多维度可信度评分
   - 动态权重调整机制

5. **交互式前端**
   - Web UI 界面
   - 实时辩论进度展示
   - 交互式证据浏览

6. **辩论质量评估**
   - 自动化质量评分体系
   - 多维度质量指标
   - 辩论过程可视化分析

---

## 🏗️ 架构设计

### LangGraph 状态图设计

```
                        [START]
                           │
                           ▼
                  ┌──────────────────┐
                  │ InitializeDebate │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  SourceIngest    │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ FreshnessCheck   │
                  └────────┬─────────┘
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
    ┌──────────────────┐        ┌──────────────────┐
    │  PerRoundIngest  │        │   DebateRound    │
    └────────┬─────────┘        └────────┬─────────┘
             │                           │
             └─────────────┬─────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  ParallelDebate  │
                  └────────┬─────────┘
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
    ┌──────────────┐            ┌──────────────┐
    │  ProDebater  │            │  ConDebater  │
    └──────┬───────┘            └──────┬───────┘
           │                           │
           └─────────────┬─────────────┘
                         │
                         ▼
                ┌──────────────────┐
                │   JudgeAudit     │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
           ┌────│  RoundComplete?  │
           │    └────────┬─────────┘
           │             │ No
           │             ▼
           │    ┌──────────────────┐
           └───►│  NextRound       │
                └────────┬─────────┘
                         │ Yes
                         ▼
                ┌──────────────────┐
                │ FinalSynthesis   │
                └────────┬─────────┘
                         │
                         ▼
                ┌──────────────────┐
                │ QualityAssessment│
                └────────┬─────────┘
                         │
                         ▼
                      [END]
```

### LangGraph 状态定义

```python
from typing import TypedDict, List, Dict, Annotated
from langgraph.graph import add_messages

class DebateState(TypedDict):
    """辩论状态"""
    
    # 基础配置
    topic: str
    rounds: int
    current_round: int
    depth: str
    mode: str
    language: str
    
    # 证据系统
    evidence_store: List[Dict]
    evidence_weights: Dict[str, float]  # NEW: 证据权重
    
    # 声明系统
    claim_ledger: List[Dict]
    
    # 辩论轮次数据
    pro_arguments: Annotated[List[Dict], add_messages]
    con_arguments: Annotated[List[Dict], add_messages]
    judge_rulings: List[Dict]
    
    # 模型配置
    pro_model: str
    con_model: str
    judge_model: str
    model_provider: str  # NEW
    
    # 质量评估
    quality_metrics: Dict  # NEW
    
    # 工作空间
    workspace_path: str
    status: str
```

---

## 🔌 多模型接入架构

### 模型抽象层设计

```python
from abc import ABC, abstractmethod

class BaseLLMProvider(ABC):
    """LLM 提供商基类"""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass
    
    @abstractmethod
    def generate_structured(self, prompt: str, schema: Dict) -> Dict:
        pass

class OpenAIProvider(BaseLLMProvider):
    """OpenAI 提供商"""
    pass

class AnthropicProvider(BaseLLMProvider):
    """Anthropic 提供商"""
    pass

class LocalModelProvider(BaseLLMProvider):
    """本地模型提供商"""
    pass
```

---

## 🇨🇳 中文信源适配

### 中文搜索源配置

支持的中文信源包括：

- **百度搜索** (tier2_reputable)
- **微信公众号** (tier3_general)
- **知乎** (tier3_general)
- **中国政府网** (tier1_authoritative)
- **新华社** (tier1_authoritative)
- **人民网** (tier1_authoritative)

### 中文查询优化

```python
class ChineseQueryOptimizer:
    """中文搜索查询优化器"""
    
    def generate_chinese_queries(self, topic: str, depth: str) -> List[str]:
        """生成中文优化搜索查询"""
        pass
```

---

## ⚖️ 证据可信度加权算法

### 多维度评分体系

```python
class EvidenceCredibilityScorer:
    """证据可信度评分器"""
    
    def calculate_credibility_score(self, evidence: Dict) -> float:
        """
        计算综合可信度分数 (0-1)
        
        评分维度:
        1. 来源权威性 (30%)
        2. 时效性 (15%)
        3. 交叉验证 (25%)
        4. 内容质量 (20%)
        5. 透明度 (10%)
        """
        pass
```

---

## 🖥️ 交互式前端设计

### 技术栈

- **前端框架**: React 18 + TypeScript
- **UI 库**: Material-UI (MUI)
- **状态管理**: Redux Toolkit
- **实时通信**: WebSocket (Socket.IO)
- **可视化**: D3.js + Recharts

### 主要界面模块

1. **辩题配置面板** - 输入辩题和参数
2. **实时进度监控** - 展示当前阶段和进度
3. **证据浏览器** - 证据列表、详情、关系图
4. **辩论轮次视图** - 正反方论点和裁判裁定
5. **最终报告展示** - Markdown 渲染和导出
6. **质量评估仪表盘** - 多维度质量指标

---

## 📊 辩论质量自动评估体系

### 质量评估维度

```python
class DebateQualityAssessor:
    """辩论质量评估器"""
    
    def assess_debate_quality(self, debate_data: Dict) -> Dict:
        """
        评估维度:
        1. 证据质量
        2. 推理深度
        3. 论点多样性
        4. 反驳有效性
        5. 裁判严谨性
        6. 交叉验证率
        7. 辩论平衡性
        8. 结论可靠性
        """
        pass
```

---

## 📁 项目结构

```
critical-debater-v3/
├── src/
│   ├── core/                    # 核心业务逻辑
│   │   ├── graph/               # LangGraph 状态图
│   │   ├── models/              # 模型抽象层
│   │   ├── evidence/            # 证据系统
│   │   ├── agents/              # Agent 实现
│   │   ├── quality/             # 质量评估
│   │   └── synthesis/           # 最终综合
│   ├── api/                     # FastAPI 后端
│   │   ├── routers/
│   │   ├── websocket/
│   │   └── schemas/
│   ├── frontend/                # React 前端
│   │   └── src/
│   │       ├── components/
│   │       ├── pages/
│   │       └── store/
│   └── utils/                   # 工具函数
├── config/                      # 配置文件
│   ├── models.yaml
│   ├── chinese_sources.yaml
│   └── credibility_rules.yaml
├── scripts/                     # 脚本工具
├── tests/                       # 测试
├── docker/                      # Docker 配置
└── docs/                        # 文档
```

---

## 🚀 实施路线图

### Phase 1: 核心架构迁移 (Week 1-2) ✅ 已完成 / DONE
- 搭建 LangGraph 基础架构 → `pyproject.toml` + `src/critical_debater/`（包结构见下方实现映射）
- 实现状态定义和基本节点 → `graph/state.py`（DebateState）+ `graph/nodes.py`（17 节点）+ `graph/builder.py`
- 迁移现有 4-agent 逻辑 → 保留 CLI 派发（`AgentRunner` 协议 + claude/codex runner），提示词/步骤 ID/重试/审计/失败状态与 v2 逐一对齐；`graph/runner.py` 为入口

**实现映射 / Implementation notes**：
- 图结构：`START → initialize → source_ingest → freshness → evidence_gate（重试环）→ round_entry（条件：per_round refresh）→ debate_prep → [pro_debater ∥ con_debater] → post_turns → judge_audit → post_round →（条件：round loop / final）→ final_synthesis → report_gate → quality_assessment → END`
- `pro_arguments` / `con_arguments` / `judge_rulings` 使用 append-only reducer（`operator.add`）保证并行分支不互相覆盖
- 校验、审计追加（含幂等去重）、workspace 初始化由 bash/jq 移植为纯 Python（`validation.py` / `workspace.py`），v3 流水线不再依赖 jq
- `config/models.yaml` 外置模型层级映射，`registry.py` 支持环境变量覆盖
- 测试：34 个 pytest 用例（图结构、双轮快乐路径、证据门重试环、失败路径、fallback 渲染、单元）

### Phase 2: 多模型接入 (Week 3-4)
- 实现模型抽象层
- 集成 OpenAI、Anthropic、本地模型
- 模型配置系统

### Phase 2: 多模型接入 (Week 3-4) ✅ 已完成 / DONE
- 实现模型抽象层 → `models/provider.py`：`OpenAICompatProvider`（一个类覆盖 DeepSeek / Kimi / GLM / Qwen / OpenAI / 本地 Ollama/vLLM——同为 OpenAI Chat Completions 协议，仅 base_url/key/model 不同）+ `AnthropicProvider`（Claude Messages API）；stdlib `urllib` 传输，零新增依赖；4xx 不重试、5xx/超时指数退避重试
- 集成多厂商 + 本地模型 → 内置 DeepSeek/Kimi/智谱/OpenAI/Anthropic/Ollama 预设；API key 走环境变量（配置文件只存 `api_key_env` 名，绝不落盘）
- 模型配置系统 → `config/models.yaml`：`providers` + `role_models` 角色路由（裁判可与辩手用不同厂商）+ `search` 搜索后端 + `runtime: api|cli|auto`；`AgentRunner` dispatch 增加 `context` 结构化参数
- 能力执行层 → `models/api_runner.py` `LLMAgentRunner`：注入能力指令 + 工作区上下文（证据库/论点账本/上轮工件），JSON 输出契约 + 工件落盘；`final_synthesis` 走 LLM 生成 `final_report.json` + 确定性渲染器产出双语 `debate_report.md`
- 可插拔搜索 → `models/search.py`：Tavily 实现 + Null 降级（无搜索时证据门诚实失败，不让模型编造信源）；Phase 3 中文信源复用同一协议
- 测试：77 个 pytest 用例（新增 provider/搜索/注册表/API runner 各步 + API 全链路 e2e）

### Phase 3: 中文信源适配 (Week 5-6)
- 中文搜索查询优化器
- 集成中文搜索源
- 中文证据提取和评估

### Phase 3: 中文信源适配 (Week 5-6) ✅ 已完成 / DONE
- 中文搜索查询优化器 → `evidence/chinese.py` `ChineseQueryOptimizer`：LLM 保持查询措辞的语义优先权（中文多角度查询 + 1 条英文交叉验证查询），优化器确定性补充**权威站点限定搜索**（`site:gov.cn` / 新华社 / 人民网），保证中文辩题不会只依赖英文或自媒体信源
- 集成中文搜索源 → `models/search.py` 新增 `BochaSearchProvider`（博查中文搜索 API，`BOCHA_API_KEY`）；Tavily 原生支持 `include_domains` 站点限定，Bocha 以 `site:` 操作符实现；`search.provider: tavily | bocha | none`
- 中文证据提取和评估 → `config/chinese_sources.yaml` 域名分级注册表：gov.cn/新华社/人民网/央视 → tier1_authoritative，财新/澎湃/一财 → tier2_reputable，知乎/微信公众号/百家号 → tier3_general，微博/贴吧 → tier4_social；ingest 后对已知中文域名做**确定性可信度覆盖**（LLM 分级错误也会被纠正）；新增 `source_language` 字段（zh/en）标注证据语言；中文模式下的提取提示词注入中文媒体可信度口径
- 触发条件：辩题含中文，或 `language: zh`；英文辩题行为完全不变
- 测试：93 个 pytest 用例（新增中文注册表分级/后缀安全匹配/语言检测/查询优化器/Bocha 请求与映射/中文 ingest 链路）

### Phase 4: 证据可信度优化 (Week 7-8)
- 多维度评分体系
- 动态权重调整算法
- 证据关系图谱

### Phase 4: 证据可信度优化 (Week 7-8) ✅ 已完成 / DONE
- 多维度评分体系 → `evidence/credibility.py` `EvidenceCredibilityScorer`：计划口径五维加权 —— 来源权威性 30%（tier 基础分 + 信源类型增减 + 中文注册表锚定）、时效性 15%（时间带衰减；**reasoning 轨/timeless 永不衰减**——契约关键规则）、交叉验证 25%（corroboration 状态 + 裁判论点裁定 verified 加分/contested 减分 + 同域复本稀释）、内容质量 20%（摘录信息量 + 元数据 + 社媒旗标）、透明度 10%（url/发布方/日期披露）；全部确定性计算，零 LLM 调用
- 动态权重调整算法 → `adjust_weights`：规则化语境调整 —— red_team 模式强化交叉验证、社交信源占比 >40% 双重提防、过期事实占比 >30% 提升时效权重、第 3 轮起裁判 scrutiny 收紧；调整后归一化到 1.0；规则外置于 `config/credibility_rules.yaml`（环境变量 `CRITICAL_CREDIBILITY_RULES_CONFIG` 可覆盖）
- 证据关系图谱 → `evidence/relations.py`：节点（证据 + 论点）与五类边 —— `duplicate_of`（同 URL/同哈希）、`same_domain`（同域聚类，带每节点边数上限）、`co_cited`（同claim共引，权重=共引次数）、`supports`（论点引用）、`contradicts`（裁判 conflict_details 矛盾对）；落盘 `evidence/evidence_graph.json` 含统计摘要
- 图接入：`post_round` 每轮评分 + 图谱落盘，`state.evidence_weights`（计划 DebateState 字段）携带 evidence_id→分数；`final_synthesis` 提示词注入 `credibility_score` 并约束低可信度社媒证据不得锚定结论；质量基线新增 credibility 均值与 source_language 分布
- 测试：107 个 pytest 用例（新增五维边界/权重归一化与调整触发/图谱五类边/工作区集成）

### Phase 5: 质量评估体系 (Week 9-10)
- 8 维度质量评估
- 质量报告生成
- 可视化图表

### Phase 5: 质量评估体系 (Week 9-10) ✅ 已完成 / DONE
- 8 维度质量评估 → `quality/assessor.py` `DebateQualityAssessor`：证据质量（Phase 4 可信度均分 + tier 结构）、推理深度（推理链五要素完整率 + 每轮论点量对 depth 门槛 + 情景/历史引用）、论点多样性（claim_type 覆盖 / 引用域名广度 / 双方引用重叠度）、反驳有效性（针对性反驳占比 + **上轮必答点 MRP 履行率**）、裁判严谨性（论点裁定覆盖率 + 裁定附理由率 + 因果标记轮次占比）、交叉验证率（verified 论点 + corroborated 证据）、辩论平衡性（正反论点数与发现证据对称度）、结论可靠性（verified facts 锚定 + 结论画像可证伪/有效窗口完整率 + 争议点状态标注）；全部确定性 0-1 分 + 子分 + 双语注记
- 质量报告生成 → `quality/report.py`：`reports/quality_report.md`（综合得分档位判定 优秀/良好/中等/薄弱 + 八维表 + 各维度要点 + 基础统计，全双语）；`reports/quality_metrics.json` 为机器可读完整报告
- 可视化图表 → `quality/charts.py`：**零依赖自包含 HTML 仪表盘** `reports/quality_dashboard.html` —— 8 维雷达图（内联 SVG，含 0.25/0.5/0.75/1.0 参考环与顶点标注）+ 可信度分级/论点状态分布条形图，无外部 JS/CSS 资源
- 权重外置 → `config/quality_rules.yaml`（`dimension_weights`，默认等权 0.125，自动归一化）
- 测试：115 个 pytest 用例（新增八维结构/推理链退化/平衡性/MRP 履行/可信度联动/结论画像/权重覆盖/工件渲染）

### Phase 6: 交互式前端 (Week 11-14)
- React 项目初始化
- 主要界面模块实现
- WebSocket 集成

### Phase 7: 系统集成和测试 (Week 15-16)
- 端到端测试
- 性能优化
- 文档完善

### Phase 6: 交互式前端 (Week 11-14) ✅ 已完成 / DONE
- 后端 API → `src/critical_debater/api/`：FastAPI（计划指定）——`POST /api/debates`（后台线程运行 LangGraph 图）、`GET /api/debates/{id}`（状态+当前轮）、`/artifacts/{name}`（证据库/论点账本/质量报告/轮次工件，含 `round_N_pro_turn` 动态名）、`/report`；**WS `/ws/{id}`**：快照 + mtime 轮询的审计事件流/状态事件流（async，终态自动收尾）
- React 项目 → `frontend/`（Vite + React 18 + TypeScript 严格模式 + **MUI** + **Redux Toolkit** 状态管理 + **Recharts** 可视化；D3 未单独引入——Recharts 基于 D3 已覆盖需求）
- 主要界面模块 → 计划 6 模块全部实现：辩题配置面板 / 实时进度监控（Stepper + WS 审计事件流）/ 证据浏览器（分级筛选 + 可信度分 + 语言标注）/ 辩论轮次视图（正反论点 + 驳论 + 裁判裁定）/ 质量仪表盘（Recharts 8 维雷达 + 维度表）/ 最终报告展示
- WebSocket 集成 → 原生 WebSocket（计划括注 Socket.IO——原生 WS 前后端均零额外依赖，协议可平滑替换）；断线指数退避重连，终态自动收尾
- 构建产物由 FastAPI 挂载为 SPA（`create_app(frontend_dist=...)`，客户端路由 fallback 到 index.html）；dev 模式 Vite 代理 /api + /ws

### Phase 7: 系统集成和测试 (Week 15-16) ✅ 已完成 / DONE
- 端到端测试 → `tests/test_api_integration.py`：HTTP 全链路（启动→状态轮询→工件检索→报告读取→404 语义）、WS 事件流（快照→审计事件→终态收尾）、既有工作空间复用、SPA 静态挂载；加上真实 uvicorn + 已构建前端的端口冒烟验证；总计 119 个 pytest 用例
- 性能优化 → WS feed 采用 mtime 守卫轮询（空闲时零解析开销、无 inotify 依赖）；工件端点按需读取文件
- 文档完善 → README（Phase 6/7 使用说明）、计划文档（本节）、api/__main__ 入口
- 说明：浏览器级 E2E（Playwright）未纳入测试套件——需要浏览器运行时，当前以 API 层集成测试 + 构建验证 + 真实端口冒烟覆盖

### Phase 8: 上线和优化 (Week 17+) — 进行中 / IN PROGRESS
- ✅ API 安全边界(v3.1 提前落地)：Token 鉴权(CRITICAL_DEBATER_API_TOKEN,HTTP 头 + WS 查询参数,常量时间比较)、工作空间围栏(realpath + commonpath,根外 403)、协作式取消(CancellableRunner 在 AgentRunner 接缝按步骤终止,config 置 `cancelled`)
- ✅ 断点恢复(v3.1 提前落地)：`map_resume_entry` 将 config 检查点映射到 `resume_router` 入口(fresh/rounds/final),CLI `--resume`、API `resume:true`;修复 sync_status 将旧终态复活进新 run 的竞态
- 待办 / TODO: 监控与日志采集对接、Docker/K8s 部署模板、前端代码分割与浏览器级 E2E
- 生产环境部署
- 监控和日志
- 持续优化

---

## 🔧 技术依赖

### Python 后端

```
langgraph>=0.1.0
langchain>=0.1.0
openai>=1.0.0
anthropic>=0.20.0
fastapi>=0.110.0
websockets>=12.0
jieba>=0.42.1
```

### 前端依赖

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "@mui/material": "^5.15.0",
    "@reduxjs/toolkit": "^2.0.0",
    "socket.io-client": "^4.6.0",
    "recharts": "^2.10.0",
    "d3": "^7.8.0"
  }
}
```

---

## ⚠️ 风险和挑战

1. **LangGraph 迁移风险** - 学习曲线，影响开发效率
2. **多模型兼容性** - 不同模型输出格式差异
3. **中文信源质量** - 可信度评估难度大
4. **前端复杂度** - 实时交互和可视化实现复杂
5. **性能和成本** - 多模型调用成本高

---

## 📚 参考资源

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [OpenAI API](https://platform.openai.com/docs)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [React 文档](https://react.dev/)
- [Material-UI](https://mui.com/)

---

**文档版本**: v3.0.0-plan  
**最后更新**: 2026-08-30
