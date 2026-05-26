#!/usr/bin/env python3
from trendradar.scripts.settings import get_logger
log = get_logger('push-slot-detect')
"""读取 timeline.yaml，检测当前时段并输出路由参数。
容忍 ±1 分钟误差，避免 cron 启动延迟导致 NO_SLOT。

v2.0: 新增 IO 预取支持
  --minutes-until  输出距离下个 slot 的分钟数（用于预取决策）
  --next-slot      输出下个 slot 的名称和时间
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import json
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


def find_next_slot(now_h: int, now_m: int) -> tuple | None:
    """Find the next upcoming slot from current time. Returns ((sh, sm), key, cfg) or None."""
    now_minutes = now_h * 60 + now_m
    best = None
    best_delta = float('inf')

    for (sh, sm), (key, cfg) in slots.items():
        slot_minutes = sh * 60 + sm
        if slot_minutes > now_minutes:
            delta = slot_minutes - now_minutes
            if delta < best_delta:
                best_delta = delta
                best = ((sh, sm), key, cfg, delta)

    return best


# ── Handle special modes ─────────────────────────────────────
if '--minutes-until' in sys.argv:
    next_slot = find_next_slot(h, m)
    if next_slot:
        (sh, sm), key, cfg, delta = next_slot
        print(delta)
    else:
        # No more slots today — return large number
        print(1440)
    sys.exit(0)

if '--next-slot' in sys.argv:
    next_slot = find_next_slot(h, m)
    if next_slot:
        (sh, sm), key, cfg, delta = next_slot
        print(json.dumps({
            "slot": key,
            "time": f"{sh:02d}:{sm:02d}",
            "minutes_until": delta,
            "prefetch_recommended": delta <= 5,
        }, ensure_ascii=False))
    else:
        print(json.dumps({"slot": None, "minutes_until": 1440,
                          "prefetch_recommended": False}, ensure_ascii=False))
    sys.exit(0)

# ── Normal mode: detect current slot ─────────────────────────

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
