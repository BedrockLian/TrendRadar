#!/usr/bin/env python3
from trendradar.scripts.common import CST
"""TrendRadar Curator — 全局重分类 + 并行精选（frozenset加速 + cache）"""
from trendradar.scripts.settings import get_logger
log = get_logger('curate-and-push')
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import lru_cache, cache

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


@lru_cache(maxsize=1)
def _config() -> dict:
    try:
        return json.loads((get_config_dir() / 'sources.json').read_text())
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
        raise SystemExit(f"FATAL: Cannot load sources.json: {e}") from e


@lru_cache(maxsize=1)
def _sources() -> list[dict]:
    return [s for s in _config().get('data_sources', []) if s.get('type') == 'rss' and s.get('enabled', True)]


@lru_cache(maxsize=1)
def _authority() -> dict[str, int]:
    return {s['name']: s.get('authority', 1) for s in _sources()}


@lru_cache(maxsize=1)
def _game_sources() -> frozenset:
    return frozenset(s['name'].lower() for s in _sources() if s.get('category') == 'game')


@lru_cache(maxsize=1)
def _econ_boost() -> frozenset:
    return frozenset(s['name'] for s in _sources() if s.get('authority', 1) >= 2 and s.get('category') in ('news', 'finance'))


@lru_cache(maxsize=1)
def _econ_extra() -> frozenset:
    return frozenset({'澎湃新闻', '中国新闻网', '半月谈', '联合早报', 'BBC', '纽约时报', '中国事实核查'})


@lru_cache(maxsize=1)
def _foreign_sources() -> frozenset:
    return frozenset(s['name'].lower() for s in _sources()
                     if s.get('authority', 1) >= 2 and s.get('platform') in (
        'reuters', 'bbc', 'nytimes', 'arstechnica', 'techcrunch', 'nhk',
        'VideoGamesChronicle', 'PCGamer', 'Eurogamer', 'RockPaperShotgun',
        'GamersNexus', 'nintendoeverything', 'aftermath', 'automaton',
        'guardian', 'scmp', 'nikkei', 'japantimes', 'koreaherald', 'npr',
        'bloomberg', 'ft', 'wsj', 'apnews', 'aljazeera', 'economist',
        'technologyreview', 'nature',
        'restofworld', 'sixthtone', 'foreignpolicy', 'straitstimes',
        'scmp_china',
    ))


@lru_cache(maxsize=1)
def _china_kw() -> frozenset:
    return frozenset({'中国', '北京', '上海', '广州', '深圳', '习近平', '中俄', '中美', '中日',
                       '中欧', '中央', '解放军', '外交部', '商务部', '国务院', '发改委',
                       '国家', '台湾', '台独', '香港', '澳门', '经济', '股市', '制造业',
                       '贸易', '关税', '芯片', '半导体', '华为', 'TikTok', '支付宝', '微信',
                       '人民币', '比亚迪', '阿里巴巴', '腾讯', '宁德时代',
                       '一带一路', '大湾区', 'China', 'Chinese', 'Beijing', 'Shanghai',
                       'Xi Jinping', 'Taiwan', 'Hong Kong', 'Macau', 'Sino-', 'Made in China',
                       'tariff', 'trade war', 'supply chain', 'yuan', 'renminbi',
                       '美中', '中美关系', '对华', '外贸', '制裁', '出口管制',
                       '地缘', '脱钩', '外媒', '国际', '中概股',
                       '字节跳动', '小红书', 'TikTok', 'DeepSeek', '百度', '小米',
                       '中兴', '中芯', '中石油', '中石化', '工商银行',
                       'Chinese stocks', 'China market', 'trade deficit',
                       'technology war', 'chip ban', 'AI ban',
                       'South China Sea', 'Xinjiang', 'Tibet',
                       'CPTPP', 'Belt and Road', 'foreign ministry',
                       'EVs', 'electric vehicle', 'overcapacity'})


@lru_cache(maxsize=1)
def _source_domain() -> dict[str, str]:
    return {s['name']: s.get('category') for s in _sources() if s.get('category') in ('tech', 'economy', 'game')}


@lru_cache(maxsize=1)
def _all_source_category() -> dict[str, str]:
    """所有源 → category 映射，含 news 类别。用于 fallback 路由。"""
    return {s['name']: s.get('category', '') for s in _sources()}


# ── Backward-compatible aliases (for tests and external consumers) ──

# Old private function names → new public module functions
_load_interests = load_interests
_score = score_item
calculate_score = score_item
_classify_items = classify_items
_score_headlines = score_headlines
_curate_domain = curate_domain


def _inject_heat(raw: list):
    """注入热度信息到 raw items（无副作用地修改传入列表）。"""
    try:
        import trendradar.scripts.heat_tracker as ht
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
