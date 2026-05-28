#!/usr/bin/env python3
"""
render_markdown.py — 纯脚本渲染 TrendRadar 简报，无需 LLM API。

读取 curated JSON，直接拼接为严格格式化的 Markdown 简报。
格式硬编码，永远一致，零 token 成本。

═══════════════════════════════════════════════════════════════
格式契约（修改此文件也必须遵守以下规则）：
1. 全文无 `---` 横线分隔线
2. 板块标题后跟 `\\n\\n\\n`（2个空行）
3. 条目间用 `\\n\\n\\n` 分隔（2个空行）
4. 条目内部：标题 + \\n\\n + 摘要（50字内，完整句子） + \\n\\n + 链接（各1个空行）
5. 链接格式：[【媒体名】](url)，媒体名本身可点击
6. 尾注跟 \\n\\n 单空行
7. 禁止 LLM 改写输出——本脚本的输出即最终简报
═══════════════════════════════════════════════════════════════

用法: python3 render_markdown.py --push-id morning|noon|evening
输出: Markdown 简报到 stdout，兼容 fragment_push.py 分片
"""
from trendradar.scripts.settings import get_logger
log = get_logger('render-markdown')

import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
from trendradar.scripts.settings import get_data_dir, DOMAINS, DOMAIN_LABELS, SLOT_NAMES

DATA_DIR = get_data_dir()


def _detect_emoji(heat_value, push_id, track=None):
    """Detect emoji prefix based on heat/track status."""
    # Evening recap items (track_events sets 'new'/'continued'/'progress')
    if push_id == 'evening' and track and (track.endswith('_recap') or track in ('continued', 'progress', 'falling')):
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
    """Trim text to max_len chars, preserving sentence boundaries.
    
    Never produces broken sentences (断句): if no sentence boundary found
    within range, returns clean text without ellipsis marker.
    """
    import re
    text = re.sub(r'\s+', ' ', text.strip())
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    # 1. Sentence-ending punctuation (preferred)
    for sep in '。。！？?！\n':
        pos = cut.rfind(sep)
        if pos > max_len * 0.6:
            return cut[:pos + 1]
    # 2. Clause boundary (逗号)
    pos = cut.rfind('，')
    if pos > max_len * 0.4:
        return cut[:pos + 1]
    # 3. Space (English word boundary)
    pos = cut.rfind(' ')
    if pos > max_len * 0.4:
        return cut[:pos]
    # 4. Clean truncation — no ellipsis, no broken-sentence marker
    return cut.rstrip()


def _format_item(idx, item, push_id):
    """Format a single item.

    WeCom format:
      🆕 N. **标题**
      \n\n摘要（截断150字，句号边界）
      \n\n[查看原文](url)【来源】

    Each line pair separated by single blank line (\n\n).
    """
    title = _shorten(item.get('title_cn') or item.get('title') or '', 80)
    summary = _shorten(item.get('summary_cn') or item.get('summary') or '', 50)
    url = (item.get('url') or '').strip()
    # 防御性清洗 URL：移除空格（agent 可能错误插入）、确保格式正确
    url = url.replace(' ', '').replace('　', '')
    source = (item.get('source_platform') or '').split('+')[0].strip()
    heat = item.get('_heat')
    track = item.get('_track') if push_id == 'evening' else None
    emoji = _detect_emoji(heat, push_id, track)

    lines = [f"{emoji} {idx}. **{title}**"]

    if summary:
        lines.append(summary)

    link = f"[【{source}】]({url})" if url and source else ""
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
    # Archive: save pure markdown to archive/YYYY-MM-DD/{slot}.md for resend
    archive_dir = Path(get_data_dir()).parent / 'archive' / today_display
    archive_path = archive_dir / f'{push_id}.md'
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path.write_text(output, encoding='utf-8')
        log.info(f"Archived to {archive_path}")
    except OSError as e:
        log.warning(f'存档写入失败 {archive_path}: {e}')

    sys.stdout.write(output)


if __name__ == '__main__':
    main()
