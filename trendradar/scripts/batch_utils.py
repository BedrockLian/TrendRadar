"""
Batch processing utils — 泛化批次处理支持翻译/扩写/未来 AI 操作复用。

提取自 ai_translate.py 的 _batch_translate_all 与 _batch_expand_all，
消除约 80% 重复代码。
"""
import asyncio
import logging
from typing import Callable, Any

log = logging.getLogger('batch-utils')


async def process_batches(
    session: Any,
    batches: list,
    items_to_process: list,
    batch_func: Callable,
    api_key: str,
    source_lang_field: int = 7,
    max_concurrent: int = 6,
    batch_size: int = 5,
    circuit_broken: Callable = lambda: False,
    circuit_reset: Callable = lambda: None,
    circuit_fail: Callable = lambda: None,
    log_prefix: str = "Batch",
    group_by_lang: bool = True,
) -> list:
    """泛化批次处理 — 翻译/扩写/未来 AI 操作复用。

    Args:
        session: aiohttp ClientSession
        batches: 预分的批次列表，每项 (batch_list, pairs, batch_start, [source_lang])
        items_to_process: 原始 items 列表（用于计算总数）
        batch_func: 异步批处理函数，签名为 (session, pairs, api_key, [lang]) → list
        api_key: API key
        source_lang_field: items 元组中 source_lang 的索引
        max_concurrent: 最大并发批次
        batch_size: 每批大小
        circuit_broken/circuit_reset/circuit_fail: 熔断器回调
        log_prefix: 日志前缀
        group_by_lang: 是否按语言分组

    Returns: list of (batch, results_or_None, error_or_None) tuples
    """
    all_results = []

    async def process_one_batch(batch, pairs, batch_start, source_lang=None):
        try:
            if circuit_broken():
                log.error(
                    f"熔断触发 — 跳过剩余批次")
                return (batch, None, RuntimeError("Circuit breaker open"))

            kwargs = {'session': session, 'items': pairs, 'api_key': api_key}
            if source_lang and group_by_lang:
                kwargs['source_lang'] = source_lang
            results = await batch_func(**kwargs)

            batch_end = batch_start + len(batch)
            total = len(items_to_process)
            log.info(
                f"{log_prefix} {batch_start+1}-{batch_end}/{total}: "
                f"processed {len(batch)} items")
            circuit_reset()
            return (batch, results, None)
        except Exception as e:
            circuit_fail()
            log.error(
                f"{log_prefix} failed: {e}")
            return (batch, None, e)

    # If only one batch, no semaphore overhead
    if len(batches) == 1:
        result = await process_one_batch(*batches[0])
        all_results.append(result)
        return all_results

    # Multiple batches: run concurrently with semaphore
    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded(batch, pairs, batch_start, source_lang=None):
        async with semaphore:
            return await process_one_batch(batch, pairs, batch_start, source_lang)

    results = await asyncio.gather(*[
        bounded(*b) for b in batches
    ])
    all_results.extend(results)

    return all_results
