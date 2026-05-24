#!/usr/bin/env python3
"""
render_markdown.py — 纯脚本渲染 TrendRadar 简报，无需 LLM API。

读取 curated JSON，直接拼接为严格格式化的 Markdown 简报。
格式硬编码，永远一致，零 token 成本。

用法: python3 render_markdown.py --push-id morning|noon|evening
输出: Markdown 简报到 stdout，兼容 fragment_push.py 分片
"""
from settings import get_logger
log = get_logger('render-markdown')

import json, sys
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
from settings import get_data_dir, DOMAINS, DOMAIN_LABELS, SLOT_NAMES

DATA_DIR = get_data_dir()


def _detect_emoji(heat_value, push_id, track=None):
    """Detect emoji prefix based on heat/track status."""
    if push_id == 'evening' and track and track.endswith('_recap'):
        return '🔄'
    if heat_value:
        if isinstance(heat_value, dict):
            apps = heat_value.get('appearances', 0)
            if apps >= 2:
                return '🔥'
            score = heat_value.get('heat_score', 0)
            if score >= 0.8:
                return '🔥'
        elif isinstance(heat_value, (int, float)) and heat_value >= 2:
            return '🔥'
    return '🆕'


def _shorten(text, max_len):
    """Trim text to max_len chars, preserving sentence boundaries."""
    text = text.strip().replace('\n', ' ').replace('\r', ' ')
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    for sep in '。。！？?！\n':
        pos = cut.rfind(sep)
        if pos > max_len * 0.6:
            return cut[:pos + 1]
    pos = cut.rfind(' ')
    if pos > max_len * 0.6:
        return cut[:pos] + '…'
    return cut.rstrip() + '…'


def _format_item(idx, item, push_id):
    """Format a single item.

    WeCom format:
      🆕 N. **标题**
      \n\n摘要（截断150字，句号边界）
      \n\n[查看原文](url)【来源】

    Each line pair separated by single blank line (\n\n).
    """
    title = _shorten(item.get('title_cn') or item.get('title') or '', 80)
    summary = _shorten(item.get('summary_cn') or item.get('summary') or '', 150)
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


def _generate_section(domain, items, push_id):
    """Generate a full section with header + items.

    Structure:
      ### 📰 头条
      \n\n\n(2 blank lines)
      🆕 1. **标题**
      ...
      \n\n\n(2 blank lines)
      🆕 2. **标题**
      ...
    """
    if not items:
        return f"### {DOMAIN_LABELS[domain]}\n\n暂无内容"

    header = f"### {DOMAIN_LABELS[domain]}"
    item_blocks = [_format_item(i + 1, item, push_id) for i, item in enumerate(items)]

    # header + 2 blank lines + items joined by 2 blank lines
    return header + '\n\n\n' + '\n\n\n'.join(item_blocks)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Render TrendRadar Markdown briefing')
    parser.add_argument('--push-id', choices=['morning', 'noon', 'evening'], default='morning')
    args = parser.parse_args()

    push_id = args.push_id
    slot_name = SLOT_NAMES.get(push_id, push_id)
    today_display = datetime.now(CST).strftime('%Y-%m-%d')
    today_file = datetime.now(CST).strftime('%Y%m%d')

    # Load curated JSON
    # Try dated file first, then fall back to non-dated
    curated_path = DATA_DIR / f'curated_{push_id}_{today_file}.json'
    if not curated_path.exists():
        curated_path = DATA_DIR / f'curated_{push_id}.json'
    if not curated_path.exists():
        log.error(f"Curated file not found: {curated_path}")
        sys.exit(1)

    data = json.loads(curated_path.read_text(encoding='utf-8'))

    # Extract items per domain from the curated JSON structure
    # Structure: {domain_key: [item_dict, ...], "total": N, ...}
    domain_items = {}
    for domain in DOMAINS:
        domain_items[domain] = data.get(domain, [])

    # Build header with counts per domain
    total = data.get('total', sum(len(v) for v in domain_items.values()))
    counts_parts = []
    for d in DOMAINS:
        count = len(domain_items[d])
        emoji = DOMAIN_LABELS[d].split()[0] if ' ' in DOMAIN_LABELS[d] else ''
        counts_parts.append(f"{emoji}{count}")
    counts_str = '  '.join(counts_parts)

    header = f"### Hermes日报 · {today_display}（{slot_name}）\n\n\n📋 **共 {total} 条** · {counts_str}"

    # Generate sections
    sections = []
    for domain in DOMAINS:
        section = _generate_section(domain, domain_items.get(domain, []), push_id)
        sections.append(section)

    # Footer (only for last fragment in fragment_push.py)
    footer = f"\n📌 *共{total}条 · 自动生成于{today_display} · TrendRadar by Hermes*"

    # Assemble: header + 2 blank lines + sections (each separated by 2 blank lines) + 2 blank lines + footer
    output = header + '\n\n\n' + '\n\n\n'.join(sections) + '\n\n\n' + footer
    sys.stdout.write(output)


if __name__ == '__main__':
    main()
