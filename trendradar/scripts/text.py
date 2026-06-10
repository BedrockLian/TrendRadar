"""text.py — 文本处理工具 (Sprint 2 P1-14)

从 common.py 拆出。
"""
import re

# ── Stop words (combined from curate_and_push + aggregate_monthly) ─
STOP_WORDS: frozenset[str] = frozenset({
    # Original set from curate_and_push.py
    '关注', '我关注', '特别是', '尤其是', '方面', '方向', '影响', '变化',
    '竞争', '进展', '动态', '格局', '政策', '领域', '情况', '调整',
    '战略', '应用', '落地', '态势', '热点', '赛道', '曲线',
    '部署', '突破', '升级', '趋势', '市场', '产业', '发展', '推动',
    '提升', '分析', '报告', '状况', '环节', '相关', '就是',
    '不会', '还是', '可以', '这个', '那个', '什么', '怎么', '因为',
    '所以', '如果', '但是', '而且', '或者', '虽然', '由于', '关于',
    '基于', '通过', '采用', '进行', '开始', '继续', '实现', '成为',
    '带来', '加大', '进入', '超过', '达到', '保持', '构成', '形成',
    '新闻', '游戏', '体育', '行业', '重大', '娱乐', '明星',
    # Additional from aggregate_monthly.py
    '目前', '正在', '已经', '主要', '其中', '以及', '可能', '需要',
    '表示', '认为', '指出', '预计', '显示', '公布', '宣布',
    '数据', '同比', '环比', '增长', '下降', '此外',
    '一些', '这种', '一种', '所有', '这些', '那些',
})


def _write_anchored(
    results: list[tuple[str, str] | None],
    idx: int,
    collected: list[str],
    fallback_label: str,
):
    """Write collected lines into results[idx] as (title, summary)."""
    if idx < 0 or idx >= len(results):
        return  # out of bounds, skip
    title = collected[0] if len(collected) > 0 else fallback_label
    summary = collected[1] if len(collected) > 1 else fallback_label
    results[idx] = (title, summary)


def _parse_line_pairs(
    raw_content: str,
    num_items: int,
    fallback_label: str = "[处理失败]",
) -> list[tuple[str, str]]:
    """Parse AI API response into (title, summary) pairs.

    Two strategies:
    1. Index-anchored — looks for 'Item N:' markers in the response and
       maps each marker to the correct position by index. Prevents item
       misalignment when AI reorders or skips items.
    2. Sequential (fallback) — pairs lines sequentially as (title, summary),
       strips numbering prefixes, pads/truncates. Legacy compat.

    Args:
        raw_content: Raw response text from AI API.
        num_items: Expected number of items.
        fallback_label: Label used for missing items, e.g. '[翻译失败]', '[扩写失败]'.

    Returns:
        List of (title, summary) tuples with exactly num_items entries.
    """
    raw_lines = [l.strip() for l in raw_content.split('\n')]

    # ── Strategy 1: Index-anchored parsing ──────────────────────────────
    # Look for 'Item N:' or '[N]' markers at line start
    anchored_results: list[tuple[str, str] | None] = [None] * num_items
    found_anchor = False
    current_idx: int | None = None
    collected: list[str] = []

    for l in raw_lines:
        # Check for anchor markers: 'Item N:', '[N]', or '【N】'
        m = re.match(r'^Item\s+(\d+)[:：]?\s*$', l)
        if not m:
            m = re.match(r'^\[(\d+)\]\s*$', l)
        if not m:
            m = re.match(r'^【(\d+)】\s*$', l)

        if m:
            found_anchor = True
            # Flush previous item if we were collecting
            if current_idx is not None and collected:
                _write_anchored(anchored_results, current_idx, collected, fallback_label)
            current_idx = int(m.group(1)) - 1  # convert to 0-based
            collected = []
            continue

        if current_idx is not None:
            # Skip blank lines and commentary between items
            if not l:
                continue
            if l.startswith(('Here', 'The following', 'Below', 'Note:', '以上是',
                             '---', '===')):
                continue
            # Strip TITLE:/SUMMARY: prefixes (AI may mimic input format)
            if l.upper().startswith('TITLE:'):
                l = l[6:].strip()
            elif l.upper().startswith('SUMMARY:'):
                l = l[8:].strip()
            elif l.upper().startswith('REWRITTEN TITLE:'):
                l = l[16:].strip()
            elif l.upper().startswith('REWRITTEN SUMMARY:'):
                l = l[18:].strip()
            if not l:
                continue
            collected.append(l)

    # Flush last item
    if current_idx is not None and collected:
        _write_anchored(anchored_results, current_idx, collected, fallback_label)

    if found_anchor:
        # Fill any gaps with fallback
        for i in range(num_items):
            if anchored_results[i] is None:
                anchored_results[i] = (fallback_label, fallback_label)
        return anchored_results  # type: ignore[return-value]

    # ── Strategy 2: Sequential pairing (backward compat) ────────────────
    lines = []
    for l in raw_lines:
        if not l:
            continue
        if l.startswith(('Here', 'The following', 'Below', 'Note:', '以上是')):
            continue
        lines.append(l)

    results = []
    for i in range(0, len(lines), 2):
        title_cn = lines[i] if i < len(lines) else fallback_label
        summary_cn = lines[i + 1] if i + 1 < len(lines) else fallback_label
        title_cn = re.sub(r'^[\［\（\(]?\d+[\］\）\)]?[.、．\s]*', '', title_cn).strip()
        summary_cn = re.sub(r'^[\［\（\(]?\d+[\］\）\)]?[.、．\s]*', '', summary_cn).strip()
        # Strip REWRITTEN TITLE/SUMMARY prefixes
        for prefix in ('REWRITTEN TITLE:', 'TITLE:'):
            if title_cn.upper().startswith(prefix):
                title_cn = title_cn[len(prefix):].strip()
        for prefix in ('REWRITTEN SUMMARY:', 'SUMMARY:'):
            if summary_cn.upper().startswith(prefix):
                summary_cn = summary_cn[len(prefix):].strip()
        if title_cn.startswith(('---', '===')):
            continue
        results.append((title_cn, summary_cn))

    while len(results) < num_items:
        results.append((fallback_label, fallback_label))
    results = results[:num_items]

    return results
