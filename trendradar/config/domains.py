"""TrendRadar 领域常量 — 板块定义、名称、限制。"""

DOMAINS = ['top_headlines', 'foreign_china', 'tech', 'economy', 'gaming']

DOMAIN_LABELS = {
    'top_headlines': '📰 头条',
    'foreign_china': '🌏 国际/外媒看华',
    'tech': '💻 科学/技术',
    'economy': '📊 经济民生',
    'gaming': '🎮 游戏',
}

MAX_PER_DOMAIN: dict[str, int] = {
    'top_headlines': 8,
    'tech': 7,
    'economy': 5,
    'gaming': 5,
    'foreign_china': 5,
}

DOMAIN_EMOJI = {
    'top_headlines': '📰', 'foreign_china': '🌏',
    'tech': '💻', 'economy': '📊', 'gaming': '🎮',
}

SLOT_NAMES = {'morning': '早报', 'noon': '午间速递', 'evening': '今日回顾'}

DAILY_LIMIT = 80
BRIEFING_RATIO = {'morning': 30, 'noon': 30, 'evening': 30}

# 层级多样性保护
HIGH_AUTHORITY_THRESHOLD = 3          # authority >= 3 视为高权威
TIER_DIVERSITY_MIN = 1                # 每域至少保留 1 条非高权威条目（如有）
