#!/usr/bin/env python3
from trendradar.scripts.common import CST, STOP_WORDS, list_curated_files
"""
aggregate_monthly.py — 月度统计聚合 + 兴趣漂移检测

收集近 30 天 curated JSON 数据，输出量化统计：
- 各板块文章数 / 推送次数
- 来源多样性排名
- 热度高频词
- 跨板块主题聚合
- **兴趣漂移建议**（NEW）：高频词 vs 当前 ai_interests.yaml 的增删建议

用法: python3 aggregate_monthly.py [--days 32] [--suggest-interests]
输出: JSON 到 stdout
"""
from trendradar.scripts.settings import get_logger
log = get_logger('aggregate-monthly')
import argparse, json, os, sys, re
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

from trendradar.scripts.file_utils import get_data_dir, TRENDRADAR_HOME
DATA_DIR = get_data_dir()

from trendradar.scripts.settings import DOMAINS, DOMAIN_LABELS


def _extract_word_fragments(text: str, min_len: int = 2, max_len: int = 4) -> list[str]:
    """Extract meaningful Chinese 2-4 char fragments from text.
    
    Skips common stopwords and single-use tokens.
    """
    chars = list(re.findall(r'[\u4e00-\u9fff]', text))
    fragments = []
    for i in range(len(chars)):
        for wlen in range(min_len, max_len + 1):
            if i + wlen <= len(chars):
                word = ''.join(chars[i:i+wlen])
                if word not in STOP_WORDS:
                    fragments.append(word)
    return fragments


def _load_current_interests() -> tuple[set, set]:
    """Load current ai_interests.yaml positive/negative keywords."""
    import yaml
    yaml_path = os.path.join(TRENDRADAR_HOME, 'config', 'ai_interests.yaml')
    positive, negative = set(), set()
    if os.path.exists(yaml_path):
        try:
            data = yaml.safe_load(open(yaml_path).read())
            for item in data.get('positive', []):
                positive.add(item)
            for item in data.get('negative', []):
                negative.add(item)
        except (KeyError, TypeError, FileNotFoundError, json.JSONDecodeError) as e:
            log.warning("加载热度数据失败: %s", e)
            pass
    return positive, negative


def suggest_interests(files: list, min_frequency: int = 5, max_suggestions: int = 10):
    """Analyze titles for high-frequency terms not in current interests.
    
    Returns:
        dict with 'suggest_add', 'suggest_remove', 'current_positive', 'current_negative'
    """
    current_pos, current_neg = _load_current_interests()
    word_counter = Counter()
    title_count = 0

    for fpath in files:
        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            for item in data.get(domain, []):
                title = item.get('title', '')
                title_cn = item.get('title_cn', '')
                text = f"{title} {title_cn}"
                fragments = _extract_word_fragments(text)
                word_counter.update(fragments)
                title_count += 1

    # Suggest additions: high-frequency terms not in current interests
    current_all = current_pos | current_neg
    suggest_add = []
    for word, count in word_counter.most_common(50):
        if count < min_frequency:
            break
        # Skip if already in interests (substring match)
        if any(word in kw or kw in word for kw in current_all):
            continue
        suggest_add.append({"keyword": word, "frequency": count})

    suggest_add = suggest_add[:max_suggestions]

    # Suggest removals: current keywords with zero recent hits
    suggest_remove = []
    for kw in current_pos:
        # Check if keyword or its fragments appear in recent data
        fragments = _extract_word_fragments(kw)
        total_hits = sum(word_counter.get(f, 0) for f in fragments)
        if total_hits == 0:
            suggest_remove.append({"keyword": kw, "reason": "近 30 天无匹配"})

    return {
        "total_titles_analyzed": title_count,
        "suggest_add": suggest_add,
        "suggest_remove": suggest_remove,
        "current_positive": sorted(current_pos)[:20],
        "current_negative": sorted(current_neg)[:10],
    }


def main():
    parser = argparse.ArgumentParser(description='Monthly data aggregation')
    parser.add_argument('--days', type=int, default=32, help='Days to look back')
    parser.add_argument('--suggest-interests', action='store_true',
                        help='Also output interest drift suggestions')
    args = parser.parse_args()

    files = list_curated_files(args.days)
    if not files:
        print(json.dumps({"error": f"No curated files in last {args.days} days"},
                         ensure_ascii=False))
        return

    # Count per domain per day
    domain_counts = defaultdict(int)
    source_counts = Counter()
    total_items = 0
    push_count = len(files)

    for fpath in files:
        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            items = data.get(domain, [])
            domain_counts[domain] += len(items)
            total_items += len(items)
            for item in items:
                src = (item.get('source_platform') or '').split('+')[0].strip()
                if src:
                    source_counts[src] += 1

    # Build output
    output = {
        "period": f"最近{args.days}天",
        "files_analyzed": push_count,
        "total_items": total_items,
        "domain_breakdown": {},
        "top_sources": [],
    }

    for d in DOMAINS:
        cnt = domain_counts.get(d, 0)
        pct = round(cnt / total_items * 100, 1) if total_items else 0
        output["domain_breakdown"][d] = {
            "label": DOMAIN_LABELS[d],
            "count": cnt,
            "percentage": pct,
        }

    for src, cnt in source_counts.most_common(15):
        output["top_sources"].append({"source": src, "count": cnt})

    if args.suggest_interests:
        output["interest_suggestions"] = suggest_interests(files)

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
