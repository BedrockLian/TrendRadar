---
name: system-config
slug: system-config
version: 4.0.0
description: 管理 TrendRadar 的路径、Python 环境、配置和 Codex 计划清单。
metadata:
  tags: [trendradar, config, runtime, performance]
---

## 单一事实来源

- 运行路径：`src/trendradar/runtime/paths.py`。
- 计划、描述和时间：`src/trendradar/config/plan.json`。
- 配置：`src/trendradar/config/`。
- 运维入口：`ops/codex/`。
- 运行数据：未设置 `TRENDRADAR_HOME` 时为仓库 `.runtime/`。

不要在脚本、Skill 或计划提示中复制路径、时间表和输出字段；引用上述文件即可。

## Python 基线

使用 Python 3.14.5。安装项目依赖后，从仓库根目录执行：

```text
python -m trendradar.pipeline.pipeline_orchestrator --check-version
python -m pytest tests -q
```

日报总预算为 180 秒，结果中的 `stats.budget` 是验收依据。

## 参考

`../../../docs/INDEX.md`、`ARCHITECTURE.md`、`OPERATIONS.md`、`TRAPS.md`。
