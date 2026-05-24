#!/usr/bin/env python3
"""
blind_spot_audit.py — 信息茧房盲点检测

扫描最近 N 日 curated JSON，识别：
- _serendipity: true 的意外发现条目
- 板块覆盖率偏差（哪些领域被忽视）
- 来源多样性缺失

用法: python3 blind_spot_audit.py --days 7
输出: 结构化文本报告到 stdout
"""
import argparse, json, os, sys
from datetime import datetime, timezone, timedelta, date
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


def list_curated_files(days: int):
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


def scan_serendipity(files):
    """Extract items with _serendipity: true."""
    results = []
    for fpath in files:
        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            for item in data.get(domain, []):
                if item.get('_serendipity'):
                    results.append({
                        'file': os.path.basename(fpath),
                        'domain': domain,
                        'title': item.get('title', '?'),
                        'summary': (item.get('summary') or '')[:80],
                        'source': item.get('source_platform', '?'),
                    })
    return results


def scan_coverage(files):
    """Count articles per domain across all files."""
    counts = defaultdict(int)
    total = 0
    for fpath in files:
        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            cnt = len(data.get(domain, []))
            counts[domain] += cnt
            total += cnt
    return counts, total


def scan_sources(files):
    """Check source diversity per domain."""
    domain_sources = defaultdict(set)
    for fpath in files:
        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            for item in data.get(domain, []):
                src = (item.get('source_platform') or '').split('+')[0].strip()
                if src:
                    domain_sources[domain].add(src)
    return domain_sources


def main():
    parser = argparse.ArgumentParser(description='Blind spot audit')
    parser.add_argument('--days', type=int, default=7)
    args = parser.parse_args()

    files = list_curated_files(args.days)
    if not files:
        print(f"[INFO] 未找到最近 {args.days} 天的 curated JSON 文件")
        return

    print(f"📊 信息茧房盲点检测 · 最近 {args.days} 天 ({len(files)} 个文件)")
    print()

    # 1. Serendipity items
    serendipity = scan_serendipity(files)
    print(f"## 🌱 意外发现条目 (_serendipity)")
    if serendipity:
        for item in serendipity:
            print(f"  - [{item['domain']}] {item['title']}")
            print(f"    来源: {item['source']} | 摘要: {item['summary']}")
    else:
        print(f"  无 _serendipity=True 条目（可能未启用标记）")
    print()

    # 2. Domain coverage
    counts, total = scan_coverage(files)
    print(f"## 📐 板块覆盖率 (总计 {total} 条)")
    target_pct = {'top_headlines': 18, 'foreign_china': 18, 'tech': 22, 'economy': 22, 'gaming': 20}
    for domain in DOMAINS:
        cnt = counts.get(domain, 0)
        pct = round(cnt / total * 100, 1) if total else 0
        target = target_pct.get(domain, 20)
        status = '✅' if abs(pct - target) <= 8 else ('⚠️' if abs(pct - target) <= 15 else '❌')
        print(f"  {status} {DOMAIN_LABELS[domain]}: {cnt}条 ({pct}%) 目标约{target}%")
    print()

    # 3. Source diversity
    sources = scan_sources(files)
    print(f"## 🔀 来源多样性")
    for domain in DOMAINS:
        srcs = sources.get(domain, set())
        label = DOMAIN_LABELS[domain]
        if len(srcs) >= 3:
            print(f"  ✅ {label}: {len(srcs)} 个来源 → {', '.join(sorted(srcs)[:5])}")
        elif len(srcs) >= 1:
            print(f"  ⚠️ {label}: 仅 {len(srcs)} 个来源 → {', '.join(sorted(srcs))}")
        else:
            print(f"  ❌ {label}: 无来源数据")
    print()

    # 4. Coverage gap summary
    print(f"## 🔍 盲点总结")
    low_coverage = [d for d in DOMAINS if counts.get(d, 0) / total * 100 < 10]
    if low_coverage:
        for d in low_coverage:
            print(f"  ⚠️ {DOMAIN_LABELS[d]} 覆盖率低于 10%")
    print(f"  无其他显著盲点")


if __name__ == '__main__':
    main()
