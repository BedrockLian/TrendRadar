#!/usr/bin/env python3
"""读取 timeline.yaml，检测当前时段并输出路由参数。
容忍 ±1 分钟误差，避免 cron 启动延迟导致 NO_SLOT。

Functions:
  detect_current_slot() -> dict | None  主入口（供 pipeline 直接调用）
  find_next_slot(now_h, now_m) -> tuple | None
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import json
import yaml
import os as _os

from trendradar.scripts.common import CST
from trendradar.scripts.settings import get_logger
log = get_logger('push-slot-detect')

_TIMELINE_DIR = Path(_os.environ.get('TRENDRADAR_HOME', Path(__file__).resolve().parent.parent))
TIMELINE_PATH = _TIMELINE_DIR / 'config' / 'timeline.yaml'


def slot_match(target_h, target_m, now_h, now_m):
    """Check if current time is within ±1 minute of target (minute-precision)."""
    delta = (now_h * 60 + now_m) - (target_h * 60 + target_m)
    return -1 <= delta <= 1


def _load_slots() -> dict:
    """Load and parse timeline.yaml slots."""
    if not TIMELINE_PATH.exists():
        return {}
    timeline = yaml.safe_load(TIMELINE_PATH.read_text(encoding='utf-8'))
    slots_cfg = timeline.get('slots', {})
    slots = {}
    for key, cfg in slots_cfg.items():
        parts = str(cfg.get('time', '')).strip().split(':')
        if len(parts) == 2:
            sh, sm = int(parts[0]), int(parts[1])
            slots[(sh, sm)] = (key, cfg)
    return slots


def find_next_slot(now_h: int, now_m: int) -> tuple | None:
    """Find the next upcoming slot from current time."""
    slots = _load_slots()
    if not slots:
        return None
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


def detect_current_slot() -> dict | None:
    """Detect current push slot. Returns dict with push_id/dedup_flag or None.

    Returns:
        {'push_id': 'morning', 'dedup_flag': '--dedup', 'extra': '', 'filter': 'keyword'} or None
    """
    now = datetime.now(CST)
    h, m = now.hour, now.minute
    slots = _load_slots()
    if not slots:
        return None

    found = None
    for (sh, sm), (key, cfg) in slots.items():
        if slot_match(sh, sm, h, m):
            found = (sh, sm, key, cfg)
            break

    if not found:
        now_minutes = h * 60 + m
        closest = min(slots.keys(), key=lambda t: abs(t[0] * 60 + t[1] - (h * 60 + m)))
        delta = abs(closest[0] * 60 + closest[1] - now_minutes)
        closest_minutes = closest[0] * 60 + closest[1]
        if delta <= 10 and now_minutes >= closest_minutes:
            key, cfg = slots[closest]
            found = (closest[0], closest[1], key, cfg)
            log.info(f"偏离 {delta} 分钟, fallback 到 {cfg.get('display', '')}")

    if not found:
        return None

    sh, sm, key, cfg = found
    return {
        'push_id': key,
        'slot_label': cfg.get('display', ''),
        'dedup_flag': '--dedup' if cfg.get('dedup', False) else '',
        'extra': cfg.get('extra', ''),
        'filter': cfg.get('filter', 'keyword'),
    }


def main():
    now = datetime.now(CST)
    h, m = now.hour, now.minute

    if '--minutes-until' in sys.argv:
        next_slot = find_next_slot(h, m)
        print(next_slot[3] if next_slot else 1440)
        return 0

    if '--next-slot' in sys.argv:
        next_slot = find_next_slot(h, m)
        if next_slot:
            (sh, sm), key, cfg, delta = next_slot
            print(json.dumps({
                "slot": key, "time": f"{sh:02d}:{sm:02d}",
                "minutes_until": delta, "prefetch_recommended": delta <= 5,
            }, ensure_ascii=False))
        else:
            print(json.dumps({"slot": None, "minutes_until": 1440,
                              "prefetch_recommended": False}, ensure_ascii=False))
        return 0

    result = detect_current_slot()
    if result:
        print(f'PUSH_ID={result["push_id"]}')
        print(f'SLOT_LABEL={result["slot_label"]}')
        print(f'DEDUP_FLAG={result["dedup_flag"]}')
        print(f'EXTRA={result["extra"]}')
        print(f'FILTER={result["filter"]}')
    else:
        print('NO_SLOT')
    return 0 if result else 1


if __name__ == '__main__':
    sys.exit(main())
