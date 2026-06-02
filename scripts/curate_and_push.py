#!/usr/bin/env python3
from trendradar.scripts.common import CST
"""TrendRadar Curator — 全局重分类 + 并行精选（frozenset加速 + cache）"""
from trendradar.scripts.settings import get_logger
log = get_logger('curate-and-push')
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
import threading

from trendradar.scripts.settings import get_data_dir, get_cache_dir, get_config_dir, MIN_SCORE, MAX_PER_DOMAIN, DOMAINS, TRENDRADAR_HOME, BRIEFING_RATIO, SCORE_HEAT_WORDS, MAX_SAME_SOURCE, DIVERSITY_PENALTY_FACTOR, MAX_SOURCE_PCT
from trendradar.config.keywords import has_keyword_match, ALL_KEYWORDS
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()

# ── Sub-module imports ──────────────────────────────────────────────
from trendradar.scripts.classifier import classify_items
from trendradar.scripts.scorer import (
    score_item, score_headlines, curate_domain,
    load_penalty_file, load_source_health,
    _get_source_penalty, _get_health_penalty,
)
from trendradar.scripts.truncator import apply_truncation
from trendradar.scripts.interest_loader import load_interests


from trendradar.scripts.domain_metadata import (
    _config, _sources, _authority, _game_sources, _econ_boost,
    _econ_extra, _foreign_sources, _china_kw, _source_domain, _all_source_category,
)


import trendradar.scripts.heat_tracker as ht


def _inject_heat(raw: list):
    """注入热度信息到 raw items（无副作用地修改传入列表）。"""
    try:
        if not any('_heat' in item for item in raw):
            hi = ht.get_heat_info(raw)
            for item in raw:
                if (fp := ht.make_fingerprint(item.get('title', ''), item.get('url', ''))) in hi:
                    item['_heat'] = hi[fp]
    except Exception as e:
        import traceback
        log.warning(f'热度追踪失败: {e}\n{traceback.format_exc()}')


def classify_and_score(raw: list) -> tuple:
    """分类 + 评分：返回 (top_headlines, pool_items)。"""
    headline, remaining, foreign_china = classify_items(raw)
    top_headlines = score_headlines(headline)
    return top_headlines, remaining + foreign_china


def _curate_sections(pool: list, push_id: str) -> dict:
    """非头条 domain 精选 + 组装结果。"""
    result = {'top_headlines': [], 'foreign_china': [], 'tech': [], 'economy': [], 'gaming': [],
              'total': 0, 'curated_at': datetime.now(CST).isoformat(), 'push_id': push_id}
    for domain in ['tech', 'economy', 'gaming', 'foreign_china']:
        items = curate_domain(pool, domain)
        if items:
            result[domain] = items
    result['total'] = sum(len(result[d]) for d in DOMAINS)
    return result


def curate_all(raw: list, push_id: str) -> dict:
    """全局重分类 + 并行精选（拆分为 _inject_heat / classify_and_score / _curate_sections / apply_truncation）。"""
    # 热度信息
    _inject_heat(raw)

    # 分类 + 评分
    top_headlines, pool = classify_and_score(raw)

    # 其余 domain 精选
    result = _curate_sections(pool, push_id)
    result['top_headlines'] = top_headlines
    result['total'] = sum(len(result[d]) for d in DOMAINS)

    # 多样性截断
    apply_truncation(result, push_id)

    return result
