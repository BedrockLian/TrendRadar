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

from trendradar.scripts.settings import get_data_dir, get_logger

log = get_logger('ai-translate')

from trendradar.scripts.common import CST
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
    except Exception as e:
        log.error(f"加载 sources.json 失败，翻译功能已禁用: {e}")
        return frozenset(), frozenset()


_EN_PLATFORMS = None
_JA_PLATFORMS = None


def _get_source_languages():
    global _EN_PLATFORMS, _JA_PLATFORMS
    if _EN_PLATFORMS is None:
        _EN_PLATFORMS, _JA_PLATFORMS = _load_source_languages()
    return _EN_PLATFORMS, _JA_PLATFORMS


def get_source_lang(source_platform: str) -> str | None:
    """Return 'English', 'Japanese', or None (skip — Chinese or unknown).
    
    Matched by substring: platform in source_platform.lower().
    Japanese keywords checked first (NHK could contain English keyword too).
    """
    _get_source_languages()
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
from trendradar.scripts.settings import TRANSLATE_BATCH_SIZE, TRANSLATE_BATCH_MAX_CONCURRENT
BATCH_SIZE = TRANSLATE_BATCH_SIZE
MAX_CONCURRENT_BATCHES = TRANSLATE_BATCH_MAX_CONCURRENT

# ── Exponential Backoff 熔断配置 ────────────────────────────────────────────
# 针对 Trap 28: DeepSeek openresty 流中断 (RemoteProtocolError)
RETRY_BASE_DELAY = 2.0        # 初始等待秒数
RETRY_MAX_DELAY = 30.0        # 上限秒数
RETRY_JITTER = 0.5            # ±50% 随机抖动
RETRY_MAX_ATTEMPTS = 4        # 最多 5 次尝试 (初始 + 4 次重试)
CIRCUIT_BREAKER_THRESHOLD = 5  # 连续 5 个 batch 失败 → 熔断（瞬态429不应触发）

_translate_failures = 0        # 模块级熔断计数器

_EXPAND_TEMPLATE = Template("""You are a professional news editor. The following Chinese news items have very short summaries (often just a tagline or metaphor).

Rewrite each item's TITLE and SUMMARY into a complete, informative Chinese sentence of about 50-80 Chinese characters.

Rules:
1. Preserve all factual details (company names, numbers, dates, percentages).
2. If the summary is too vague or metaphorical (e.g. "风口上的猪"), draw on the title context to write a concrete, factual summary.
3. Do NOT add information that is not implied by the title or summary.
4. Use journalistic Chinese style — clear, objective, and fluent.
5. Output each item as EXACTLY TWO lines: first line = rewritten title, second line = rewritten summary.
6. Each line must be a single line (no line breaks inside).
7. Do NOT add numbering, prefixes, or any extra commentary.
8. Output exactly 2N lines for N input items.""")

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
        timeout_seconds = 30 + len(messages) * 3 + (attempt * 15)
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
                log.warning(
                    f"API error (attempt {attempt+1}/{RETRY_MAX_ATTEMPTS+1}), "
                    f"retrying in {delay:.1f}s: {e}")
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


def increment_failures():
    """Increment circuit breaker counter."""
    global _translate_failures
    _translate_failures += 1


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
    # Model may add extra blank lines, numbering, or commentary — strip noise
    raw_lines = [l.strip() for l in content.split('\n')]
    # Filter out empty lines and common model commentary prefixes
    lines = []
    for l in raw_lines:
        if not l:
            continue
        # Skip lines that look like model commentary, not translations
        if l.startswith(('Here', 'The following', 'Below', 'Note:', '以上是')):
            continue
        lines.append(l)

    # Pair into (title, summary) tuples
    results = []
    for i in range(0, len(lines), 2):
        title_cn = lines[i] if i < len(lines) else "[翻译失败]"
        summary_cn = lines[i + 1] if i + 1 < len(lines) else "[翻译失败]"
        # Strip any [N] prefix or bullet the model may have added
        title_cn = re.sub(r'^[\[（\(]?\d+[\]）\)]?[.、．\s]*', '', title_cn).strip()
        summary_cn = re.sub(r'^[\[（\(]?\d+[\]）\)]?[.、．\s]*', '', summary_cn).strip()
        # Skip if this looks like a separator/commentary line
        if title_cn.startswith(('---', '===')):
            continue
        results.append((title_cn, summary_cn))

    # Pad or truncate to match input count
    while len(results) < len(items):
        results.append(("[翻译失败]", "[翻译失败]"))
    results = results[:len(items)]

    return results


# ── Batch processing utils (was batch_utils.py, merged into ai_translate) ──
# process_batches is only used by _batch_translate_all and _batch_expand_all below

async def process_batches(
    session,
    batches: list,
    items_to_process: list,
    batch_func,
    api_key: str,
    source_lang_field: int = 7,
    max_concurrent: int = 6,
    batch_size: int = 5,
    circuit_broken=lambda: False,
    circuit_reset=lambda: None,
    circuit_fail=lambda: None,
    log_prefix: str = "Batch",
    group_by_lang: bool = True,
) -> list:
    """泛化批次处理 — 翻译/扩写/未来 AI 操作复用。"""
    all_results = []

    async def process_one_batch(batch, pairs, batch_start, source_lang=None):
        try:
            if circuit_broken():
                log.error(f"熔断触发 — 跳过剩余批次")
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
            log.error(f"{log_prefix} failed: {e}")
            return (batch, None, e)

    if len(batches) == 1:
        result = await process_one_batch(*batches[0])
        all_results.append(result)
        return all_results

    semaphore = asyncio.Semaphore(max_concurrent)

    async def bounded(batch, pairs, batch_start, source_lang=None):
        async with semaphore:
            return await process_one_batch(batch, pairs, batch_start, source_lang)

    results = await asyncio.gather(*[
        bounded(*b) for b in batches
    ])
    all_results.extend(results)

    return all_results


async def _batch_translate_all(
    session: aiohttp.ClientSession,
    items_to_translate: list,
    api_key: str,
    batch_size: int = None,
) -> list:
    """Translate all items using concurrent batches (via inline process_batches)."""

    # Group by source_lang to keep language-specific prompts correct
    groups: dict[str, list] = {}
    for item in items_to_translate:
        lang = item[7] or 'English'
        groups.setdefault(lang, []).append(item)

    bs = batch_size if batch_size is not None else BATCH_SIZE
    all_batches = []
    for lang, group_items in groups.items():
        for batch_start in range(0, len(group_items), bs):
            batch = group_items[batch_start:batch_start + bs]
            pairs = [(item[3], item[4]) for item in batch]
            all_batches.append((batch, pairs, batch_start, lang))

    return await process_batches(
        session=session,
        batches=all_batches,
        items_to_process=items_to_translate,
        batch_func=batch_translate,
        api_key=api_key,
        max_concurrent=MAX_CONCURRENT_BATCHES,
        batch_size=bs,
        circuit_broken=circuit_broken,
        circuit_reset=reset_circuit,
        circuit_fail=increment_failures,
        log_prefix="Translate batch",
        group_by_lang=True,
    )


async def _batch_expand_all(
    session: aiohttp.ClientSession,
    items_to_expand: list,
    api_key: str,
    batch_size: int = None,
) -> list:
    """Expand short Chinese summaries using AI (via inline process_batches)."""

    bs = batch_size if batch_size is not None else BATCH_SIZE
    batches = []
    for batch_start in range(0, len(items_to_expand), bs):
        batch = items_to_expand[batch_start:batch_start + bs]
        pairs = [(item[3], item[4]) for item in batch]
        batches.append((batch, pairs, batch_start, None))

    return await process_batches(
        session=session,
        batches=batches,
        items_to_process=items_to_expand,
        batch_func=batch_expand,
        api_key=api_key,
        max_concurrent=MAX_CONCURRENT_BATCHES,
        batch_size=bs,
        circuit_broken=circuit_broken,
        circuit_reset=reset_circuit,
        circuit_fail=increment_failures,
        log_prefix="Expand batch",
        group_by_lang=False,
    )


async def batch_expand(
    session: aiohttp.ClientSession,
    items: list[tuple[str, str]],
    api_key: str,
) -> list[tuple[str, str]]:
    """Expand a batch of short Chinese summaries using AI.

    Each item is (title, summary) tuple.
    Returns list of (title_cn, summary_cn) tuples.
    """
    user_lines = []
    for idx, (title, summary) in enumerate(items, 1):
        user_lines.append(
            f"Item {idx}:\nTITLE: {title}\nSUMMARY: {summary}"
        )

    user_message = "\n\n".join(user_lines)
    messages = [
        {"role": "system", "content": _EXPAND_TEMPLATE.substitute()},
        {"role": "user", "content": user_message},
    ]

    response = await _make_request(session, api_key, messages)
    if 'choices' not in response or not response['choices']:
        raise ValueError(
            f"Unexpected API response: "
            f"{response.get('error', {}).get('message', 'unknown')}"
        )
    content = response["choices"][0]["message"]["content"].strip()

    raw_lines = [l.strip() for l in content.split('\n')]
    lines = [l for l in raw_lines if l]
    # Strip model commentary lines
    lines = [l for l in lines if not l.startswith(('Here', 'The following', 'Below', 'Note:', '以上是'))]

    results = []
    for i in range(0, len(lines), 2):
        title_cn = lines[i] if i < len(lines) else "[扩写失败]"
        summary_cn = lines[i + 1] if i + 1 < len(lines) else "[扩写失败]"
        title_cn = re.sub(r'^[\[\（\(]?\d+[\]）\)]?[.、．\s]*', '', title_cn).strip()
        summary_cn = re.sub(r'^[\[\（\(]?\d+[\]）\)]?[.、．\s]*', '', summary_cn).strip()
        results.append((title_cn, summary_cn))

    while len(results) < len(items):
        results.append(("[扩写失败]", "[扩写失败]"))
    results = results[:len(items)]

    return results


# ── Main processing ──────────────────────────────────────────────────────────


def _load_and_scan(push_id: str) -> tuple[dict, list, list, Path]:
    """Load curated JSON and scan for items needing translation or expansion.
    Returns (data, items_to_translate, items_to_expand, curated_path).
    items_to_translate: foreign items needing translation to Chinese.
    items_to_expand: Chinese items with short summaries (< 50 chars) needing expansion.
    Each item is (domain, idx, item, title, summary, needs_title, needs_summary, source_lang).
    Prefers dated file (YYYYMMDD) to match render_markdown.py priority.
    """
    from datetime import datetime
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
        log.info(
            f"No curated file found for push-id '{push_id}'")
        sys.exit(1)

    data = json.loads(curated_path.read_text())
    from trendradar.scripts.settings import DOMAINS
    domains = DOMAINS
    items_to_translate = []
    items_to_expand = []

    for domain in domains:
        items = data.get(domain, [])
        for idx, item in enumerate(items):
            title = (item.get('title', '') or '').strip()
            summary = (item.get('summary', '') or '').strip()
            has_title_cn = bool(item.get('title_cn'))
            has_summary_cn = bool(item.get('summary_cn'))

            # Skip if both already translated/expanded
            if has_title_cn and has_summary_cn:
                continue

            # Determine source language by platform (from translate.yaml)
            source_lang = get_source_lang(item.get('source_platform', ''))

            if source_lang:
                # Foreign language: translate to Chinese
                needs_title = not has_title_cn and bool(title)
                needs_summary = not has_summary_cn and bool(summary)
                if needs_title or needs_summary:
                    items_to_translate.append(
                        (domain, idx, item, title, summary, needs_title, needs_summary, source_lang)
                    )
            else:
                # Chinese source: check if summary is too short (< 50 chars) and needs expansion
                if not has_summary_cn and len(summary) > 0 and len(summary) < 50:
                    items_to_expand.append(
                        (domain, idx, item, title, summary, True, True, 'Chinese')
                    )

    return data, items_to_translate, items_to_expand, curated_path


def _write_back(data: dict, curated_path: Path, push_id: str):
    """Write translated data back to curated file and dated variant."""
    from trendradar.scripts.settings import atomic_write_json
    atomic_write_json(curated_path, data)

    from datetime import datetime
    today = datetime.now(CST).strftime('%Y%m%d')
    dated_path = DATA_DIR / f'curated_{push_id}_{today}.json'
    if dated_path.exists():
        from trendradar.scripts.settings import atomic_write_json
        atomic_write_json(dated_path, data)


async def process_curated(push_id: str) -> dict:
    """Load curated JSON, translate foreign titles+summaries and expand short Chinese summaries, then save back."""
    data, items_to_translate, items_to_expand, curated_path = _load_and_scan(push_id)

    if not items_to_translate and not items_to_expand:
        log.info(
            f"No items need processing for push-id '{push_id}'")
        return data

    from trendradar.scripts.settings import get_api_key
    api_key = get_api_key()
    if not api_key:
        log.warning(
            "DEEPSEEK_API_KEY not set — skipping translation "
            "(graceful degradation)")
        from trendradar.scripts.common import EXIT_NO_CONTENT
        sys.exit(EXIT_NO_CONTENT)

    total_chars = 0
    translated_count = 0

    async with aiohttp.ClientSession() as session:
        # Step 1: Translate foreign items
        if items_to_translate:
            log.info(
                f"Found {len(items_to_translate)} items to translate "
                f"for push-id '{push_id}'")
            batch_results = await _batch_translate_all(
                session, items_to_translate, api_key
            )

            for batch, translations, error in batch_results:
                if error:
                    continue
                for entry, (title_cn, summary_cn) in zip(batch, translations, strict=True):
                    domain, idx, item, title, summary, needs_title, needs_summary, _source_lang = entry
                    if needs_title:
                        item['title_cn'] = title_cn
                    if needs_summary:
                        item['summary_cn'] = summary_cn
                    translated_count += 1
                    total_chars += len(title) + len(summary)

        # Step 2: Expand short Chinese summaries
        if items_to_expand:
            log.info(
                f"Found {len(items_to_expand)} Chinese items with short summaries to expand "
                f"for push-id '{push_id}'")
            expand_results = await _batch_expand_all(
                session, items_to_expand, api_key
            )

            for batch, translations, error in expand_results:
                if error:
                    continue
                for entry, (title_cn, summary_cn) in zip(batch, translations, strict=True):
                    domain, idx, item, title, summary, needs_title, needs_summary, _source_lang = entry
                    if needs_title and title_cn:
                        item['title_cn'] = title_cn
                    if needs_summary and summary_cn:
                        item['summary_cn'] = summary_cn
                    translated_count += 1
                    total_chars += len(title) + len(summary)

    _write_back(data, curated_path, push_id)

    log.info(
        f"Done: {translated_count} items processed, "
        f"{total_chars} chars total")

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
    parser.add_argument('--batch-size', type=int, default=None,
                        help=f'Items per batch (default: {TRANSLATE_BATCH_SIZE}, max 50)')
    args = parser.parse_args()
    
    # Apply batch_size override
    global BATCH_SIZE
    if args.batch_size:
        BATCH_SIZE = min(args.batch_size, 50)
    
    asyncio.run(process_curated(args.push_id))


if __name__ == '__main__':
    main()
