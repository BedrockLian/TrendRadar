# API 指数退避 + 熔断器 — reusable pattern

`ai_translate.py` 的 DeepSeek API 调用使用此模式，适用于所有 LLM API 集成。

## 配置常量

```python
RETRY_BASE_DELAY = 2.0        # 初始等待秒数
RETRY_MAX_DELAY = 30.0        # 上限秒数
RETRY_JITTER = 0.5            # ±50% 随机抖动
RETRY_MAX_ATTEMPTS = 4        # 最多 5 次尝试 (初始 + 4 次重试)
CIRCUIT_BREAKER_THRESHOLD = 3  # 连续 3 个 batch 失败 → 熔断
```

## 退避算法

```
attempt 0: no delay (first try)
attempt 1: base * 2^0 = 2s   ± 50% jitter → 1-3s
attempt 2: base * 2^1 = 4s   ± 50% jitter → 2-6s
attempt 3: base * 2^2 = 8s   ± 50% jitter → 4-12s
attempt 4: base * 2^3 = 16s  ± 50% jitter, capped at 30s → 8-24s
```

每次重试超时递增 30s（stream drop 可能需要更长等待）。

## 熔断器

模块级计数器 `_translate_failures`：
- 每个 batch 成功 → 重置为 0
- 每个 batch 失败 → +1
- 达到 CIRCUIT_BREAKER_THRESHOLD → `circuit_broken()` 返回 True → 跳过所有剩余 batch
- 手动重置：`reset_circuit()`

## 使用模式

```python
# 在 batch 循环中
for batch in batches:
    if circuit_broken():
        skip_remaining()  # 不浪费 API 额度
    try:
        result = await call_api()
        reset_circuit()   # 成功后清零
    except Exception:
        increment_failures()
```

## 适配陷阱

- Jitter 用 `random.random() * 2 - 1` 产生 ±50%，不要用固定的 `* 0.5`
- 模块级计数器在 asyncio 中不需要锁（Python GIL 保护单个 bytecode 操作）
- 熔断阈值应该 = 并发 batch 数（如 5 concurrent → threshold=5），否则 3 个并发失败不会触发
