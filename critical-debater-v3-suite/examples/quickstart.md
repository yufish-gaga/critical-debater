# Quickstart / 快速上手

## Changelog / 变更日志

| 时间 / Time | 作者 / Author | 变更 / Change |
|---|---|---|
| 2026-08-30 | Claude | 初始创建 / Initial creation |

完整说明见 [../../docs/deployment-guide.md](../../docs/deployment-guide.md)。

## 1. 安装 / Install

```bash
git clone https://github.com/yufish-gaga/critical-debater.git
cd critical-debater
pip install -e .
bash critical-debater-v3-suite/scripts/check-install.sh   # 验证 / verify
```

## 2. 配置密钥 / Configure keys

```bash
export DEEPSEEK_API_KEY=sk-...      # 或 / or: OPENAI_API_KEY / ANTHROPIC_API_KEY / MOONSHOT_API_KEY ...
export TAVILY_API_KEY=tvly-...      # 可选搜索 / optional search (或 BOCHA_API_KEY)
```

## 3a. 命令行辩论 / CLI debate

```bash
PYTHONPATH=src python -m critical_debater /tmp/my-debate "中国应如何平衡经济增长与碳排放目标" 3
# 中断后续跑 / resume after interruption:
PYTHONPATH=src python -m critical_debater /tmp/my-debate "辩题" 3 --resume
```

## 3b. Web 界面 / Web UI

```bash
cd frontend && npm install && npm run build && cd ..
PYTHONPATH=src uvicorn critical_debater.api.app:create_app --factory --port 8000
# 打开 / open http://127.0.0.1:8000
```

## 4. 查看结果 / Results

| 文件 / File | 内容 / Content |
|---|---|
| `reports/debate_report.md` | 双语最终报告 / bilingual report |
| `reports/quality_report.md` | 八维质量报告 / quality report |
| `reports/quality_dashboard.html` | 可视化仪表盘 / dashboard |
| `logs/audit_trail.jsonl` | 全程审计 / audit trail |
