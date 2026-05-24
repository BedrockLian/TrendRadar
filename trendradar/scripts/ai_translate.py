#!/usr/bin/env python3
"""
ai_translate.py — Batch-translate English RSS summaries to Chinese using AI.

Reads curated_{slot}.json, detects English summaries (<50% CJK characters),
batch-translates them via DeepSeek API, and writes 'summary_cn' fields back.

Concurrency: Uses aiohttp for async HTTP. When items_to_translate > BATCH_SIZE,
multiple batches run in parallel via asyncio.gather (bounded by semaphore).

Usage: python3 ai_translate.py --push-id morning|noon|evening
"""
import json
import os
import sys
import re
import asyncio
from functools import lru_cache
from pathlib import Path

import aiohttp

from trendradar.scripts.settings import get_data_dir
DATA_DIR = get_data_dir()

# ── CJK detection ────────────────────────────────────────────────────────────

def _is_cjk(c: str) -> bool:
    """True if c is a CJK Unified Ideograph (Chinese hanzi / Japanese kanji / Korean hanja).
    Hiragana (0x3040-0x309F), Katakana (0x30A0-0x30FF), and Hangul (0xAC00-0xD7AF)
    are excluded — they are distinct scripts that should trigger translation.
    """
    cp = ord(c)
    # CJK Symbols & Punctuation (0x3000-0x303F) — include fullwidth punctuation
    if 0x3000 <= cp <= 0x303F:
        return True
    # Hiragana (0x3040-0x309F) and Katakana (0x30A0-0x30FF) — Japanese, NOT CJK
    if 0x3040 <= cp <= 0x30FF:
        return False
    # CJK Unified Ideographs (0x4E00-0x9FFF) + Ext A (0x3400-0x4DBF)
    if 0x3400 <= cp <= 0x9FFF:
        return True
    # CJK Compatibility Ideographs
    if 0xF900 <= cp <= 0xFAFF:
        return True
    # Fullwidth forms (punctuation, Latin)
    if 0xFF00 <= cp <= 0xFFEF:
        return True
    # CJK Extension B, C, D, E, Compatibility Supplement
    if cp < 0x20000:
        return False
    return (0x20000 <= cp <= 0x2CEAF or 0x2F800 <= cp <= 0x2FA1F)


@lru_cache(maxsize=2048)
def cjk_ratio(text: str) -> float:
    """Return fraction of non-whitespace characters that are CJK."""
    if not text:
        return 0.0
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(1 for c in chars if _is_cjk(c)) / len(chars)


def _has_japanese_kana(text: str) -> bool:
    """Detect Japanese text by looking for Hiragana (0x3040-0x309F) or Katakana (0x30A0-0x30FF)."""
    return any('぀' <= c <= 'ゟ' or '゠' <= c <= 'ヿ' for c in text)


def detect_source_lang(text: str) -> str:
    """Detect source language: 'Japanese' if has kana, else 'English'."""
    if _has_japanese_kana(text):
        return 'Japanese'
    return 'English'


def needs_translation(text: str) -> bool:
    """Determine if text needs translation to Chinese.
    
    Returns True if:
    1. Text contains Japanese kana (Hiragana/Katakana) — regardless of CJK ratio
    2. Chinese CJK character ratio is < 50% (English or mixed text)
    False for purely Chinese text (CJK ratio >= 50% and no kana).
    """
    if not text:
        return False
    # Japanese text: contains Hiragana or Katakana
    if _has_japanese_kana(text):
        return True
    # English or other: low CJK ratio
    return cjk_ratio(text) < 0.5


# ── Source matching ──────────────────────────────────────────────────────────

# Sources known to produce English content about China (foreign_china domain).
# Matched case-insensitively against source_platform.
_FOREIGN_CHINA_KEYWORDS = [
    'bbc', 'nytimes', 'reuters', 'guardian', 'scmp',
    '纽约时报', '卫报', '南华早报', '路透社',
]


def is_foreign_china_source(source_platform: str) -> bool:
    plat_lower = source_platform.lower()
    return any(kw in plat_lower for kw in _FOREIGN_CHINA_KEYWORDS)


# ── Translation API ──────────────────────────────────────────────────────────

from trendradar.scripts.settings import get_api_key, get_api_endpoint, get_model
from string import Template

API_ENDPOINT = get_api_endpoint()
MODEL = get_model()
BATCH_SIZE = 20
MAX_CONCURRENT_BATCHES = 5

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
    max_retries: int = 2,
) -> dict:
    """Send a single API request with retries on failure. Uses shared aiohttp session."""
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
    timeout = aiohttp.ClientTimeout(total=120)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async with session.post(
                API_ENDPOINT, json=payload, headers=headers, timeout=timeout
            ) as resp:
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                print(
                    f"[TRANSLATE] API error (attempt {attempt+1}/{max_retries+1}), "
                    f"retrying in {wait}s: {e}",
                    file=sys.stderr,
                )
                await asyncio.sleep(wait)
    if last_error is None:
        raise RuntimeError("_make_request failed but no error was captured")
    raise last_error


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

    items_to_translate: list of (domain, idx, item, title, summary, needs_title, needs_summary)
    Returns a list of (batch_items, translations_or_None, error_or_None) tuples.    """
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
        try:
            translations = await batch_translate(session, pairs, api_key, source_lang)
            batch_end = batch_start + len(batch)
            print(
                f"[TRANSLATE] Batch {batch_start+1}-{batch_end}/{len(items_to_translate)}: "
                f"translated {len(batch)} items",
                file=sys.stderr,
            )
            return (batch, translations, None)
        except Exception as e:
            print(
                f"[TRANSLATE] Batch translation failed: {e}",
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
    Each item is (domain, idx, item, title, summary).
    Prefers dated file (YYYYMMDD) to match render_markdown.py priority."""
    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    today_file = datetime.now(CST).strftime('%Y%m%d')
    curated_path = DATA_DIR / f'curated_{push_id}_{today_file}.json'
    if not curated_path.exists():
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

            needs_title = not has_title_cn and title and needs_translation(title)
            needs_summary = not has_summary_cn and summary and needs_translation(summary)

            if needs_title or needs_summary:
                                # Determine source language by platform
                plat = item.get('source_platform', '').lower()
                source_lang = None
                for kw in ['nhk', 'nhk ビジネス', '4gamer']:
                    if kw in plat: source_lang = 'Japanese'; break
                if not source_lang:
                    for kw in ['bbc', 'reuters', 'nytimes', 'guardian', 'techcrunch',
                               '路透社', '纽约时报', '卫报', 'ars technica', 'pc gamer',
                               'nintendo everything', 'eurogamer', 'video games chronicle',
                               'npr', 'koreaherald']:
                        if kw in plat: source_lang = 'English'; break
                items_to_translate.append((domain, idx, item, title, summary, needs_title, needs_summary, source_lang))

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
    Split into _load_and_scan / _batch_translate / _write_back."""
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
        # batch: list of (domain, idx, item, title, summary, needs_title, needs_summary)
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
