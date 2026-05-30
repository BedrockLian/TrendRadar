# 性能参数决策记录

最后更新: 2026-05-30（审计修复 §4.4）

## 当前值

| 参数 | 值 | 位置 | 理由 |
|------|-----|------|------|
| `TRANSLATE_BATCH_SIZE` | **5** | `config/translation.py` | DeepSeek batch >5 时只翻摘要不翻标题（已知陷阱，不可改） |
| `TRANSLATE_BATCH_MAX_CONCURRENT` | **6** ↑5 | `config/translation.py` | 配合 batch_size=5 提供并发余量 |
| `TIMEOUT_SEC` (RSS) | **8** ↑6 | `config/fetching.py` | WSL2 代理到外网偶有 5-7s 延迟 |
| `CIRCUIT_BREAKER_THRESHOLD` | **5** ↑3 | `ai_translate.py` | 瞬态 429 不应触发熔断 |
| `TCPConnector.limit_per_host` | **12** ↑8 | `fetch_feeds.py` | 代理连接器所有外部源共享限制 |
| `API_CALL_TIMEOUT` | 60 | `config/fetching.py` | 无需改动（翻译超时已自适应） |
| `FETCH_RETRIES` | 3 | `config/fetching.py` | |
| `API_RETRIES` | 3 | `config/fetching.py` | |
| `API_RETRY_BACKOFF` | 2 | `config/fetching.py` | |

## BATCH_SIZE=5 陷阱

DeepSeek API 在 batch >5 时，模型会翻译摘要但标题保持原文不变（`title_cn == title`）。
这是模型行为 bug，非 prompt 问题。**不可提升 BATCH_SIZE**。

假翻译检测：`if item.get('title_cn') == item.get('title'): item.pop('title_cn', None)`

## 自适应翻译超时

`ai_translate.py:batch_translate()` 超时公式：
```
timeout_seconds = 30 + len(messages) * 3 + (attempt * 15)
```
- 基础 30s + 每消息 3s + 每次重试加 15s
- 替代原来的 `120 + attempt * 30`

## 直连+代理并行抓取

`fetch_feeds.py` 2026-05-29 改为并行：
```
async with (direct_session, proxy_session):
    direct_results, proxy_results = await asyncio.gather(direct_task, proxy_task)
```
预期节约 ~5s/次。
