# TrendRadar

TrendRadar 是一个多源 RSS 聚合、分类、精选、翻译和 Markdown 简报系统。脚本生成可审计的 JSON/Markdown 产物，Codex 读取结果并将最终 Markdown 直接输出到聊天框，不调用外部消息平台。

## 快速开始

```text
python -m pip install -e ".[dev]"
python -m trendradar.pipeline.pipeline_orchestrator --check-version
python ops/codex/health_check.py
python ops/codex/source_audit.py --live --format markdown
python -m trendradar.pipeline.pipeline_orchestrator --push-id morning --output json
```

本地运行默认把数据写入 `.runtime/`；部署时可设置 `TRENDRADAR_HOME` 指向独立运行目录。Python 基线为 3.14.5，日报全链路预算为 180 秒。

## 计划任务

唯一时间表在 [`src/trendradar/config/plan.json`](src/trendradar/config/plan.json)，其中同时记录任务描述、入口、时区和预算。

日报在 09:00、12:00、21:00；看门狗在 09:10、12:10、21:10；体检每日 15:00；维护每日 03:00；周报周一 09:30；月报每月 1 日 09:00。

## 目录

- `src/trendradar/`：Python 包、配置、迁移和业务脚本。
- `tests/`：单元测试和集成烟雾测试。
- `docs/`：架构、管线、运维和陷阱文档。
- `ops/codex/`：体检、维护、看门狗和安装入口。
- `skills/trendradar/`：面向 Codex 的薄 Skill 入口。
- `.runtime/`：本地运行数据，不进入 Git。

更多内容见 [`SETUP.md`](SETUP.md) 和 [`docs/INDEX.md`](docs/INDEX.md)。
