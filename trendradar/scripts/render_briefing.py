#!/usr/bin/env python3
from settings import get_logger
log = get_logger('render-briefing')
"""
render_briefing.py — 并行渲染 5 板块 Markdown 简报。

读取 curated JSON + batch JSON，将 5 个 domain 拆分为 5 路并行 Flash API 调用，
拼接为完整 Markdown 简报。比串行 LLM 渲染快 3-5x。

用法: python3 render_briefing.py --push-id morning|noon|evening
输出: Markdown 简报到 stdout，日志到 stderr
"""
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import aiohttp

CST = timezone(timedelta(hours=8))
from settings import get_data_dir, get_cache_dir
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()

from settings import get_api_endpoint, get_model
API_ENDPOINT = get_api_endpoint()
MODEL = get_model()

DOMAIN_EMOJI = {
    'top_headlines': '📰', 'foreign_china': '🌏',
    'tech': '💻', 'economy': '📊', 'gaming': '🎮',
}
DOMAIN_LABEL = {
    'top_headlines': '头条', 'foreign_china': '外媒看华',
    'tech': '科技', 'economy': '经济民生', 'gaming': '游戏',
}

from string import Template

_BRIEFING_TEMPLATE = Template("""你是新闻简报编辑。将输入的新闻条目渲染为简洁的 Markdown 简报片段，输出纯 Markdown 文本，无额外解释。

格式规则（严格遵守）：
1. 板块标题: `### $emoji $label`，独占一行，标题后一个空行
2. 每条新闻三行式，条目之间两个空行：
   行1: `🆕/🔥 序号. **标题**`（标题必须是中文，若有英文标题需翻译成中文）
   行2: 摘要（30-60字中文，英文摘要必须翻译）
   行3: `[查看原文](url)【媒体名】`
3. 三行式内部一行一个空行
4. 禁止表格、横线、代码块、自我叙述
5. 直接从第一条开始输出""")


def get_briefing_prompt(emoji: str = "{emoji}", label: str = "{label}") -> str:
    """Render briefing prompt template."""
    return _BRIEFING_TEMPLATE.substitute(emoji=emoji, label=label)


SYSTEM_PROMPT = get_briefing_prompt()  # backward-compatible default


def get_api_key() -> str:
    from settings import get_api_key as _get_api_key
    return _get_api_key()


def load_data(push_id: str) -> tuple[dict, dict]:
    curated = None
    for p in [DATA_DIR / f'curated_{push_id}.json',
              DATA_DIR / f'curated_{push_id}_{datetime.now(CST).strftime("%Y%m%d")}.json']:
        if p.exists():
            curated = json.loads(p.read_text())
            break
    if not curated:
        raise FileNotFoundError(f"No curated data for {push_id}")

    batch = {}
    bp = CACHE_DIR / f'batch_{push_id}.json'
    if bp.exists():
        try:
            batch = json.loads(bp.read_text())
        except Exception as e:
            import traceback
            log.warning(f'加载 batch 缓存失败: {e}\n{traceback.format_exc()}')
    return curated, batch


def build_domain_prompt(domain: str, items: list, push_id: str) -> str:
    lines = []
    for i, item in enumerate(items):
        title = (item.get('title_cn') or item.get('title', '') or '')[:80]
        summary = item.get('summary_cn') or item.get('summary', '') or ''
        summary = summary[:120].replace('\n', ' ')
        source = (item.get('source_platform', '') or '').split('+')[0][:20]
        url = item.get('url', '')[:200]
        heat = item.get('_heat', {})
        emoji = '🔥' if heat.get('trend') == 'rising' or heat.get('is_sustained') else '🆕'
        if push_id == 'evening' and item.get('_track'):
            t = item['_track']
            emoji = {'new': '🆕', 'rising': '🔥', 'progress': '📌'}.get(t, emoji)
        lines.append(f"[{i+1}] {emoji} 标题: {title}")
        lines.append(f"    摘要: {summary}")
        lines.append(f"    来源: {source} | URL: {url}")
    return '\n'.join(lines)


async def call_api(session: aiohttp.ClientSession, api_key: str, messages: list) -> str:
    payload = {
        "model": MODEL, "messages": messages,
        "temperature": 0.5, "max_tokens": 2048,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    from settings import API_RETRIES, API_CALL_TIMEOUT
    for attempt in range(API_RETRIES):
        try:
            async with session.post(
                API_ENDPOINT, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=API_CALL_TIMEOUT),
            ) as resp:
                data = await resp.json()
            if 'choices' not in data or not data['choices']:
                raise ValueError(f"API error: {data.get('error', {}).get('message', 'unknown')}")
            return data['choices'][0]['message']['content'].strip()
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
            else:
                raise


async def render_domain(session: aiohttp.ClientSession, domain: str, items: list, push_id: str, api_key: str) -> str:
    if not items:
        return f"### {DOMAIN_EMOJI[domain]} {DOMAIN_LABEL[domain]}\n\n暂无内容\n"
    user_prompt = build_domain_prompt(domain, items, push_id)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"板块: {DOMAIN_LABEL[domain]}\n\n新闻条目:\n{user_prompt}"},
    ]
    try:
        content = await call_api(session, api_key, messages)
        # 去除 LLM 可能自行添加的板块标题，使用硬编码的 emoji/label
        lines = content.split('\n')
        if lines and lines[0].startswith('###'):
            content = '\n'.join(lines[1:]).strip()
        header = f"### {DOMAIN_EMOJI[domain]} {DOMAIN_LABEL[domain]}"
        content = f"{header}\n\n{content}"
        log.info(f"{domain}: {len(items)}条, {len(content)}字")
        return content
    except Exception as e:
        log.info(f"{domain} 失败: {e}")
        return f"### {DOMAIN_EMOJI[domain]} {DOMAIN_LABEL[domain]}\n\n渲染失败\n"


SLOT_NAMES = {'morning': '早报', 'noon': '午间速递', 'evening': '今日回顾'}


async def render_all(push_id: str) -> str:
    curated, _ = load_data(push_id)
    api_key = get_api_key()
    if not api_key:
        log.info("DEEPSEEK_API_KEY not set")
        sys.exit(1)

    from settings import DOMAINS
    domains = DOMAINS
    async with aiohttp.ClientSession() as session:
        tasks = [render_domain(session, d, curated.get(d, []), push_id, api_key) for d in domains]
        results = await asyncio.gather(*tasks)

    date_str = datetime.now(CST).strftime('%Y-%m-%d')
    slot_name = SLOT_NAMES.get(push_id, push_id)
    header = f"### Hermes日报 · {date_str}（{slot_name}）\n"

    sections = '\n\n\n'.join(r for r in results if r)

    # 尾注：各板块条数
    counts = {d: len(curated.get(d, [])) for d in domains}
    summary = '  '.join(f"{DOMAIN_LABEL[d]}{counts[d]}" for d in domains)
    total = curated.get('total', sum(counts.values()))
    footer = f"\n\n**📋 共 {total} 条 · {summary}**"
    return header + sections + footer


def main():
    import argparse
    parser = argparse.ArgumentParser(description='并行渲染 5 板块 Markdown 简报')
    parser.add_argument('--push-id', required=True, choices=['morning', 'noon', 'evening'])
    args = parser.parse_args()

    t0 = time.time()
    result = asyncio.run(render_all(args.push_id))
    elapsed = time.time() - t0
    log.info(f"5 domain 并行完成, {elapsed:.1f}s")
    print(result)


if __name__ == '__main__':
    main()
