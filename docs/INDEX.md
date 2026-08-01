# TrendRadar 参考文档

这里是唯一的运行和设计文档入口。Skill 只引用这里，不复制操作手册。

| 文档 | 用途 |
|---|---|
| `ARCHITECTURE.md` | 模块边界、依赖方向和运行时布局 |
| `PIPELINE.md` | 日报数据流、JSON 协议和 180 秒预算 |
| `OPERATIONS.md` | Codex 计划、体检、维护和看门狗 |
| `RSS_SOURCE_SCORECARD.md` | RSS 来源替代方案、三维评分和实时评判表 |
| `TRAPS.md` | 当前仍有效的风险与处理方式 |

机器可读的时间表是 `../src/trendradar/config/plan.json`；来源评分规则是 `../src/trendradar/config/source_evaluation.json`；生成实时来源表使用 `python ops/codex/source_audit.py --live --format markdown`；生成任务提示使用 `python -m trendradar.cli.gen_cron_prompt`。
