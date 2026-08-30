# Critical Debater v3.0 重构方案

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-08-30 | Claude | Phase 1 完成核心架构迁移：LangGraph 状态图落地于 `src/critical_debater/`，17 节点 + 条件边 + Pro/Con fan-out，4-agent 逻辑与 v2 工作空间/审计完全兼容 / Phase 1 core migration done: LangGraph state graph in `src/critical_debater/` |
| 2026-08-30 | Claude | 初始创建 / Initial creation |

## 📋 文档信息

| 项目 | 内容 |
|---|---|
| **版本** | v3.0.0-plan |
| **创建日期** | 2026-08-30 |
| **状态** | Phase 1 已完成（核心架构迁移）；Phase 2+ 规划中 |
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

### Phase 3: 中文信源适配 (Week 5-6)
- 中文搜索查询优化器
- 集成中文搜索源
- 中文证据提取和评估

### Phase 4: 证据可信度优化 (Week 7-8)
- 多维度评分体系
- 动态权重调整算法
- 证据关系图谱

### Phase 5: 质量评估体系 (Week 9-10)
- 8 维度质量评估
- 质量报告生成
- 可视化图表

### Phase 6: 交互式前端 (Week 11-14)
- React 项目初始化
- 主要界面模块实现
- WebSocket 集成

### Phase 7: 系统集成和测试 (Week 15-16)
- 端到端测试
- 性能优化
- 文档完善

### Phase 8: 上线和优化 (Week 17+)
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
