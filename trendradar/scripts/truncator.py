"""Source diversity truncation — per-slot caps and global source limits."""

from collections import Counter

from trendradar.scripts.settings import (
    DOMAINS, BRIEFING_RATIO, MAX_SOURCE_PCT
)


def apply_truncation(result: dict, push_id: str):
    """per-slot 总量截断 + 全局来源多样性上限。"""
    _MAX_SOURCE_PCT = MAX_SOURCE_PCT

    # 全局来源多样性上限
    all_sources = Counter()
    for d in DOMAINS:
        for item in result.get(d, []):
            src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
            if src:
                all_sources[src] += 1
    total = result['total']
    for src, count in all_sources.most_common():
        if total > 0 and count / total > _MAX_SOURCE_PCT:
            to_remove = count - int(total * _MAX_SOURCE_PCT)
            src_items = []
            for d in DOMAINS:
                for i, item in enumerate(result.get(d, [])):
                    item_src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
                    if item_src == src:
                        score = item.get('_curator_scores', {}).get('total', 0)
                        src_items.append((score, d, i))
            src_items.sort()
            removed = 0
            for score, domain, idx in reversed(src_items):
                if removed >= to_remove:
                    break
                del result[domain][idx]
                removed += 1
                total -= 1

    # per-slot 总量截断
    max_total = BRIEFING_RATIO.get(push_id, 30)
    if result['total'] > max_total:
        non_headline = result['total'] - len(result.get('top_headlines', []))
        remaining = max_total - len(result.get('top_headlines', []))
        if remaining < 0:
            result['top_headlines'] = result['top_headlines'][:max_total]
            for d in DOMAINS:
                if d != 'top_headlines':
                    result[d] = []
        elif remaining < non_headline:
            for d in ['tech', 'gaming', 'economy', 'foreign_china']:
                keep = max(1, int(len(result[d]) / non_headline * remaining))
                result[d] = result[d][:keep]
                remaining -= keep
                if remaining <= 0:
                    break
        result['truncated'] = True
        result['total'] = sum(len(result[d]) for d in DOMAINS)
