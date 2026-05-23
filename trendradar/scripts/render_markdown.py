#!/usr/bin/env python3
"""
render_markdown.py — 纯脚本渲染 TrendRadar 简报，无需 LLM API。

读取 curated JSON + batch JSON，直接拼接为严格格式化的 Markdown 简报。
比 LLM 渲染更快、格式 100% 一致、零 token 成本。

用法: python3 render_markdown.py --push-id morning|noon|evening
输出: Markdown 简报到 stdout
"""
from settings import get_logger
log = get_logger('render-markdown')

import json, sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
from settings import get_data_dir, DOMAINS, DOMAIN_LABELS, SLOT_NAMES

DATA_DIR = get_data_dir()
CACHE_DIR = ""


def _detect_emoji(heat: dict | None, push_id: str, track: str | None = None) -> str:
    if push_id == 'evening' and track:
        return {'new': '🆕', 'rising': '🔥', 'progress': '📌'}.get(track, '🆕')
    if heat:
        if heat.get('trend') == 'rising' or heat.get('is_sustained'):
            return '🔥'
    return '🆕'


def _format_item(idx: int, item: dict, push_id: str) -> str:
    """Format a single item as 3-line block."""
    title = _shorten(item.get('title') or '', 80)
    summary = _shorten(item.get('summary') or '', 150)
    url = (item.get('url') or '').strip()
    source = (item.get('source_platform') or '').split('+')[0].strip()
    heat = item.get('_heat')
    track = item.get('_track') if push_id == 'evening' else None
    emoji = _detect_emoji(heat, push_id, track)

    lines = [f"{emoji} {idx}. **{title}**"]

    if summary:
        lines.append(summary)

    link = f"[查看原文]({url})【{source}】" if url and source else ""
    if link:
        lines.append(link)

    return '\n\n'.join(lines)


def _shorten(text: str, max_len: int) -> str:
    """Trim text to max_len chars, preserving sentence boundaries if possible."""
    text = text.strip().replace('\n', ' ').replace('\r', ' ')
    if len(text) <= max_len:
        return text
    # Try to cut at sentence boundary within max_len
    cut = text[:max_len]
    for sep in '。。！？?！\n':
        pos = cut.rfind(sep)
        if pos > max_len * 0.6:
            return cut[:pos + 1]
    # Fallback: cut at last space
    pos = cut.rfind(' ')
    if pos > max_len * 0.6:
        return cut[:pos] + '…'
    return cut.rstrip() + '…'


def _generate_section(domain: str, items: list, push_id: str) -> str:
    """Generate a full section markdown with header."""
    if not items:
        return f"### {DOMAIN_LABELS[domain]}\n\n暂无内容"

    header = f"### {DOMAIN_LABELS[domain]}"
    item_blocks = [_format_item(i + 1, item, push_id) for i, item in enumerate(items)]

    return header + '\n\n\n' + '\n\n\n'.join(item_blocks)


def _generate_footer(curated: dict) -> str:
    """Generate the summary footer."""
    counts = {d: len(curated.get(d, [])) for d in DOMAINS}
    summary = '  '.join(f"{DOMAIN_LABELS[d]}{counts[d]}" for d in DOMAINS)
    total = curated.get('total', sum(counts.values()))
    return f"**📋 共 {total} 条 · {summary}**"


def render(push_id: str) -> str:
    """Main render function - returns full markdown."""
    # Load curated data
    curated = None
    for p in sorted(DATA_DIR.glob(f'curated_{push_id}_*.json'), reverse=True):
        curated = json.loads(p.read_text())
        break
    if not curated:
        curated_path = DATA_DIR / f'curated_{push_id}.json'
        if curated_path.exists():
            curated = json.loads(curated_path.read_text())
    if not curated:
        log.error(f"No curated data found for {push_id}")
        sys.exit(1)

    date_str = datetime.now(CST).strftime('%Y-%m-%d')
    slot_name = SLOT_NAMES.get(push_id, push_id)
    header = f"### Hermes日报 · {date_str}（{slot_name}）"

    sections = []
    for domain in DOMAINS:
        items = curated.get(domain, [])
        sections.append(_generate_section(domain, items, push_id))

    footer = _generate_footer(curated)

    return header + '\n\n\n' + '\n\n\n'.join(sections) + '\n\n\n' + footer


def main():
    import argparse
    parser = argparse.ArgumentParser(description='纯脚本渲染 Markdown 简报（无 LLM）')
    parser.add_argument('--push-id', required=True, choices=['morning', 'noon', 'evening'])
    args = parser.parse_args()

    result = render(args.push_id)
    print(result)


if __name__ == '__main__':
    main()
