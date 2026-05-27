---
name: performance-optimizer
slug: performance-optimizer
version: 2.4.0
description: 渐进优化 TrendRadar 日报质量与推送偏好。每日 21:15 自愈式收敛调优。
author: Hermes Agent
tags: [trendradar, quality, push-preference, self-healing]
metadata:
  hermes:
    companion_skills: [news-secretary]
---

## 触发
每天 21:15 cron `718b663e8c04` 自动触发，或手动。

> 性能维度已达目标（脚本阶段 ~7s），不再优化。瓶颈在外网 HTTP，非可优化范围。

## API 故障韧性

优化器依赖 DeepSeek API 读取 curated 数据和计算评分。API 连接错误是已知故障模式（gateway 日志常见 `Connection error` / `RemoteProtocolError`）：

1. **重试** — terminal 命令设合理 timeout，失败后等 5-10s 重试
2. **跳过** — 若连续 3 次 API 调用失败，输出 `API 不可达，跳过本轮` 而非崩溃
3. **交付验证** — 优化报告通过 cron final response auto-delivery 投递。若当天 Gateway 不稳定，优化报告可能不送达——参考 delivery_watchdog.py 的自动补发机制

## 质量协议

**评分** (>85 达标): 空摘要<5%(+15)、重复<3%(+10)、头条命中≥60%(+10)、每板块≥3条(+10)、外媒满14条(+5)、分布均匀(+10)。扣分: 空摘要≥20%(-15)、板块为0(-20)、单源≥50%(-15)（代码层已有硬上限30%/slot）。

**单源集中度**: curate_all() 已有全局 30% 硬上限——任何单源在同一个 slot 占比 >30% 时自动剔除最低分条目。优化报告不需要再建议添加新源来稀释已超标来源（稀释策略已在源码层面通过加新源 + 上限代码解决）。集中度预警(≥40%) 仍应标注以便用户知晓结构性问题。

**杠杆**: MIN_SCORE(5-8,±1)、MAX_PER_DOMAIN(±2)、blog recency(1-3,±1)、关键词(±5词)、白名单(增/删)。详见 `references/ARCHITECTURE.md  # was fix-recipes → architecture`。

**交互**: 评分<85 → 列出扣分项+建议 → 问修哪个(编号/all/跳过)。单参数调整，3轮无改善→收敛，跳过 7 天恢复。

## 推送偏好协议

**基准**: `settings.py` 的 `BRIEFING_RATIO`（早30/午30/晚20）和 `DAILY_LIMIT=80`。5 板块: top_headlines/foreign_china/tech/economy/gaming。

**偏差检测**: 总量±30%→偏差；板块连续多天<3条→饿死；同源连续首位→垄断；单源≥40%→来源集中。饿死检测需同时看来源数，即使数量达标也可能"来源脆弱型饱和"。

**交互**: 列出偏差+选项 → 问"怎么调"。

## 输出规范

1. **直接输出报告**（`sanity_check.py` 自动拦截前缀后缀）。报告标题以 `📊 TrendRadar 优化报告 ·` 开头即可。
2. 两维度都达标→ `[SILENT]`

## "全修"模式

用户回复"全修"时：**全部建议一起执行**，不逐项确认。
使用 `todo` 工具并行推进 4 项，修改后验证语法通过，一次性告知变更汇总。
用户回复编号（如"修1和3"）时：只执行指定的项。

## 已验证修复

详见 `references/ARCHITECTURE.md  # was fix-recipes → architecture`：短摘要扩写、tech 上限调整、tirith 关闭、foreign_china 扩充。

## 参数沿革

| 时间 | BRIEFING_RATIO | MAX_PER_DOMAIN (合计) | 变动原因 |
|------|---------------|----------------------|----------|
| v6.0 | 24/32/24 | 65 | 初始值 |
| v6.1 | 30/30/20 | 30 (6+7+6+6+5) | 推送量偏差 +108%, 用户全修后收紧。新增 per-slot 截断逻辑在 curate_all(), foreign_china 加 10 词 |
| v6.2 | 30/30/20 | 30 (不变) | 虎嗅 slot 占比 40% 触发集中警报。新增 36氪 + 界面新闻稀释，curate_all() 新增全局 30%/slot 来源硬上限，虎嗅 authority 3→2 |

## 参考

| 文件 | 内容 |
|------|------|
| `references/ARCHITECTURE.md  # was fix-recipes → architecture` | 已验证修复脚本和验证命令 |
| `references/PIPELINE.md  # was render-format → pipeline` | 简报格式规范 |
| `references/DELIVERY-WATERMARK.md  # was delivery-failure-patterns → delivery` | 静默投递失败模式识别 + 诊断流程 |
| `references/ARCHITECTURE.md  # was source-diversity → architecture` | 来源集中度问题：三层递进方案（硬上限/稀释/权重） |
