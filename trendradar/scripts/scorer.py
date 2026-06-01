"""Scoring engine — item quality scoring, penalty logic, domain curation."""

import json
import sys
from datetime import datetime
from pathlib import Path

from trendradar.scripts.common import CST
from trendradar.scripts.settings import (
    get_logger, MIN_SCORE, MAX_PER_DOMAIN, SCORE_HEAT_WORDS,
    MAX_SAME_SOURCE, DIVERSITY_PENALTY_FACTOR,
    HIGH_AUTHORITY_THRESHOLD, TIER_DIVERSITY_MIN,
    RECENCY_HOURS_LOW,
)
from trendradar.scripts.interest_loader import load_interests

log = get_logger('curate-and-push')

# ── 来源惩罚表（盲点审计 → curator 权重反馈） ──────────────────
_penalty_map: dict[str, float] = {}


def load_penalty_file(path: str):
    """Load source penalty JSON from blind_spot_audit --output-penalty.
    
    Format: {"overrepresented_sources": [{"source": "bbc", "penalty_factor": 0.75}, ...]}
    """
    global _penalty_map
    try:
        data = json.loads(Path(path).read_text())
        for entry in data.get('overrepresented_sources', []):
            src = entry.get('source', '').lower().strip()
            factor = entry.get('penalty_factor', 1.0)
            if src:
                _penalty_map[src] = factor
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[curate] 加载 diversity 惩罚配置失败: {e}", file=sys.stderr)


def _get_source_penalty(platform: str) -> float:
    """Get penalty factor for a source platform (1.0 = no penalty).
    
    Matches by word boundary to avoid spurious matches:
    'reuters' should match 'Reuters' but not 'ReutersPlus' substrings.
    """
    if not _penalty_map:
        return 1.0
    plat = platform.lower().strip()
    plat_words = set(plat.replace('+', ' ').split())
    for src, factor in _penalty_map.items():
        src_lower = src.lower()
        # Match if source appears as a complete word in platform
        if src_lower in plat_words or src_lower == plat:
            return factor
    return 1.0


# ── source_health.json 消费（负反馈学习环） ─────────────────
_source_health: dict[str, dict] = {}


def load_source_health(path: str = None):
    """Load source_health.json for dynamic authority adjustment.
    
    Sources with status='failing' get authority penalized (x0.3).
    Sources with status='degrading' get authority penalized (x0.7).
    """
    global _source_health
    if path is None:
        # Lazy import to avoid circular dependency
        from trendradar.scripts.settings import get_data_dir
        path = get_data_dir() / 'source_health.json'
    try:
        data = json.loads(Path(path).read_text())
        _source_health = data.get('sources', {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.warning("加载 source_health 失败: %s", e)


def _get_health_penalty(platform: str) -> float:
    """Get authority penalty based on source health score."""
    if not _source_health:
        return 1.0
    plat = platform.lower().strip()
    for src, health in _source_health.items():
        if src.lower() in plat or plat in src.lower():
            status = health.get('status', 'healthy')
            if status == 'failing':
                return 0.3   # 70% authority reduction
            elif status == 'degrading':
                return 0.7   # 30% authority reduction
            score = health.get('health_score', 60)
            if score < 30:
                return 0.5
            return 1.0
    return 1.0


def _get_source_priority(platform: str, domain: str = '') -> int:
    from trendradar.scripts.settings import get_config_dir
    import json
    try:
        cfg = json.loads((get_config_dir() / 'sources.json').read_text())
        for s in cfg.get('data_sources', []):
            if s.get('name') == platform:
                pri = s.get('priority', 1)
                # 跨域降级：非本域来源强制 P2(末尾)，仅显示标题
                if domain and s.get('category', '') != domain:
                    domain_map = {'top_headlines': 'news', 'tech': 'tech',
                                  'economy': 'economy', 'gaming': 'game',
                                  'foreign_china': 'foreign_china'}
                    if domain_map.get(domain, '') != s.get('category', ''):
                        return 2
                return pri
    except Exception:
        pass
    return 1


def _get_item_authority(item: dict) -> int:
    """Get authority level for an item's source (lazy import to avoid circular dep)."""
    from trendradar.scripts.domain_metadata import _authority
    platform = item.get('source_platform', '')
    auth_map = _authority()
    return next((v for k, v in auth_map.items() if k in platform), 1)


def score_item(item: dict, domain: str = 'tech') -> dict:
    """综合评分：清晰度 + 权威度 + 时效性 + 唯一性 + 热度 + 来源惩罚。

    Returns: {'total': int, 'pass': bool} — total >= MIN_SCORE 且 recency > 0 为 pass。
    
    外部来源惩罚通过 --penalty-file 传入，由盲点审计产出。
    """
    # Lazy imports to avoid circular dependency with curate_and_push
    from trendradar.scripts.domain_metadata import _authority, _econ_boost, _econ_extra, _all_source_category

    title, platform, url = item.get('title', ''), item.get('source_platform', ''), item.get('url', '')
    clarity = 1 if (any(c in title for c in '?？') or len(title) < 10) else 2 if len(title) > 40 else 3
    base = next((v for k, v in _authority().items() if k in platform), 1)
    
    # 域-源匹配加分：源分类匹配当前域则 +1（如 tech 源在科技域）
    # 确保专业源在自家域内有竞争优势，防止头条源跨界刷屏
    src_cat = _all_source_category().get(platform, '')
    domain_to_cat = {'top_headlines': 'news', 'tech': 'tech', 'economy': 'economy',
                     'gaming': 'game', 'foreign_china': 'foreign_china'}
    if src_cat == domain_to_cat.get(domain):
        authority = base + 1
    else:
        authority = base
    
    # 外部来源惩罚（盲点审计 → 权重反馈）
    penalty_factor = _get_source_penalty(platform)
    if penalty_factor < 1.0:
        authority = max(1, int(authority * penalty_factor))
    
    # 健康评分惩罚（负反馈学习环 → 自动淘汰低质量源）
    health_penalty = _get_health_penalty(platform)
    if health_penalty < 1.0:
        authority = max(1, int(authority * health_penalty))
    try:
        ts = item.get('timestamp', '')
        if len(ts) > 15 and ts[10] == 'T':
            age = (datetime.now(CST) - datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone(CST)).total_seconds() / 3600
        else:
            age = 24
    except (ValueError, TypeError):
        age = 24
    recency = 3 if age < 1 else 2 if age < 6 else 1 if age < RECENCY_HOURS_LOW else 0
    # 博客内容即使内容较旧也给最低 recency（刚被 blogwatcher 发现）
    if recency == 0 and item.get('_is_blog'):
        recency = 1
    uniqueness = 3 if any(m in title for m in ['[续]', '[新]', '[更新]']) else 2 if url else 1
    cov, hits = item.get('_coverage_count', 1), sum(1 for w in SCORE_HEAT_WORDS if w in title)
    heat = 3 if cov >= 4 or (cov >= 2 and hits >= 2) else 2 if cov >= 3 or hits >= 2 else 1 if cov >= 2 or hits >= 1 else 0
    total = clarity + authority + recency + uniqueness + heat
    # AI 兴趣偏好 — 正面加分，排除项过滤
    pos_kw, neg_kw = load_interests()
    if pos_kw:
        text_to_check = f"{title} {item.get('summary', '')}"
        if any(kw in text_to_check for kw in pos_kw):
            total += 2
    if neg_kw:
        if any(kw in title for kw in neg_kw):
            return {'total': 0, 'pass': False}
    return {'total': total, 'pass': total >= MIN_SCORE and recency > 0}


def curate_domain(items: list, domain: str) -> list:
    """单 domain 精选排序（过滤空摘要条目，博客除外）。
    
    多样性惩罚：同一来源在最终结果中超过 3 条后，后续条目权重减半，
    防止单一来源霸榜。
    """
    domain_items = [i for i in items
                    if i.get('_likely_domain') == domain
                    and not i.get('_drop')
                    and i.get('summary', '').strip()]
    curated = []
    for item in domain_items:
        s = score_item(item, domain)
        item['_curator_scores'] = s
        if s['pass']:
            curated.append(item)
    curated.sort(key=lambda x: (_get_source_priority(x.get('source_platform', ''), domain),
                                 -x['_curator_scores']['total'],
                                 -x.get('_heat', {}).get('heat_score', 0)))
    
    # 来源多样性惩罚：同源超过 MAX_SAME_SOURCE 条后权重减半
    result = []
    source_counts: dict[str, int] = {}
    
    for item in curated:
        src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
        if src:
            count = source_counts.get(src, 0)
            if count >= MAX_SAME_SOURCE:
                # 权重减半但不丢弃 — 仍可能作为 low-priority 条目
                item['_curator_scores']['total'] = int(
                    item['_curator_scores']['total'] * DIVERSITY_PENALTY_FACTOR
                )
                item['_diversity_penalized'] = True
            source_counts[src] = count + 1
        
        # 按（可能已惩罚的）分数排序插入
        result.append(item)
    
    # 按最终分数重新排序
    result.sort(key=lambda x: x['_curator_scores']['total'], reverse=True)
    
    # 硬上限：同源最多 MAX_SAME_SOURCE 条，超限的低分条目丢弃
    seen: dict[str, int] = {}
    hard_capped = []
    for item in result:
        src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
        n = seen.get(src, 0)
        if n >= MAX_SAME_SOURCE:
            continue  # 丢弃超限条目
        seen[src] = n + 1
        hard_capped.append(item)
    result = hard_capped
    
    max_n = MAX_PER_DOMAIN.get(domain, 15)
    result = result[:max_n]

    # 层级多样性保护：确保至少 TIER_DIVERSITY_MIN 条非高权威条目
    # 防止高权威源垄断所有槽位，给中低权威源留出空间
    if TIER_DIVERSITY_MIN > 0:
        low_in_result = [i for i in result if _get_item_authority(i) < HIGH_AUTHORITY_THRESHOLD]
        need = TIER_DIVERSITY_MIN - len(low_in_result)
        if need > 0:
            # 候选池：未入选但已过 MIN_SCORE 的低权威条目
            low_in_pool = [i for i in curated if i not in result
                           and _get_item_authority(i) < HIGH_AUTHORITY_THRESHOLD]
            low_in_pool.sort(key=lambda x: x['_curator_scores']['total'], reverse=True)
            # 可替换的：已入选的高权威条目中得分最低的
            high_in_result = [i for i in result if _get_item_authority(i) >= HIGH_AUTHORITY_THRESHOLD]
            high_in_result.sort(key=lambda x: x['_curator_scores']['total'])

            replacements = min(need, len(low_in_pool), len(high_in_result))
            for i in range(replacements):
                if low_in_pool[i]['_curator_scores']['total'] >= MIN_SCORE:
                    result.remove(high_in_result[i])
                    result.append(low_in_pool[i])

            result.sort(key=lambda x: x['_curator_scores']['total'], reverse=True)

    for i, item in enumerate(result):
        item['_needs_search'] = i < len(result) * 0.6
    return result


def score_headlines(headline: list) -> list:
    """头条打分排序。"""
    hl_scored = []
    for item in headline:
        if not item.get('summary', '').strip():
            item['_drop'] = True
            continue
        s = score_item(item)
        item['_curator_scores'] = s
        if s['pass']:
            hl_scored.append(item)
    hl_scored.sort(key=lambda x: (_get_source_priority(x.get('source_platform', ''), 'top_headlines'),
                                   -x['_curator_scores']['total'],
                                   -x.get('_heat', {}).get('heat_score', 0)))
    max_n = MAX_PER_DOMAIN['top_headlines']

    # 同源硬上限：最多 MAX_SAME_SOURCE 条，超限丢弃
    seen: dict[str, int] = {}
    hard_capped = []
    for item in hl_scored:
        src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
        n = seen.get(src, 0)
        if n >= MAX_SAME_SOURCE:
            continue
        seen[src] = n + 1
        hard_capped.append(item)

    for i, item in enumerate(hard_capped[:max_n]):
        item['_needs_search'] = i < max_n * 0.6
    return hard_capped[:max_n]
