#!/usr/bin/env python3
from trendradar.scripts.settings import get_logger
log = get_logger('push-slot-detect')
"""读取 timeline.yaml，检测当前时段并输出路由参数。
容忍 ±1 分钟误差，避免 cron 启动延迟导致 NO_SLOT。"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import yaml

CST = timezone(timedelta(hours=8))
TIMELINE_PATH = Path(__file__).resolve().parent.parent / 'config' / 'timeline.yaml'

now = datetime.now(CST)
h, m = now.hour, now.minute

def slot_match(target_h, target_m, h, m):
    delta = (h * 60 + m) - (target_h * 60 + target_m)
    return -1 <= delta <= 1

# 读取 timeline.yaml
if not TIMELINE_PATH.exists():
    log.info('timeline.yaml not found')
    print('NO_SLOT')
    sys.exit(1)

timeline = yaml.safe_load(TIMELINE_PATH.read_text())
slots_cfg = timeline.get('slots', {})

# 构建 slots 查找表
slots = {}
for key, cfg in slots_cfg.items():
    parts = str(cfg.get('time', '')).strip().split(':')
    if len(parts) == 2:
        sh, sm = int(parts[0]), int(parts[1])
        slots[(sh, sm)] = (key, cfg)

found = None
for (sh, sm), (key, cfg) in slots.items():
    if slot_match(sh, sm, h, m):
        found = (sh, sm, key, cfg)
        break

if not found:
    now_minutes = h * 60 + m
    closest = min(slots.keys(), key=lambda t: abs(t[0]*60 + t[1] - (h*60+m)))
    delta = abs(closest[0]*60 + closest[1] - now_minutes)
    closest_minutes = closest[0]*60 + closest[1]
    if delta <= 10 and now_minutes >= closest_minutes:
        key, cfg = slots[closest]
        found = (closest[0], closest[1], key, cfg)
        log.info(f"偏离 {delta} 分钟, fallback 到 {cfg.get('display','')}")

if found:
    sh, sm, key, cfg = found
    dedup_flag = '--dedup' if cfg.get('dedup', False) else ''
    extra = cfg.get('extra', '')
    push_id = key
    filter_method = cfg.get('filter', 'keyword')
    
    print(f'PUSH_ID={push_id}')
    print(f'SLOT_LABEL={cfg.get("display", "")}')
    print(f'DEDUP_FLAG={dedup_flag}')
    print(f'EXTRA={extra}')
    print(f'FILTER={filter_method}')
else:
    print('NO_SLOT')
