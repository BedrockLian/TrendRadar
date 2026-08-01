# Codex 计划任务入口

`src/trendradar/config/plan.json` 是任务时间、描述、入口和预算的唯一来源。

这些脚本只做本地计算、检查和产物写入，stdout 输出一个 JSON 对象。Codex 计划任务读取该对象；日报、周报和月报必须把最终 Markdown 本体直接输出到当前聊天框，不以本地预览或产物路径替代正文。

| 入口 | 用途 |
|---|---|
| `health_check.py` | 每日体检运行目录、数据库、配置和最近结果 |
| `maintenance.py` | 清理运行缓存、压缩历史记录并执行轻量维护 |
| `output_watchdog.py` | 检查指定日报时段是否按时产生产物 |

运行前设置 `TRENDRADAR_HOME` 可把运行数据放到独立目录；未设置时，仓库内运行默认使用 `.runtime/`。
