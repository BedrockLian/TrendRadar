from trendradar.scripts.common import CST
#!/usr/bin/env python3
"""TrendRadar Curator — 全局重分类 + 并行精选（frozenset加速 + cache）"""
from trendradar.scripts.settings import get_logger
log = get_logger('curate-and-push')
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from functools import lru_cache, cache

from trendradar.scripts.settings import get_data_dir, get_cache_dir, MIN_SCORE, MAX_PER_DOMAIN, DOMAINS, TRENDRADAR_HOME, BRIEFING_RATIO, SCORE_HEAT_WORDS, MAX_SAME_SOURCE, DIVERSITY_PENALTY_FACTOR, MAX_SOURCE_PCT
from trendradar.config.keywords import has_keyword_match, ALL_KEYWORDS
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()


@lru_cache(maxsize=1)
def _config() -> dict:
    try:
        return json.loads((DATA_DIR / 'sources.json').read_text())
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
    ))


@lru_cache(maxsize=1)
def _load_interests() -> tuple[frozenset, frozenset]:
    """加载 config/ai_interests.yaml，返回 (正面关键词, 排除关键词) 两个 frozenset。
    
    中文用滑窗提取 2-3 字关键片段，英文保留专有名词/缩写。
    回退支持旧版 .txt 格式。
    """
    import re
    yaml_path = TRENDRADAR_HOME / 'config' / 'ai_interests.yaml'
    txt_path = TRENDRADAR_HOME / 'config' / 'ai_interests.txt'
    
    lines = []
    if yaml_path.exists():
        import yaml
        data = yaml.safe_load(yaml_path.read_text(encoding='utf-8'))
        if data:
            for item in data.get('positive', []):
                lines.append(item)
            lines.append('# 不想看')
            for item in data.get('negative', []):
                lines.append(f'- {item}')
    elif txt_path.exists():
        lines = txt_path.read_text(encoding='utf-8').splitlines()
    else:
        return frozenset(), frozenset()
    
    positive, negative = set(), set()
    in_negative = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('#'):
            in_negative = '# 不想' in stripped
            continue
        content = stripped.lstrip('- ').strip()
        if not content:
            continue
        
        # Chinese sliding window: all 2-3 char substrings
        chars = list(re.findall(r'[\u4e00-\u9fff]', content))
        stopwords = {'关注', '我关注', '特别是', '尤其是', '方面', '方向', '影响', '变化',
                     '竞争', '进展', '动态', '格局', '政策', '领域', '情况', '调整',
                     '战略', '应用', '落地', '态势', '热点', '赛道', '曲线',
                     '部署', '突破', '升级', '趋势', '市场', '产业', '发展', '推动',
                     '提升', '分析', '报告', '状况', '环节', '相关', '就是',
                     '不会', '还是', '可以', '这个', '那个', '什么', '怎么', '因为',
                     '所以', '如果', '但是', '而且', '或者', '虽然', '由于', '关于',
                     '基于', '通过', '采用', '进行', '开始', '继续', '实现', '成为',
                     '带来', '加大', '进入', '超过', '达到', '保持', '构成', '形成',
                     '新闻', '游戏', '体育', '行业', '重大', '娱乐', '明星'}
        for i in range(len(chars)):
            for wlen in (2, 3):
                if i + wlen <= len(chars):
                    word = ''.join(chars[i:i+wlen])
                    if word not in stopwords:
                        (negative if in_negative else positive).add(word)
        
        # English keywords
        for m in re.finditer(r'[A-Z][A-Za-z0-9+/]{1,}', content):
            (negative if in_negative else positive).add(m.group())
        tech_terms = {'agent', 'rag', 'llm', 'gpu', 'cpu', 'ev', 'ai', 'api', 'saas', 'cloud'}
        for t in tech_terms:
            if t in content.lower():
                (negative if in_negative else positive).add(t.upper())
    
    return frozenset(positive), frozenset(negative)


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
        path = DATA_DIR / 'source_health.json'
    try:
        data = json.loads(Path(path).read_text())
        _source_health = data.get('sources', {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[curate] 加载 source_health 失败: {e}", file=sys.stderr)


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


def _score(item: dict, domain: str = 'tech') -> dict:
    """综合评分：清晰度 + 权威度 + 时效性 + 唯一性 + 热度 + 来源惩罚。

    Returns: {'total': int, 'pass': bool} — total >= MIN_SCORE 且 recency > 0 为 pass。
    
    外部来源惩罚通过 --penalty-file 传入，由盲点审计产出。
    """
    title, platform, url = item.get('title', ''), item.get('source_platform', ''), item.get('url', '')
    clarity = 1 if (any(c in title for c in '?？') or len(title) < 10) else 2 if len(title) > 40 else 3
    base = next((v for k, v in _authority().items() if k in platform), 1)
    econ_match = platform in _econ_boost() or platform in _econ_extra()
    authority = base + (1 if domain == 'economy' and econ_match else 0)
    
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
    recency = 3 if age < 1 else 2 if age < 6 else 1 if age < 24 else 0
    # 博客内容即使内容较旧也给最低 recency（刚被 blogwatcher 发现）
    if recency == 0 and item.get('_is_blog'):
        recency = 1
    uniqueness = 3 if any(m in title for m in ['[续]', '[新]', '[更新]']) else 2 if url else 1
    cov, hits = item.get('_coverage_count', 1), sum(1 for w in SCORE_HEAT_WORDS if w in title)
    heat = 3 if cov >= 4 or (cov >= 2 and hits >= 2) else 2 if cov >= 3 or hits >= 2 else 1 if cov >= 2 or hits >= 1 else 0
    total = clarity + authority + recency + uniqueness + heat
    # AI 兴趣偏好 — 正面加分，排除项过滤
    pos_kw, neg_kw = _load_interests()
    if pos_kw:
        text_to_check = f"{title} {item.get('summary', '')}"
        if any(kw in text_to_check for kw in pos_kw):
            total += 2
    if neg_kw:
        if any(kw in title for kw in neg_kw):
            return {'total': 0, 'pass': False}
    return {'total': total, 'pass': total >= MIN_SCORE and recency > 0}


# Public alias for _score (naming convention: verb_noun)
calculate_score = _score


def _curate_domain(items: list, domain: str) -> list:
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
        s = _score(item, domain)
        item['_curator_scores'] = s
        if s['pass']:
            curated.append(item)
    curated.sort(key=lambda x: (x['_curator_scores']['total'], x.get('_heat', {}).get('heat_score', 0)), reverse=True)
    
    # 来源多样性惩罚：同源 > 3 条时权重减半
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
    
    max_n = MAX_PER_DOMAIN.get(domain, 15)
    result = result[:max_n]
    for i, item in enumerate(result):
        item['_needs_search'] = i < len(result) * 0.6
    return result


def _classify_items(raw: list) -> tuple[list, list, list]:
    """分类：头条 / 外媒看华 / 其余 domain / 垃圾丢弃。"""
    KW = ALL_KEYWORDS
    FOREIGN = _foreign_sources()
    CHINA = _china_kw()
    GAME_SRC = _game_sources()
    SRC_DOMAIN = _source_domain()
    ALL_SRC_CAT = _all_source_category()
    # False positive patterns for game keyword matching
    _GAME_FALSE_POSITIVES = frozenset({'改变游戏规则'})
    # Also skip game classification if the only game keyword match is '索尼' in a music context
    _is_sony_music = lambda t: '索尼' in t and '音乐' in t
    headline, remaining, foreign_china = [], [], []
    for item in raw:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        plat = (item.get('source_platform', '') or '').lower()
        src_is_foreign = any(fs in plat for fs in FOREIGN)
        china_hit = any(k in text for k in CHINA)

        if src_is_foreign and china_hit and not any(sp in plat for sp in GAME_SRC):
            item['_likely_domain'] = 'foreign_china'
            foreign_china.append(item)
        elif any(sp in plat for sp in GAME_SRC) or (
            has_keyword_match(text, 'game', KW['game'])
            and not has_keyword_match(text, 'game', _GAME_FALSE_POSITIVES)
            and not (_is_sony_music(text) and not any(sp in plat for sp in GAME_SRC))
        ):
            item['_likely_domain'] = 'gaming'
            remaining.append(item)
        elif has_keyword_match(text, 'junk', KW['junk']):
            item['_drop'] = True
        elif has_keyword_match(text, 'safety', KW['safety']) or has_keyword_match(text, 'politics', KW['politics']):
            item['_likely_domain'] = 'headline'
            headline.append(item)
        elif has_keyword_match(text, 'tech', KW['tech']):
            item['_likely_domain'] = 'tech'
            remaining.append(item)
        elif has_keyword_match(text, 'economy', KW['economy']):
            item['_likely_domain'] = 'economy'
            remaining.append(item)
        else:
            orig = item.get('_likely_domain', '')
            if orig in ('tech', 'economy', 'gaming', 'top_headlines'):
                item['_likely_domain'] = orig
                remaining.append(item)
            elif item.get('source_platform', '') in SRC_DOMAIN:
                item['_likely_domain'] = 'gaming' if SRC_DOMAIN[item['source_platform']] == 'game' else SRC_DOMAIN[item['source_platform']]
                remaining.append(item)
            else:
                src_cat = ALL_SRC_CAT.get(item.get('source_platform', ''), '')
                if src_cat == 'news':
                    item['_likely_domain'] = 'headline'
                    headline.append(item)
                elif src_cat == 'game':
                    item['_likely_domain'] = 'gaming'
                    remaining.append(item)
                elif src_cat == 'tech':
                    item['_likely_domain'] = 'tech'
                    remaining.append(item)
                elif src_cat == 'economy':
                    item['_likely_domain'] = 'economy'
                    remaining.append(item)
                else:
                    item['_drop'] = True
    return headline, remaining, foreign_china


def _score_headlines(headline: list) -> list:
    """头条打分排序。"""
    hl_scored = []
    for item in headline:
        if not item.get('summary', '').strip():
            item['_drop'] = True
            continue
        s = _score(item)
        item['_curator_scores'] = s
        if s['pass']:
            hl_scored.append(item)
    hl_scored.sort(key=lambda x: (x['_curator_scores']['total'], x.get('_heat', {}).get('heat_score', 0)), reverse=True)
    max_n = MAX_PER_DOMAIN['top_headlines']
    for i, item in enumerate(hl_scored[:max_n]):
        item['_needs_search'] = i < max_n * 0.6
    return hl_scored[:max_n]


def _curate_sections(pool: list, push_id: str) -> dict:
    """非头条 domain 精选 + 组装结果。"""
    result = {'top_headlines': [], 'foreign_china': [], 'tech': [], 'economy': [], 'gaming': [],
              'total': 0, 'curated_at': datetime.now(CST).isoformat(), 'push_id': push_id}
    for domain in ['tech', 'economy', 'gaming', 'foreign_china']:
        items = _curate_domain(pool, domain)
        if items:
            result[domain] = items
    result['total'] = sum(len(result[d]) for d in DOMAINS)
    return result


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
    headline, remaining, foreign_china = _classify_items(raw)
    top_headlines = _score_headlines(headline)
    return top_headlines, remaining + foreign_china


def apply_truncation(result: dict, push_id: str):
    """per-slot 总量截断 + 全局来源多样性上限。"""
    from collections import Counter
    from trendradar.scripts.settings import MAX_SOURCE_PCT as _MAX_SOURCE_PCT
    
    # 全局来源多样性上限
    all_sources = Counter()
    for d in DOMAINS:
        for item in result.get(d, []):
            src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
            if src:
                all_sources[src] += 1
    total = result['total']
    for src, count in all_sources.most_common():
        if total > 0 and count / total > _MAX_SOURCE_PCT:
            to_remove = count - int(total * _MAX_SOURCE_PCT)
            src_items = []
            for d in DOMAINS:
                for i, item in enumerate(result.get(d, [])):
                    item_src = (item.get('source_platform', '') or '').split('+')[0].strip().lower()
                    if item_src == src:
                        score = item.get('_curator_scores', {}).get('total', 0)
                        src_items.append((score, d, i))
            src_items.sort()
            removed = 0
            for score, domain, idx in reversed(src_items):
                if removed >= to_remove:
                    break
                del result[domain][idx]
                removed += 1
                total -= 1

    # per-slot 总量截断
    from trendradar.scripts.settings import BRIEFING_RATIO
    max_total = BRIEFING_RATIO.get(push_id, 30)
    if result['total'] > max_total:
        non_headline = result['total'] - len(result.get('top_headlines', []))
        remaining = max_total - len(result.get('top_headlines', []))
        if remaining < 0:
            result['top_headlines'] = result['top_headlines'][:max_total]
            for d in DOMAINS:
                if d != 'top_headlines':
                    result[d] = []
        elif remaining < non_headline:
            for d in ['tech', 'gaming', 'economy', 'foreign_china']:
                keep = max(1, int(len(result[d]) / non_headline * remaining))
                result[d] = result[d][:keep]
                remaining -= keep
                if remaining <= 0:
                    break
        result['truncated'] = True
        result['total'] = sum(len(result[d]) for d in DOMAINS)


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
