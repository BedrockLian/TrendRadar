#!/usr/bin/env python3
"""清理 curated JSON 中 [翻译失败] / [外媒] 标记 + 补全中文项空 title_cn。

为 ai_translate 重跑铺路。如果只删 [翻译失败] 字段，ai_translate 会因为
`needs_title = not has_title_cn and bool(title)` 判断把已有的 [翻译失败]
值视为 "已有"，跳过重翻译。**必须彻底删除字段**。

用法:
    python3 clean_failed_translations.py --push-id evening [--date 20260602]
    python3 clean_failed_translations.py --push-id evening --date 20260602 --dry-run

实战: 2026-06-02 22:11 evening 补投时使用，清掉 6 个 [翻译失败] 字段后
ai_translate 重跑 → 6/6 翻译成功，3.3s。
"""
import argparse
import json
import sys
from pathlib import Path

CST = __import__('datetime').timezone(__import__('datetime').timedelta(hours=8))
from datetime import datetime, timezone, timedelta
CST = timezone(timedelta(hours=8))

TR = Path('/home/asus/.hermes/trendradar')
DOMAINS = ['top_headlines', 'foreign_china', 'tech', 'economy', 'gaming']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--push-id', required=True, choices=['morning', 'noon', 'evening'])
    ap.add_argument('--date', default=datetime.now(CST).strftime('%Y%m%d'),
                    help='YYYYMMDD, 默认今天')
    ap.add_argument('--dry-run', action='store_true', help='只统计不写回')
    args = ap.parse_args()

    # 找最新 curated 文件（优先带日期后缀）
    candidates = [
        TR / 'data' / f'curated_{args.push_id}_{args.date}.json',
        TR / 'data' / f'curated_{args.push_id}.json',
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        print(f"ERROR: no curated file for push_id={args.push_id} date={args.date}", file=sys.stderr)
        print(f"  checked: {candidates}", file=sys.stderr)
        sys.exit(1)

    print(f"target: {path}")
    data = json.loads(path.read_text())

    cleared_failed_title = 0
    cleared_external_summary = 0
    filled_chinese = 0
    empty_after = 0

    for domain in DOMAINS:
        for item in data.get(domain, []):
            # 清 [翻译失败] 字段
            t = str(item.get('title_cn', ''))
            if t.startswith('[翻译失败]'):
                if not args.dry_run:
                    del item['title_cn']
                cleared_failed_title += 1
            # 清 [外媒] 标记的 summary_cn（ai_translate 会重生成）
            s = str(item.get('summary_cn', ''))
            if s.startswith('[外媒]'):
                if not args.dry_run:
                    del item['summary_cn']
                cleared_external_summary += 1
            # 补全中文项空 title_cn
            if not item.get('title_cn') and item.get('title', ''):
                # 简单判断：含非 ASCII 字符 = 中文
                if any(ord(c) > 127 for c in item['title']):
                    if not args.dry_run:
                        item['title_cn'] = item['title']
                        item['summary_cn'] = (item.get('summary', '') or '')[:100]
                    filled_chinese += 1
            # 仍空的
            if not item.get('title_cn'):
                empty_after += 1

    print(f"  cleared [翻译失败] title_cn: {cleared_failed_title}")
    print(f"  cleared [外媒] summary_cn:   {cleared_external_summary}")
    print(f"  filled Chinese 项:          {filled_chinese}")
    print(f"  仍空 title_cn:              {empty_after}")

    if args.dry_run:
        print("DRY RUN — 未写回")
    else:
        path.write_text(json.dumps(data, ensure_ascii=False))
        print(f"  写回 {path} ({path.stat().st_size} bytes)")
        print()
        print("下一步:")
        print(f"  cd {TR}")
        print(f"  python3.14t -m trendradar.scripts.ai_translate --push-id {args.push_id}")


if __name__ == '__main__':
    main()
