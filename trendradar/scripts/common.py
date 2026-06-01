#!/usr/bin/env python3
"""TrendRadar 公共工具 — 追溯号生成 + 解析 + 标记 + RUN_ID contextvar。"""

import uuid, re, os
import contextvars
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, TypedDict

CST = timezone(timedelta(hours=8))

# Python 3.14 contextvars: 子线程自动继承（thread_inherit_context 默认开启）
current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar('run_id', default='')
def gen_run_id(slot: str = "") -> str:
    """生成可读追溯号: YYYYMMDD_slot_短UUID（CST 时区）。"""
    date = datetime.now(CST).strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"{date}_{slot}_{short}" if slot else f"{date}_{short}"


def parse_run_id(run_id: str) -> dict:
    """解析追溯号"""
    parts = run_id.split("_")
    if len(parts) < 2:
        return {"date": parts[0], "slot": "", "uid": ""}
    return {"date": parts[0], "slot": parts[1] if len(parts) > 2 else "", "uid": parts[-1]}


def run_id_marker(run_id: str) -> str:
    """WeCom 不可见追溯标记 — 放在消息末尾"""
    return f"\n\u200b[rid:{run_id}]"  # 零宽空格开头，用户不可见


def set_run_id_ctx(run_id: str):
    """设置 contextvar，子线程自动继承（Python 3.14 thread_inherit_context）。"""
    current_run_id.set(run_id)


def get_run_id_ctx() -> str:
    """获取当前 contextvar 中的 RUN_ID。"""
    return current_run_id.get()

# ── Exit codes (was exitcodes.py, merged into common) ──────────────────
EXIT_SUCCESS = 0        # 成功，有产出
EXIT_NO_CONTENT = 2     # 成功，无新内容（正常，不告警）
EXIT_PARTIAL = 3        # 部分成功（部分 domain 或源失败，推送降级内容）
EXIT_CONFIG_ERROR = 10  # 配置错误（需人工介入）
EXIT_API_ERROR = 11     # API 不可达（自动重试）
EXIT_DB_ERROR = 12      # 数据库损坏（触发自愈）
EXIT_FATAL = 99         # 致命错误（停止管线）

__all__ = ['CST', 'current_run_id', 'gen_run_id', 'parse_run_id',
           'run_id_marker',
           'set_run_id_ctx', 'get_run_id_ctx',
           'EXIT_SUCCESS', 'EXIT_NO_CONTENT', 'EXIT_PARTIAL',
           'EXIT_CONFIG_ERROR', 'EXIT_API_ERROR', 'EXIT_DB_ERROR', 'EXIT_FATAL',
           'STOP_WORDS', 'list_curated_files', 'find_curated_file',
           'get_data_dir_for_common', 'PipelineItem']


# ═══════════════════════════════════════════════════════════════════════════════
# PipelineItem TypedDict — data contract for items flowing through the pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class PipelineItem(TypedDict, total=False):
    """Data contract documenting internal underscore-prefixed fields.

    All fields are optional (total=False) since different pipeline stages
    populate different subsets.
    """
    title: str
    summary: str
    source_platform: str
    source_url: str
    _likely_domain: Optional[str]
    _drop: bool
    _coverage_count: int
    _coverage_platforms: list[str]
    _heat: Optional[dict]
    _needs_search: bool
    _curator_scores: Optional[dict]
    _diversity_penalized: bool
    _is_blog: bool
    _track: Optional[str]


# ═══════════════════════════════════════════════════════════════════════════════
# Shared stop words — combined superset from curate_and_push + aggregate_monthly
# ═══════════════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════════════
# Shared data directory resolution (lazy import to avoid circular deps)
# ═══════════════════════════════════════════════════════════════════════════════

_data_dir_cache: Optional[Path] = None
_data_dir_lock = threading.Lock()


def get_data_dir_for_common() -> Path:
    """Return DATA_DIR, caching the first call.

    Avoids import-time side effects (the underlying get_data_dir may load
    settings which does I/O).  Multiple callers get the same cached value.
    """
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache
    with _data_dir_lock:
        if _data_dir_cache is not None:
            return _data_dir_cache
        from trendradar.scripts.file_utils import get_data_dir
        _data_dir_cache = get_data_dir()
        return _data_dir_cache


# ═══════════════════════════════════════════════════════════════════════════════
# list_curated_files — extracted from blind_spot_audit + aggregate_monthly
# ═══════════════════════════════════════════════════════════════════════════════

def list_curated_files(days: int) -> list[str]:
    """List curated JSON files within the last N days.

    Returns sorted list of absolute file paths.
    """
    data_dir = get_data_dir_for_common()
    cutoff = datetime.now(CST) - timedelta(days=days)
    files = []
    for f in os.listdir(str(data_dir)):
        if not f.startswith('curated_') or not f.endswith('.json'):
            continue
        fpath = os.path.join(str(data_dir), f)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=CST)
        if mtime >= cutoff:
            files.append(fpath)
    return sorted(files)


# ═══════════════════════════════════════════════════════════════════════════════
# find_curated_file — 3-level fallback extracted from ai_translate + render_markdown
# ═══════════════════════════════════════════════════════════════════════════════

def find_curated_file(date: str, slot: str) -> Optional[Path]:
    """Find a curated JSON file with 3-level fallback.

    Level 1: exact dated file     curated_{slot}_{date}.json
    Level 2: latest dated file    curated_{slot}_*YYYYMMDD*.json
    Level 3: generic file         curated_{slot}.json

    Args:
        date: YYYYMMDD date string.
        slot: push slot name (e.g. 'morning', 'noon', 'evening').

    Returns:
        Path if found, None otherwise.
    """
    data_dir = get_data_dir_for_common()

    # Level 1: exact dated file
    curated_path = data_dir / f'curated_{slot}_{date}.json'
    if curated_path.exists():
        return curated_path

    # Level 2: latest dated version
    dated_files = sorted(
        data_dir.glob(f'curated_{slot}_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json'),
        reverse=True,
    )
    if dated_files:
        return dated_files[0]

    # Level 3: generic version
    curated_path = data_dir / f'curated_{slot}.json'
    if curated_path.exists():
        return curated_path

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# _parse_line_pairs — shared API response parser extracted from ai_translate
# ═══════════════════════════════════════════════════════════════════════════════

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
        if title_cn.startswith(('---', '===')):
            continue
        results.append((title_cn, summary_cn))

    while len(results) < num_items:
        results.append((fallback_label, fallback_label))
    results = results[:num_items]

    return results


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
