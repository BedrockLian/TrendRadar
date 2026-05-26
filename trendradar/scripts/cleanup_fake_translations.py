#!/usr/bin/env python3
"""清理假翻译：移除 title_cn == title 或 summary_cn == summary 的伪翻译条目"""
import json
import sys
from pathlib import Path

# 动态发现 data 目录
DATA_DIR = Path("/home/asus/.hermes/trendradar/data")
if not DATA_DIR.exists():
    print(f"ERROR: data dir not found: {DATA_DIR}", file=sys.stderr)
    sys.exit(1)

count = 0
files_checked = 0
files_changed = 0

for f in sorted(DATA_DIR.glob('curated_*.json')):
    files_checked += 1
    data = json.loads(f.read_text())
    changed = False
    for domain in ['top_headlines', 'foreign_china', 'tech', 'economy', 'gaming']:
        for item in data.get(domain, []):
            # 清理 title_cn 假翻译
            tc = item.get('title_cn')
            t = item.get('title')
            if tc and t and tc == t:
                item.pop('title_cn', None)
                changed = True
                count += 1
            # 清理 summary_cn 假翻译
            sc = item.get('summary_cn')
            s = item.get('summary')
            if sc and s and sc == s:
                item.pop('summary_cn', None)
                changed = True
                count += 1
    if changed:
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        files_changed += 1

print(f"Checked: {files_checked} files")
print(f"Changed: {files_changed} files")
print(f"Cleaned: {count} fake translations")
