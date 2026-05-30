#!/usr/bin/env python3
from trendradar.scripts.common import CST, list_curated_files
"""
blind_spot_audit.py — 信息茧房盲点检测

扫描最近 N 日 curated JSON，识别：
- _serendipity: true 的意外发现条目
- 板块覆盖率偏差（哪些领域被忽视）
- 来源多样性缺失

用法: python3 blind_spot_audit.py --days 7
输出: 结构化文本报告到 stdout
"""
import argparse, json, os, sys, re
from datetime import datetime, timezone, timedelta, date
from collections import Counter, defaultdict

from trendradar.scripts.file_utils import get_data_dir
DATA_DIR = get_data_dir()

from trendradar.scripts.settings import DOMAINS, DOMAIN_LABELS


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
    parser.add_argument('--json', action='store_true',
                        help='Output machine-readable JSON (for self-healing integration)')
    parser.add_argument('--coverage-threshold', type=float, default=10.0,
                        help='Coverage percentage threshold for alerts (default: 10%%)')
    parser.add_argument('--output-penalty', type=str, default=None,
                        help='Output source penalty JSON file for curator consumption')
    parser.add_argument('--update-health', action='store_true',
                        help='Update data/source_health.json with quality scores')
    args = parser.parse_args()

    files = list_curated_files(args.days)
    
    if args.json:
        # Machine-readable mode — for self-healing / automation
        counts, total = scan_coverage(files)
        sources = scan_sources(files)
        coverage_pct = {}
        for d in DOMAINS:
            cnt = counts.get(d, 0)
            pct = round(cnt / total * 100, 1) if total else 0
            coverage_pct[d] = {
                "label": DOMAIN_LABELS[d],
                "count": cnt,
                "percentage": pct,
            }
        
        low_coverage = [
            d for d in DOMAINS
            if counts.get(d, 0) / total * 100 < args.coverage_threshold
        ] if total > 0 else DOMAINS
        
        print(json.dumps({
            "files_analyzed": len(files),
            "total_items": total,
            "coverage": coverage_pct,
            "low_coverage_domains": low_coverage,
            "source_diversity": {d: len(s) for d, s in sources.items()},
            "warnings": [
                f"{DOMAIN_LABELS[d]} 覆盖率 {coverage_pct[d]['percentage']}% < {args.coverage_threshold}%"
                for d in low_coverage
            ] if low_coverage else [],
        }, ensure_ascii=False, indent=2))
        return
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

    # ── Output penalty file for curator consumption ──────────────
    if args.output_penalty:
        _write_penalty_file(args, files, counts, total, sources)

    # ── Update source health ───────────────────────────────────
    if args.update_health:
        _update_source_health(files, sources, total)


def _write_penalty_file(args, files, counts, total, sources):
    """Generate a source penalty JSON for curate_and_push to consume.
    
    Rules:
    - Source appearing in >20% of articles in a domain → authority penalty
    - Penalty factor: 1.0 (no penalty) → 0.5 (half authority)
    """
    if total == 0:
        return
    
    # Count per-source appearances
    source_counts = Counter()
    for fpath in files:
        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            for item in data.get(domain, []):
                src = (item.get('source_platform') or '').split('+')[0].strip()
                if src:
                    source_counts[src] += 1
    
    # Calculate penalties
    OVERREP_THRESHOLD = 0.20  # 20% of total
    penalties = {}
    for src, cnt in source_counts.most_common():
        ratio = cnt / total
        if ratio > OVERREP_THRESHOLD:
            # Penalty: linear from 1.0 (at 20%) to 0.5 (at 40%+)
            penalty = max(0.5, 1.0 - (ratio - OVERREP_THRESHOLD) * 2.5)
            penalties[src] = round(penalty, 2)
    
    output = {
        "generated_at": datetime.now(CST).isoformat(),
        "period_days": args.days,
        "total_items": total,
        "overrepresented_sources": [
            {"source": src, "count": source_counts[src],
             "percentage": round(source_counts[src] / total * 100, 1),
             "penalty_factor": factor}
            for src, factor in sorted(penalties.items(), key=lambda x: x[1])
        ],
    }
    
    from trendradar.scripts.file_utils import atomic_write_json
    atomic_write_json(Path(args.output_penalty), output)
    
    print(f"[PENALTY] Written {len(penalties)} source penalties to {args.output_penalty}",
          file=sys.stderr if not args.json else None)


def _update_source_health(files, sources, total):
    """Update data/source_health.json with per-source quality metrics.

    Tracks:
    - appearance_count: total times this source appears in data
    - curated_count: times it appeared in curated results (passing score filter)
    - curated_ratio: curated / appearance (low ratio → source may be declining)
    - last_seen: most recent curation date
    - health_score: 0-100, composite quality score
    """
    if total == 0:
        return

    health_path = os.path.join(DATA_DIR, 'source_health.json')

    # Load existing health data
    existing = {}
    if os.path.exists(health_path):
        try:
            with open(health_path) as f:
                data = json.load(f)
                existing = data.get('sources', {})
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[blind_spot] 加载现有分析数据失败: {e}", file=sys.stderr)
            pass

    # Count appearances and curated appearances
    appearance_counts = Counter()
    curated_counts = Counter()
    last_seen_dates = {}

    for fpath in files:
        fname = os.path.basename(fpath)
        # Extract date from filename: curated_morning_20260525.json
        date_match = re.search(r'(\d{8})', fname)
        file_date = date_match.group(1) if date_match else 'unknown'

        with open(fpath, 'r') as f:
            data = json.load(f)
        for domain in DOMAINS:
            for item in data.get(domain, []):
                src = (item.get('source_platform') or '').split('+')[0].strip()
                if not src:
                    continue
                appearance_counts[src] += 1
                # Check if curated (has score)
                if item.get('_curator_scores', {}).get('pass'):
                    curated_counts[src] += 1
                last_seen_dates[src] = file_date

    # Merge with existing and calculate health scores
    updated = {}
    for src in set(list(appearance_counts.keys()) + list(existing.keys())):
        hist = existing.get(src, {})
        hist_appearances = hist.get('total_appearances', 0)
        hist_curated = hist.get('total_curated', 0)

        total_appearances = hist_appearances + appearance_counts.get(src, 0)
        total_curated = hist_curated + curated_counts.get(src, 0)

        curated_ratio = (total_curated / total_appearances * 100) if total_appearances > 0 else 0

        # Health score: 0-100
        # - Base 50
        # - +curated_ratio (up to +30)
        # - +source diversity bonus (up to +10)
        # - -penalty for never curated (up to -30)
        health = 50
        health += min(curated_ratio * 0.6, 30)  # curated ratio bonus
        src_diversity = len(sources.get(src, set())) if src in sources else 1
        health += min(src_diversity * 2, 10)     # diversity bonus

        if total_appearances > 10 and total_curated == 0:
            health -= 30  # never curated despite high volume

        health = max(0, min(100, int(health)))
        status = 'healthy' if health >= 60 else ('degrading' if health >= 30 else 'failing')

        updated[src] = {
            'total_appearances': total_appearances,
            'total_curated': total_curated,
            'curated_ratio': round(curated_ratio, 1),
            'last_seen': last_seen_dates.get(src, hist.get('last_seen', '')),
            'health_score': health,
            'status': status,
        }

    output = {
        'version': 2,
        'updated_at': datetime.now(CST).isoformat(),
        'total_sources_tracked': len(updated),
        'sources': updated,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    from trendradar.scripts.file_utils import atomic_write_json
    atomic_write_json(Path(health_path), output)

    failing = [s for s, d in updated.items() if d['status'] == 'failing']
    if failing:
        print(f"[HEALTH] {len(failing)} sources marked as failing: {', '.join(failing[:5])}",
              file=sys.stderr)


if __name__ == '__main__':
    main()
