#!/usr/bin/env python3
"""Domain metadata — source configuration, authority, and category lookups.

Extracted from curate_and_push.py to break circular dependencies with
classifier.py and scorer.py. Uses thread-safe _init_once pattern instead
of @lru_cache for compatibility.
"""

import json
import sys
import threading
from pathlib import Path


# ── Lazy import to avoid circular dependency ──
def _get_config_dir():
    from trendradar.scripts.settings import get_config_dir
    return get_config_dir()


# ── Thread-safe once-init lock & sentinel ──
_INIT_LOCK = threading.Lock()

# ── _config ──────────────────────────────────────────────────────
_CONFIG_VAL: dict = None

def _config() -> dict:
    global _CONFIG_VAL
    if _CONFIG_VAL is not None:
        return _CONFIG_VAL
    with _INIT_LOCK:
        if _CONFIG_VAL is not None:
            return _CONFIG_VAL
        try:
            _CONFIG_VAL = json.loads((_get_config_dir() / 'sources.json').read_text())
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            raise SystemExit(f"FATAL: Cannot load sources.json: {e}") from e
        return _CONFIG_VAL


# ── _sources ─────────────────────────────────────────────────────
_SOURCES_VAL: list = None

def _sources() -> list[dict]:
    global _SOURCES_VAL
    if _SOURCES_VAL is not None:
        return _SOURCES_VAL
    with _INIT_LOCK:
        if _SOURCES_VAL is not None:
            return _SOURCES_VAL
        _SOURCES_VAL = [s for s in _config().get('data_sources', []) if s.get('type') == 'rss' and s.get('enabled', True)]
        return _SOURCES_VAL


# ── _authority ───────────────────────────────────────────────────
_AUTHORITY_VAL: dict = None

def _authority() -> dict[str, int]:
    global _AUTHORITY_VAL
    if _AUTHORITY_VAL is not None:
        return _AUTHORITY_VAL
    with _INIT_LOCK:
        if _AUTHORITY_VAL is not None:
            return _AUTHORITY_VAL
        _AUTHORITY_VAL = {s['name']: s.get('authority', 1) for s in _sources()}
        return _AUTHORITY_VAL


# ── _game_sources ────────────────────────────────────────────────
_GAME_SOURCES_VAL: frozenset = None

def _game_sources() -> frozenset:
    global _GAME_SOURCES_VAL
    if _GAME_SOURCES_VAL is not None:
        return _GAME_SOURCES_VAL
    with _INIT_LOCK:
        if _GAME_SOURCES_VAL is not None:
            return _GAME_SOURCES_VAL
        _GAME_SOURCES_VAL = frozenset(s['name'].lower() for s in _sources() if s.get('category') == 'game')
        return _GAME_SOURCES_VAL


# ── _econ_boost ──────────────────────────────────────────────────
_ECON_BOOST_VAL: frozenset = None

def _econ_boost() -> frozenset:
    global _ECON_BOOST_VAL
    if _ECON_BOOST_VAL is not None:
        return _ECON_BOOST_VAL
    with _INIT_LOCK:
        if _ECON_BOOST_VAL is not None:
            return _ECON_BOOST_VAL
        _ECON_BOOST_VAL = frozenset(s['name'] for s in _sources() if s.get('authority', 1) >= 2 and s.get('category') in ('news', 'finance'))
        return _ECON_BOOST_VAL


# ── _econ_extra ──────────────────────────────────────────────────
_ECON_EXTRA_VAL: frozenset = None

def _econ_extra() -> frozenset:
    global _ECON_EXTRA_VAL
    if _ECON_EXTRA_VAL is not None:
        return _ECON_EXTRA_VAL
    with _INIT_LOCK:
        if _ECON_EXTRA_VAL is not None:
            return _ECON_EXTRA_VAL
        _ECON_EXTRA_VAL = frozenset({'澎湃新闻', '中国新闻网', '半月谈', '联合早报', 'BBC', '纽约时报', '中国事实核查'})
        return _ECON_EXTRA_VAL


# ── _foreign_sources ─────────────────────────────────────────────
_FOREIGN_SOURCES_VAL: frozenset = None

def _foreign_sources() -> frozenset:
    global _FOREIGN_SOURCES_VAL
    if _FOREIGN_SOURCES_VAL is not None:
        return _FOREIGN_SOURCES_VAL
    with _INIT_LOCK:
        if _FOREIGN_SOURCES_VAL is not None:
            return _FOREIGN_SOURCES_VAL
        _FOREIGN_SOURCES_VAL = frozenset(s['name'].lower() for s in _sources()
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
        return _FOREIGN_SOURCES_VAL


# ── _china_kw ────────────────────────────────────────────────────
_CHINA_KW_VAL: frozenset = None

def _china_kw() -> frozenset:
    global _CHINA_KW_VAL
    if _CHINA_KW_VAL is not None:
        return _CHINA_KW_VAL
    with _INIT_LOCK:
        if _CHINA_KW_VAL is not None:
            return _CHINA_KW_VAL
        _CHINA_KW_VAL = frozenset({'中国', '北京', '上海', '广州', '深圳', '习近平', '中俄', '中美', '中日',
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
        return _CHINA_KW_VAL


# ── _source_domain ───────────────────────────────────────────────
_SOURCE_DOMAIN_VAL: dict = None

def _source_domain() -> dict[str, str]:
    global _SOURCE_DOMAIN_VAL
    if _SOURCE_DOMAIN_VAL is not None:
        return _SOURCE_DOMAIN_VAL
    with _INIT_LOCK:
        if _SOURCE_DOMAIN_VAL is not None:
            return _SOURCE_DOMAIN_VAL
        _SOURCE_DOMAIN_VAL = {s['name']: s.get('category') for s in _sources() if s.get('category') in ('tech', 'economy', 'game')}
        return _SOURCE_DOMAIN_VAL


# ── _all_source_category ─────────────────────────────────────────
_ALL_SOURCE_CATEGORY_VAL: dict = None

def _all_source_category() -> dict[str, str]:
    """所有源 → category 映射，含 news 类别。用于 fallback 路由。"""
    global _ALL_SOURCE_CATEGORY_VAL
    if _ALL_SOURCE_CATEGORY_VAL is not None:
        return _ALL_SOURCE_CATEGORY_VAL
    with _INIT_LOCK:
        if _ALL_SOURCE_CATEGORY_VAL is not None:
            return _ALL_SOURCE_CATEGORY_VAL
        _ALL_SOURCE_CATEGORY_VAL = {s['name']: s.get('category', '') for s in _sources()}
        return _ALL_SOURCE_CATEGORY_VAL
