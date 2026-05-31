"""TrendRadar 评分参数 — 精选门槛、多样性惩罚、热度词。"""

MIN_SCORE = 6

# 多样性惩罚
MAX_SAME_SOURCE = 2
DIVERSITY_PENALTY_FACTOR = 0.5
MAX_SOURCE_PCT = 0.25

# 标题清晰度分档（字符数）
TITLE_CLARITY_LOW = 10
TITLE_CLARITY_HIGH = 40

# 时效分档（小时）
RECENCY_HOURS_HIGH = 1
RECENCY_HOURS_MID = 6
RECENCY_HOURS_LOW = 24

# 热度信号词（评分用）
SCORE_HEAT_WORDS = frozenset({'突发', '重磅', '紧急', '首次', '正式', '官宣', '定档', '上线', '新政', '突破'})

# 热度信号词（指纹/追踪用）
HEAT_WORDS = frozenset({'突发', '重磅', '紧急', '首次', '首发', '正式', '官宣', '确认', '定档', '上线', '发布', '新政', '突破', '里程碑', '重大', '最新', '首款', '警告', '战', '大跌', '暴涨', '全球'})

# 搜索标记比例
SEARCH_RATIO = 0.6
