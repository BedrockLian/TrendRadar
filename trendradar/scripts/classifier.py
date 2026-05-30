"""Item classification into domains: headline / foreign_china / tech / economy / gaming / junk."""

from trendradar.config.keywords import has_keyword_match, ALL_KEYWORDS


def classify_items(raw: list) -> tuple[list, list, list]:
    """分类：头条 / 外媒看华 / 其余 domain / 垃圾丢弃。"""
    # Lazy imports to avoid circular dependency with curate_and_push
    from trendradar.scripts.curate_and_push import (
        _foreign_sources, _china_kw, _game_sources,
        _source_domain, _all_source_category
    )

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
