# Critical Debater

**多 Agent 对抗式辩论系统 / Multi-agent adversarial debate system**

给定一个辩题,正方与反方并行多轮辩论,中立法官对每条论点独立验证,LangGraph 状态图编排全流程。每条论点要求五要素推理链,每条证据经过确定性可信度评分,最终输出双语报告与八维质量评估。

## 特性

- **LangGraph 编排**:17 节点状态图,条件边驱动证据门重试环与轮次循环,正反方并行辩论
- **多模型接入**:一个兼容层通吃 DeepSeek / Kimi / GLM / Qwen / OpenAI / Anthropic / 本地 Ollama;裁判与辩手可用不同厂商;API key 只走环境变量
- **中文信源适配**:中文辩题自动切换中文查询与权威站点限定搜索(gov.cn / 新华社 / 人民网),域名分级注册表确定性校正可信度
- **证据可信度评分**:权威性 30% / 交叉验证 25% / 内容质量 20% / 时效性 15% / 透明度 10%,红队模式等语境动态调权;证据关系图谱
- **八维质量评估**:证据质量、推理深度、多样性、反驳有效性、裁判严谨性、交叉验证率、平衡性、结论可靠性,产出双语报告与可视化仪表盘
- **Web 界面**:React + MUI,实时进度(WebSocket)、证据浏览、轮次视图、质量雷达、报告展示
- **安全与恢复**:API Token 鉴权、工作空间路径围栏、辩论取消、基于检查点的断点续跑

## 快速开始

```bash
git clone https://github.com/yufish-gaga/critical-debater.git
cd critical-debater
pip install -e .
```

配置 API key(在 `config/secrets.yaml` 中直接填写,该文件已被 gitignore;详见 `config/models.yaml`):

```bash
cp config/secrets.example.yaml config/secrets.yaml
# 编辑 config/secrets.yaml:
#   providers: { deepseek: { api_key: "sk-..." } }
#   search:    { tavily:   { api_key: "tvly-..." } }
# 或用环境变量: export DEEPSEEK_API_KEY=sk-...
```

### 命令行辩论

```bash
PYTHONPATH=src python -m critical_debater /tmp/my-debate "中国应如何平衡经济增长与碳排放目标" 3

# 中断后续跑
PYTHONPATH=src python -m critical_debater /tmp/my-debate "辩题" 3 --resume
```

### Web 界面

```bash
cd frontend && npm install && npm run build && cd ..
PYTHONPATH=src uvicorn critical_debater.api.app:create_app --factory --port 8000
# 打开 http://127.0.0.1:8000
```

### 纯 API

```bash
curl -X POST http://127.0.0.1:8000/api/debates \
  -H "Content-Type: application/json" \
  -d '{"topic":"Should AGI development be slowed?","rounds":2}'
# 轮询 /api/debates/{id},实时事件 ws://.../ws/{id},工件 /api/debates/{id}/artifacts/{name}
```

## 产出物

每场辩论生成一个自包含工作空间:

| 路径 | 内容 |
|---|---|
| `reports/debate_report.md` | 双语最终报告 |
| `reports/final_report.json` | 结构化报告(验证事实/争议点/情景展望/结论画像) |
| `reports/quality_report.md` / `quality_dashboard.html` | 八维质量评估与仪表盘 |
| `evidence/evidence_store.json` | 全部证据(可信度分级/语言/交叉验证状态) |
| `evidence/evidence_credibility.json` / `evidence_graph.json` | 可信度评分明细与关系图谱 |
| `claims/claim_ledger.json` | 论点账本(verified / contested / unverified / stale) |
| `rounds/round_N/` | 每轮正反方论点与裁判裁定 |
| `logs/audit_trail.jsonl` | 全程审计事件 |

## 技能库

系统同时封装为可安装的 Agent 技能:[critical-debater-v3-suite/](critical-debater-v3-suite/SKILL.md)(含 Claude Code / Codex / OpenClaw 适配层、辩论方法论能力文档、安装校验脚本)。

```bash
bash critical-debater-v3-suite/scripts/check-install.sh   # 安装校验
```

## 测试

```bash
pip install -e ".[dev]"
pytest            # 142 个用例:单元 / 图结构 / 全链路 / API 集成 / 技能库
```

## 文档

- [部署运行指南](docs/deployment-guide.md) — 配置详解、三种运行方式、生产部署与故障排查
- [重构方案](docs/refactoring-plan-langgraph.md) — 架构设计与实施记录
- [原版技能套件](critical-debater-suite/) — 纯 Agent Skills 运行时的实现(兼容保留)

## License

MIT-0
