#!/usr/bin/env python3
"""
ai_translate.py — Batch-translate English/Japanese RSS summaries to Chinese using AI.

Reads curated_{slot}.json, classifies items by source_platform (not content heuristics),
batch-translates via DeepSeek API, and writes 'title_cn'/'summary_cn' fields back.

Language detection is driven by data/sources.json — each source entry has a
`language` field ("zh"/"en"/"ja"). The `platform` field values are extracted
at import time for matching against item source_platform.

Add/edit sources in data/sources.json with the correct language field;
do NOT maintain a separate language mapping file (translate.yaml is obsolete).
"""
import json
import os
import sys
import re
import asyncio
import random
from functools import lru_cache
from pathlib import Path

import aiohttp

from trendradar.scripts.settings import get_data_dir
DATA_DIR = get_data_dir()


# ── Source language classification (from data/sources.json) ──────────────────
# Each source entry has a `language` field ("zh"/"en"/"ja").
# The `platform` field values are extracted per language for substring matching.
# Do NOT maintain a separate mapping file — sources.json is the single truth.

_SOURCES_PATH = get_data_dir() / 'sources.json'

def _load_source_languages() -> tuple[frozenset, frozenset]:
    """Read sources.json and build (en_keywords, ja_keywords) frozensets.

    Uses both `platform` (short: 'bbc') and `name` (full: 'BBC 商务') from
    entries where language is "en" or "ja". Short platforms match compound
    source_platform values like 'BBC 商务+BBC 科技'.
    """
    if not _SOURCES_PATH.exists():
        return frozenset(), frozenset()
    try:
        with open(_SOURCES_PATH) as f:
            cfg = json.load(f)
        en = set()
        ja = set()
        def _scan(obj):
            if isinstance(obj, dict):
                lang = obj.get('language', '')
                if lang in ('en', 'ja'):
                    name = str(obj.get('name', '')).lower().strip()
                    plat = str(obj.get('platform', '')).lower().strip()
                    if name:
                        (en if lang == 'en' else ja).add(name)
                    if plat:
                        (en if lang == 'en' else ja).add(plat)
                for v in obj.values():
                    _scan(v)
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item)
        _scan(cfg)
        return frozenset(en), frozenset(ja)
    except Exception:
        return frozenset(), frozenset()


_EN_PLATFORMS, _JA_PLATFORMS = _load_source_languages()


def get_source_lang(source_platform: str) -> str | None:
    """Return 'English', 'Japanese', or None (skip — Chinese or unknown).
    
    Matched by substring: platform in source_platform.lower().
    Japanese keywords checked first (NHK could contain English keyword too).
    """
    plat = source_platform.lower().strip()
    for kw in _JA_PLATFORMS:
        if kw in plat:
            return 'Japanese'
    for kw in _EN_PLATFORMS:
        if kw in plat:
            return 'English'
    return None


# ── Translation API ──────────────────────────────────────────────────────────

from trendradar.scripts.settings import get_api_key, get_api_endpoint, get_model
from string import Template

API_ENDPOINT = get_api_endpoint()
MODEL = get_model()
BATCH_SIZE = 5
MAX_CONCURRENT_BATCHES = 5

# ── Exponential Backoff 熔断配置 ────────────────────────────────────────────
# 针对 Trap 28: DeepSeek openresty 流中断 (RemoteProtocolError)
RETRY_BASE_DELAY = 2.0        # 初始等待秒数
RETRY_MAX_DELAY = 30.0        # 上限秒数
RETRY_JITTER = 0.5            # ±50% 随机抖动
RETRY_MAX_ATTEMPTS = 4        # 最多 5 次尝试 (初始 + 4 次重试)
CIRCUIT_BREAKER_THRESHOLD = 3  # 连续 3 个 batch 失败 → 熔断，跳过剩余

_translate_failures = 0        # 模块级熔断计数器

_TRANSLATE_TEMPLATE = Template("""You are a professional translator. Translate the following $source_lang news items
into concise, natural Chinese.
Each item contains a TITLE and a SUMMARY.
Rules:
1. Preserve all factual details (names, numbers, dates, percentages, locations).
2. Use journalistic Chinese style — clear, objective, and fluent.
3. Keep proper nouns untranslated unless a widely-accepted Chinese name exists.
4. Output each item as EXACTLY TWO lines: first line = translated title, second line = translated summary.
5. Each line must be a single line (no line breaks inside).
6. Do NOT add numbering, prefixes, or any extra commentary.
7. Output exactly 2N lines for N input items.""")


def get_system_prompt(source_lang: str = "English") -> str:
    """Render translation prompt template."""
    return _TRANSLATE_TEMPLATE.substitute(source_lang=source_lang)


async def _make_request(
    session: aiohttp.ClientSession,
    api_key: str,
    messages: list,
) -> dict:
    """Send a single API request with exponential backoff + jitter retry.

    Retry strategy:
    - Base delay 2s, doubles each retry (2→4→8→16→30s capped)
    - ±50% random jitter to avoid thundering herd
    - Max 5 total attempts (initial + 4 retries)
    - On RemoteProtocolError (Trap 28 — DeepSeek stream drop), retries with
      increased timeout budget
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    last_error = None
    for attempt in range(RETRY_MAX_ATTEMPTS + 1):
        # Increase timeout on retries (stream drops may need longer)
        timeout_seconds = 120 + (attempt * 30)
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)

        try:
            async with session.post(
                API_ENDPOINT, json=payload, headers=headers, timeout=timeout
            ) as resp:
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                jitter = delay * RETRY_JITTER * (random.random() * 2 - 1)
                delay += jitter
                print(
                    f"[TRANSLATE] API error (attempt {attempt+1}/{RETRY_MAX_ATTEMPTS+1}), "
                    f"retrying in {delay:.1f}s: {e}",
                    file=sys.stderr,
                )
                await asyncio.sleep(delay)

    if last_error is None:
        raise RuntimeError("_make_request failed but no error was captured")
    raise last_error


def circuit_broken() -> bool:
    """Check if circuit breaker is open (too many consecutive failures)."""
    return _translate_failures >= CIRCUIT_BREAKER_THRESHOLD


def reset_circuit():
    """Reset circuit breaker counter."""
    global _translate_failures
    _translate_failures = 0


async def batch_translate(
    session: aiohttp.ClientSession,
    items: list,
    api_key: str,
    source_lang: str = 'English',
) -> list[tuple[str, str]]:
    """Translate a batch of (title, summary) pairs. Returns list of (title_cn, summary_cn) tuples."""
    if not items:
        return []

    # Source language was determined by get_source_lang in _load_and_scan
    # and passed through items_to_translate tuple

    # Build the user message: each item = title line + summary line
    user_lines = []
    for i, (title, summary) in enumerate(items):
        clean_title = title.replace('\n', ' ').replace('\r', ' ').strip()
        clean_title = re.sub(r'\s+', ' ', clean_title)
        clean_title = re.sub(r'&#\d+;', '', clean_title)
        clean_summary = summary.replace('\n', ' ').replace('\r', ' ').strip()
        clean_summary = re.sub(r'\s+', ' ', clean_summary)
        clean_summary = re.sub(r'&#\d+;', '', clean_summary)
        user_lines.append(
            f"[{i+1}] TITLE: {clean_title}\n    SUMMARY: {clean_summary}"
        )

    user_message = "\n\n".join(user_lines)
    messages = [
        {"role": "system", "content": get_system_prompt(source_lang)},
        {"role": "user", "content": user_message},
    ]

    response = await _make_request(session, api_key, messages)
    if 'choices' not in response or not response['choices']:
        raise ValueError(
            f"Unexpected API response: "
            f"{response.get('error', {}).get('message', 'unknown')}"
        )
    content = response["choices"][0]["message"]["content"].strip()

    # Parse the response: expect 2N lines (title_cn, summary_cn per item)
    lines = [l.strip() for l in content.split('\n') if l.strip()]

    # Pair into (title, summary) tuples
    results = []
    for i in range(0, len(lines), 2):
        title_cn = lines[i] if i < len(lines) else "[翻译失败]"
        summary_cn = lines[i + 1] if i + 1 < len(lines) else "[翻译失败]"
        # Strip any [N] prefix the model may have added
        title_cn = re.sub(r'^\[\d+\]\s*', '', title_cn).strip()
        summary_cn = re.sub(r'^\[\d+\]\s*', '', summary_cn).strip()
        results.append((title_cn, summary_cn))

    # Pad or truncate to match input count
    while len(results) < len(items):
        results.append(("[翻译失败]", "[翻译失败]"))
    results = results[:len(items)]

    return results


async def _batch_translate_all(
    session: aiohttp.ClientSession,
    items_to_translate: list,
    api_key: str,
) -> list:
    """Translate all items using concurrent batches when > BATCH_SIZE items.

    items_to_translate: list of (domain, idx, item, title, summary, needs_title, needs_summary, source_lang)
    Returns a list of (batch_items, translations_or_None, error_or_None) tuples.
    """
    # Split into batches
    batches = []
    # Determine source language from first item
    source_lang = items_to_translate[0][7] if items_to_translate else 'English'

    for batch_start in range(0, len(items_to_translate), BATCH_SIZE):
        batch = items_to_translate[batch_start:batch_start + BATCH_SIZE]
        # Build (title, summary) pairs for translation
        pairs = [(item[3], item[4]) for item in batch]  # (title, summary)
        batches.append((batch, pairs, batch_start))

    async def translate_one_batch(
        batch, pairs, batch_start
    ) -> tuple[list, list | None, Exception | None]:
        global _translate_failures
        try:
            # Circuit breaker check
            if circuit_broken():
                print(
                    f"[TRANSLATE] ⚡ 熔断触发 — 连续 {CIRCUIT_BREAKER_THRESHOLD} 个 batch 失败，"
                    f"跳过剩余批次",
                    file=sys.stderr,
                )
                return (batch, None, RuntimeError("Circuit breaker open"))
            translations = await batch_translate(session, pairs, api_key, source_lang)
            batch_end = batch_start + len(batch)
            print(
                f"[TRANSLATE] Batch {batch_start+1}-{batch_end}/{len(items_to_translate)}: "
                f"translated {len(batch)} items",
                file=sys.stderr,
            )
            _translate_failures = 0  # 成功后重置熔断计数
            return (batch, translations, None)
        except Exception as e:
            _translate_failures += 1
            print(
                f"[TRANSLATE] Batch translation failed ({_translate_failures}/"
                f"{CIRCUIT_BREAKER_THRESHOLD} strikes): {e}",
                file=sys.stderr,
            )
            return (batch, None, e)

    # If only one batch, no need for semaphore/gather overhead
    if len(batches) == 1:
        batch, pairs, batch_start = batches[0]
        result = await translate_one_batch(batch, pairs, batch_start)
        return [result]

    # Multiple batches: run concurrently with a semaphore bound
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)

    async def bounded_translate(batch, pairs, batch_start):
        async with semaphore:
            return await translate_one_batch(batch, pairs, batch_start)

    results = await asyncio.gather(*[
        bounded_translate(b, p, bs) for b, p, bs in batches
    ])
    return list(results)


# ── Main processing ──────────────────────────────────────────────────────────


def _load_and_scan(push_id: str) -> tuple[dict, list, Path]:
    """Load curated JSON and scan for items needing translation.
    Returns (data, items_to_translate, curated_path).
    Each item is (domain, idx, item, title, summary, needs_title, needs_summary, source_lang).
    Prefers dated file (YYYYMMDD) to match render_markdown.py priority.
    """
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    today_file = datetime.now(CST).strftime('%Y%m%d')
    curated_path = DATA_DIR / f'curated_{push_id}_{today_file}.json'
    if not curated_path.exists():
        # Fallback 2: find latest dated version
        dated_files = sorted(
            DATA_DIR.glob(f'curated_{push_id}_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json'),
            reverse=True,
        )
        if dated_files:
            curated_path = dated_files[0]
        else:
            # Fallback 3: generic version
            curated_path = DATA_DIR / f'curated_{push_id}.json'
    if not curated_path.exists():
        print(
            f"[TRANSLATE] No curated file found for push-id '{push_id}'",
            file=sys.stderr,
        )
        sys.exit(1)

    data = json.loads(curated_path.read_text())
    from trendradar.scripts.settings import DOMAINS
    domains = DOMAINS
    items_to_translate = []

    for domain in domains:
        items = data.get(domain, [])
        for idx, item in enumerate(items):
            title = (item.get('title', '') or '').strip()
            summary = (item.get('summary', '') or '').strip()
            has_title_cn = bool(item.get('title_cn'))
            has_summary_cn = bool(item.get('summary_cn'))

            # Skip if both already translated
            if has_title_cn and has_summary_cn:
                continue

            # Determine source language by platform (from translate.yaml)
            source_lang = get_source_lang(item.get('source_platform', ''))

            # Only translate if we know the source language
            needs_title = not has_title_cn and title and bool(source_lang)
            needs_summary = not has_summary_cn and summary and bool(source_lang)

            if needs_title or needs_summary:
                items_to_translate.append(
                    (domain, idx, item, title, summary, needs_title, needs_summary, source_lang)
                )

    return data, items_to_translate, curated_path


def _write_back(data: dict, curated_path: Path, push_id: str):
    """Write translated data back to curated file and dated variant."""
    from trendradar.scripts.settings import atomic_write_json
    atomic_write_json(curated_path, data)

    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    today = datetime.now(CST).strftime('%Y%m%d')
    dated_path = DATA_DIR / f'curated_{push_id}_{today}.json'
    if dated_path.exists():
        from trendradar.scripts.settings import atomic_write_json
        atomic_write_json(dated_path, data)


async def process_curated(push_id: str) -> dict:
    """Load curated JSON, translate English titles+summaries, and save back.
    Split into _load_and_scan / _batch_translate / _write_back.
    """
    data, items_to_translate, curated_path = _load_and_scan(push_id)

    if not items_to_translate:
        print(
            f"[TRANSLATE] No English items found for push-id '{push_id}'",
            file=sys.stderr,
        )
        return data

    print(
        f"[TRANSLATE] Found {len(items_to_translate)} items to translate "
        f"for push-id '{push_id}'",
        file=sys.stderr,
    )

    from trendradar.scripts.settings import get_api_key
    api_key = get_api_key()
    if not api_key:
        print(
            "[TRANSLATE] DEEPSEEK_API_KEY not set — skipping translation "
            "(graceful degradation)",
            file=sys.stderr,
        )
        sys.exit(0)

    total_chars = 0
    translated_count = 0

    async with aiohttp.ClientSession() as session:
        batch_results = await _batch_translate_all(
            session, items_to_translate, api_key
        )

    for batch, translations, error in batch_results:
        if error:
            continue
        # batch: list of (domain, idx, item, title, summary, needs_title, needs_summary, source_lang)
        # translations: list of (title_cn, summary_cn) tuples
        for entry, (title_cn, summary_cn) in zip(batch, translations, strict=True):
            domain, idx, item, title, summary, needs_title, needs_summary, _source_lang = entry
            if needs_title:
                item['title_cn'] = title_cn
            if needs_summary:
                item['summary_cn'] = summary_cn
            translated_count += 1
            total_chars += len(title) + len(summary)

    _write_back(data, curated_path, push_id)

    print(
        f"[TRANSLATE] Done: {translated_count} items translated, "
        f"{total_chars} chars total",
        file=sys.stderr,
    )

    return data


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Batch-translate English RSS summaries to Chinese using AI'
    )
    parser.add_argument(
        '--push-id',
        required=True,
        choices=['morning', 'noon', 'evening'],
        help='Which push slot to process (morning|noon|evening)'
    )
    args = parser.parse_args()
    asyncio.run(process_curated(args.push_id))


if __name__ == '__main__':
    main()
