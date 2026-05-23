# 优化参数表

> 性能维度已移除(Script阶段15s ≪ 30s目标)

## 质量参数

| 参数 | 文件 | 范围 | 步长 |
|------|------|------|------|
| `MIN_SCORE` | curate_and_push.py | 5-8 | ±1 |
| `MAX_PER_DOMAIN['top_headlines']` | curate_and_push.py | 8-15 | ±2 |
| `MAX_PER_DOMAIN['tech']` | curate_and_push.py | 12-22 | ±2 |
| blog recency 保底 | curate_and_push.py `_score()` | 1-3 | ±1 |

## 推送参数

| 参数 | 文件 | 范围 | 步长 |
|------|------|------|------|
| `MAX_PER_DOMAIN` | curate_and_push.py | ±3 | +1/-1 |
| `_kw()` 关键词集 | curate_and_push.py | — | ±5词 |
| slot 时间 | cron job | 06:00-23:00 | ±1h |
