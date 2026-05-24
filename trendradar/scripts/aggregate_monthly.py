#!/usr/bin/env python3
"""
aggregate_monthly.py — 月度统计聚合

收集近 30 天 curated JSON 数据，输出量化统计：
- 各板块文章数 / 推送次数
- 来源多样性排名
- 热度高频词
- 跨板块主题聚合

用法: python3 aggregate_monthly.py
输出: JSON 到 stdout
"""
import argparse, json, os, sys
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

CST = timezone(timedelta(hours=8))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPTS_DIR), 'data')

DOMAINS = ['top_headlines', 'foreign_china', 'tech', 'economy', 'gaming']
DOMAIN_LABELS = {
    'top_headlines': '📰 头条',
    'foreign_china': '🌏 外媒看华',
    'tech': '💻 科技',
    'economy': '📊 经济民生',
    'gaming': '🎮 游戏',
}


def list_recent_files(days: int = 32):
    """List curated JSON files within the last N days."""
    cutoff = datetime.now(CST) - timedelta(days=days)
    files = []
    for f in os.listdir(DATA_DIR):
        if not f.startswith('curated_') or not f.endswith('.json'):
            continue
        fpath = os.path.join(DATA_DIR, f)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=CST)
        if mtime >= cutoff:
            files.append(fpath)
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description='Monthly data aggregation')
    parser.add_argument('--days', type=int, default=32, help='Days to look back')
    args = parser.parse_args()

    files = list_recent_files(args.days)
    if not files:
        print(json.dumps({"error": f"No curated files in last {args.days} days"}, ensure_ascii=False))
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

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
