---
name: self-healing
slug: self-healing
version: 3.3.0
description: 自动体检 TrendRadar 各组件：DB/配置/API/Gateway/记忆。修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)。有异常推送 WeCom，健康静默。

## 检查项（18项）

详见 `references/health-check-design.md`。

核心检查：DB (WAL + Storage 统一接入) → 脚本 (21个) → 配置 → Cron → Gateway → API → 数据时效 → 盲点审计 → 拦截器 → 全链路 → 记忆 → 进程。

## 7 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `90a2866775df` | 日报推送 | LLM |
| `718b663e8c04` | 性能优化器 | LLM |
| `cab79825520e` | 推送看门狗 | no_agent |
| `68db70cd8556` | 每日维护 | no_agent |
| `c987a2883174` | 自动体检 | no_agent |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 硬编码这些 ID。

## 常见故障

详见 `references/health-check-pitfalls.md` 和 `references/traps.md`。

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/traps.md` | 陷阱全集 |
| `references/health-check-design.md` | 体检设计：检查项表 + cron ID 表 |
| `references/health-check-pitfalls.md` | 维护陷阱 |
| `references/api-diagnosis.md` | DeepSeek 断流 & WeCom WS 抖动 |
| `references/import-architecture.md` | 导入架构修复 |
| `references/migration-mechanism.md` | 迁移引擎架构 |
| `references/migration-rollback.md` | 迁移回滚约定 |
