#!/usr/bin/env python3
"""Wrapper: delegates to trendradar/scripts/collect_weekly_reports.py for monthly aggregation."""
import sys, os
from pathlib import Path

TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
target = TR / 'scripts' / 'collect_weekly_reports.py'
if not target.exists():
    target = Path(__file__).resolve().parent.parent.parent.parent.parent / 'trendradar' / 'scripts' / 'collect_weekly_reports.py'
sys.path.insert(0, str(target.parent))
exec(compile(target.read_bytes(), target, 'exec'))
