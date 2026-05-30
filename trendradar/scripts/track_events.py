#!/usr/bin/env python3
from trendradar.scripts.common import CST
"""TrendRadar 事件跟踪 — 跨日比对热度变化。
比较今天与昨天早报的精选数据，标记：新事件/热度上升/事件进展/热度下降。

用法: python3 track_events.py --today curated_morning.json --yesterday curated_20260519.json
输出: JSON 内含每条的 track 标记
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from trendradar.scripts.heat_tracker import make_fingerprint as fingerprint

from trendradar.scripts.settings import get_data_dir
DATA_DIR = get_data_dir()


def load_curated(path: str) -> list:
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    items = []
    from trendradar.scripts.settings import DOMAINS
    for domain in DOMAINS:
        for item in data.get(domain, []):
            item['_domain'] = domain
            items.append(item)
    return items


def compute_heat(item: dict) -> float:
    """综合热度分：覆盖平台数 + 权威分 + 时效分"""
    cov = item.get('_heat', {}).get('platform_count', 0)
    score = item.get('_curator_scores', {}).get('total', 0)
    return cov * 2 + score  # 平台覆盖权重更高


def compare(today_items: list, yesterday_items: list) -> dict:
    today_fps = {}
    for item in today_items:
        fp = fingerprint(item.get('title', ''), item.get('url', ''))
        if fp:
            today_fps[fp] = item

    yesterday_fps = {}
    for item in yesterday_items:
        fp = fingerprint(item.get('title', ''), item.get('url', ''))
        if fp:
            yesterday_fps[fp] = item

    new_events = []       # 昨日没有，今日新增
    hot_rising = []       # 两天都有，热度上升
    progressed = []       # 事件有新进展（标题变化/概要增加）
    hot_falling = []      # 两天都有，热度下降
    continued = []        # 两天都有，热度持平

    for fp, item in today_fps.items():
        if fp not in yesterday_fps:
            item['_track'] = 'new'
            new_events.append(item)
        else:
            y_item = yesterday_fps[fp]
            today_heat = compute_heat(item)
            yesterday_heat = compute_heat(y_item)
            diff = today_heat - yesterday_heat

            # 检测事件进展：标题长度增加/新增内容/来源变化
            t_len = len(item.get('title', ''))
            y_len = len(y_item.get('title', ''))
            t_plat = item.get('source_platform', '')
            y_plat = y_item.get('source_platform', '')

            has_progress = any([
                t_len > y_len + 10,                              # 标题更详细
                item.get('summary', '') and not y_item.get('summary', ''),  # 新增概要
                t_plat and y_plat and t_plat != y_plat,          # 不同来源（多方印证）
            ])

            if has_progress:
                item['_track'] = 'progress'
                item['_prev_title'] = y_item.get('title', '')
                item['_prev_heat'] = yesterday_heat
                progressed.append(item)
            elif diff > 2:
                item['_track'] = 'rising'
                item['_prev_heat'] = yesterday_heat
                hot_rising.append(item)
            elif diff < -2:
                item['_track'] = 'falling'
                item['_prev_heat'] = yesterday_heat
                hot_falling.append(item)
            else:
                item['_track'] = 'continued'
                continued.append(item)

    # 昨日有今日消失的
    yesterday_only = [y_item for fp, y_item in yesterday_fps.items() if fp not in today_fps]

    return {
        'new': new_events,
        'hot_rising': hot_rising,
        'progressed': progressed,
        'hot_falling': hot_falling,
        'continued': continued,
        'yesterday_only': yesterday_only,
        'stats': {
            'today_total': len(today_items),
            'yesterday_total': len(yesterday_items),
            'new_count': len(new_events),
            'rising_count': len(hot_rising),
            'progress_count': len(progressed),
            'falling_count': len(hot_falling),
            'continued_count': len(continued),
            'faded_count': len(yesterday_only),
        }
    }


def find_yesterday_morning() -> str:
    """自动找昨天早报的精选 JSON（带日期后缀的副本）"""
    today = datetime.now(CST).strftime('%Y%m%d')
    yesterday = (datetime.now(CST) - timedelta(days=1)).strftime('%Y%m%d')
    # 主路径：带日期后缀 curated_morning_YYYYMMDD.json
    dated = DATA_DIR / f'curated_morning_{yesterday}.json'
    if dated.exists():
        return str(dated)
    # 兜底：回退到按文件名找最近的 dated 副本（跑丢了一天的场景）
    files = sorted(DATA_DIR.glob('curated_morning_*.json'), reverse=True)
    for f in files:
        fname = f.name
        parts = fname.replace('curated_morning_', '').replace('.json', '')
        if parts.isdigit() and parts != today and parts < today:
            return str(f)
    # 最后兜底：当前文件（会和自己比，但不崩溃）
    fallback = DATA_DIR / 'curated_morning.json'
    if fallback.exists():
        return str(fallback)
    return ''


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='TrendRadar 事件跟踪 — 跨日热度比对')
    parser.add_argument('--today', required=True, help='今日精选 JSON 路径')
    parser.add_argument('--yesterday', default='', help='昨日精选 JSON 路径（留空自动找）')
    parser.add_argument('--output', default='', help='输出路径（留空输出到 stdout）')
    args = parser.parse_args()

    today_path = args.today
    if not Path(today_path).exists():
        today_path = str(DATA_DIR / today_path)

    yesterday_path = args.yesterday or find_yesterday_morning()
    if not yesterday_path or not Path(yesterday_path).exists():
        print(json.dumps({'error': '昨日数据未找到', 'stats': {'today_total': 0}}, ensure_ascii=False))
        sys.exit(0)

    today_items = load_curated(today_path)
    yesterday_items = load_curated(yesterday_path)

    result = compare(today_items, yesterday_items)
    result['yesterday_source'] = yesterday_path

    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"[TRACK] 写入 {args.output}: {result['stats']}")
    else:
        print(output)
