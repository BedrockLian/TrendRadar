"""TrendRadar 关键词集合 — 单一事实源，供 curate_and_push 和 fetch_feeds 共用。"""

GAME_KW = frozenset({
    '游戏', 'Game', 'game', 'ゲーム', 'Steam', 'Epic', 'Switch', 'Xbox',
    'PlayStation', 'PS5', 'PS4', 'PS Plus',
    'Nintendo', '任天堂', '索尼', '主机', '手游', '掌机', 'MOD', 'DLC',
    'FPS', 'RPG', '3A', '原神', 'Genshin', 'genshin', 'Genshin Impact',
    '黑神话', 'GTA', '塞尔达', '艾尔登法环', 'Elden Ring', 'Dark Souls',
    '博德之门', "Baldur's Gate", '魔兽', '暴雪', '使命召唤', '我的世界', '独立游戏', '评测',
    '游戏版号', '米哈游', 'miHoYo', 'mihoyo', 'HoYoverse', '崩坏',
    'Honkai', 'honkai', '星穹铁道', 'Star Rail', 'star rail', '绝区零',
    'Zenless', 'zenless', 'ZZZ', 'zzz', '未定事件簿', 'Tears of Themis',
    'tears of themis', '机核', 'GameLook', '触乐', '4Gamer', 'ファミ通',
    'Famitsu', 'ファミ',
    'gameplay', 'trailer', 'indie game', 'co-op', 'console',
    '発売', '配信', 'リリース', 'レビュー', '体験版', 'DLC情報',
    'アップデート', 'ゲーム機',
    'スクエニ', 'カプコン', 'バンナム', 'セガ', 'コナミ',
    'フロム', 'アトラス', 'レベルファイブ',
    'モンハン', 'Monster Hunter', 'ドラクエ', 'Dragon Quest',
    'ファイナルファンタジー', 'Final Fantasy',
    'Steam Deck', 'Game Pass',
    'アクション', 'シューター', 'パズル', 'サバイバル',
    'esports', 'tournament', 'championship',
    'MMO', 'MMORPG', 'battle royale', 'MOBA',
    'roguelike', 'soulslike', 'metroidvania', 'JRPG',
    'Unreal Engine', 'Unity',
    'remaster', 'remake', 'expansion',
    'Early Access', 'open beta', 'closed beta',
    'Persona', 'Yakuza', 'Resident Evil', 'Zelda',
    'Diablo', 'Overwatch', 'Skyrim', 'Witcher', 'Cyberpunk',
    'Twitch', 'Gamescom',
})

TECH_KW = frozenset({
    '大模型', 'ChatGPT', 'LLM', '芯片', '半导体', '英伟达', 'AMD',
    '英特尔', 'GPU', 'CPU', '显卡', '处理器', '手机', '电脑', '数码',
    '操作系统', '苹果', '华为', '小米', '三星', '微软', 'Meta', 'Google',
    '特斯拉', '自动驾驶', '机器人', '电动汽车', '新能源', '电池', '充电',
    '云计算', '5G', '6G', 'VR', '元宇宙', '算法', '数据', '开源',
    '编程', '智能', '3D打印', '打印机', '传感器', '物联网', '家电', '屏幕',
    '显示器', '软件', '应用', 'APP', '互联网', '网络', '电商', '直播',
    '社交媒体',
    'Nvidia', 'Intel', 'Apple', 'Samsung', 'Microsoft', 'Tesla',
    'semiconductor', 'chipmaker', 'foundry',
    'SpaceX', 'spacecraft', 'satellite', 'NASA',
    'cryptocurrency', 'blockchain', 'Bitcoin', 'crypto',
    'cybersecurity', 'malware', 'ransomware', 'vulnerability',
    'startup', 'venture capital', 'Series A', 'IPO',
    'SaaS', 'cloud computing', 'API', 'open source',
    'drone', 'autonomous', 'robotics',
    'quantum', 'machine learning', 'neural network',
    'Android', 'iOS', 'Windows', 'Linux',
    'Kubernetes', 'Docker', 'GitHub', 'DevOps',
    'fintech', 'healthtech', 'biotech',
    'antitrust', 'chip', 'Ryzen', 'NVIDIA',
})

ECONOMY_KW = frozenset({
    '就业', '消费', '工资', '收入', '物价', 'CPI', '民生', '房价',
    '裁员', '招聘', '社保', '居民', '零售', '内需', '房地产', 'GDP',
    '财政', '税收', '补贴', '养老金', '医保', '失业', '劳动', '个税',
    '贸易', '进出口', '产业', '贷款', '借贷', '债务', '融资', '投资',
    '招商', '资本', '餐饮', '餐厅', '外卖', '食品', '农业', '农民',
    '农村', '货运', '物流', '快递', '工厂', '制造', '工业', '成本',
    '价格', '涨价', '降价', '商家', '企业', '创业', '经营', '亏损',
    '利润', '市场', '行业', '脱贫', '扶贫',
    'employment', 'unemployment', 'layoff', 'hiring freeze',
    'inflation', 'deflation', 'interest rate', 'central bank',
    'Federal Reserve', 'Fed', 'monetary policy',
    'housing market', 'mortgage', 'real estate',
    'retail sales', 'consumer spending', 'consumer confidence',
    'trade war', 'tariff', 'export controls', 'supply chain',
    'wage growth', 'labor market', 'strike', 'union',
    'recession', 'GDP growth', 'stimulus package', 'fiscal',
    'commodity price', 'oil price', 'energy crisis',
    'manufacturing', 'factory output', 'industrial production',
    'food security', 'food price', 'agriculture',
    'pension', 'social security',
    'startup funding', 'venture capital', 'SME',
    'sovereign debt', 'bond market', 'treasury yield',
    'poverty', 'inequality', 'minimum wage',
})

SAFETY_KW = frozenset({
    '爆炸', '火灾', '坍塌', '倒塌', '坠河', '坠机', '车祸', '交通事故',
    '地震', '洪水', '台风', '暴雨', '泥石流', '滑坡', '中毒', '泄漏',
    '起火', '被困', '遇难', '伤亡', '失踪', '救援', '搜救', '警情',
    '灾害', '矿难', '枪击', '袭击', '失联', '抗震', '救灾',
    'explosion', 'blast', 'wildfire', 'blaze',
    'plane crash', 'train crash', 'ship sinking',
    'earthquake', 'tsunami', 'aftershock', 'tremor',
    'flood', 'flash flood', 'landslide', 'mudslide',
    'typhoon', 'hurricane', 'cyclone', 'tornado',
    'chemical leak', 'oil spill', 'toxic',
    'casualties', 'fatalities', 'death toll',
    'injured', 'wounded', 'trapped', 'stranded',
    'missing persons', 'search and rescue',
    'mass shooting', 'hostage', 'terror attack',
    'evacuation', 'state of emergency',
    'mining accident', 'building collapse',
    'outbreak', 'pandemic', 'epidemic',
})

POLITICS_KW = frozenset({
    '八项规定', '党纪', '政务处分', '纪委', '中央纪委', '监委', '反腐',
    '从严治党', '作风', '通报', '查处', '问责',
    '访华', '会见', '会谈', '外交', '大使', '双边', '国际', '普京',
    '拜登', '特朗普', '中美', '中俄', '北约', '联合国', '制裁', '声明',
    '呼吁', '谈判', '协议', '习近平', '总理', '主席', '全球', '世界',
    '海外', '外国', '境外', '国际法院', '世卫', '世贸', '欧盟', '美国',
    '英国', '法国', '德国', '日本', '韩国', '印度', '菲律宾', '伊朗',
    '以色列', '乌克兰', '俄罗斯', '朝鲜', '澳大利亚', '选举', '大选',
    '抗议', '政变', '战争', '冲突', '军演', '阅兵', '发射', '卫星',
    '航天', '太空', '火星', '月球', '诺贝尔', '奥运', '世锦赛',
    '世界杯', '大选',
    'Trump', 'Biden', 'Putin', 'Xi Jinping', 'Zelensky', 'Netanyahu',
    'Macron', 'Starmer', 'Modi',
    'Ukraine', 'Russia', 'Taiwan', 'Israel', 'Gaza', 'North Korea',
    'Iran', 'NATO', 'European Union', 'ASEAN',
    'election', 'summit', 'diplomatic', 'sanctions', 'negotiation',
    'ceasefire', 'treaty', 'alliance', 'state visit',
    'war', 'invasion', 'missile', 'drone strike', 'troops',
    'military', 'navy', 'air force', 'defense', 'offensive',
    'nuclear', 'weapons', 'arms', 'Pentagon',
    'UN Security Council', 'WHO', 'IMF', 'World Bank',
    'G7', 'G20', 'BRICS',
    'Olympics', 'World Cup', 'FIFA', 'IOC',
    'protest', 'coup', 'regime', 'parliament', 'congress',
    'space station', 'moon landing', 'Mars mission',
})

JUNK_KW = frozenset({
    '减肥药', '处方药', '药监局', '药品监管', '保健品',
    '中超', 'NBA', 'CBA', '欧冠', '英超', '西甲', '足球', '篮球',
    '综艺', '选秀', '明星', '八卦', '电视剧', '电影', '票房', '蒜薹',
    '食谱', '养生', '健康知识', '谣言', '辟谣', '瞎扯', '吐槽', '段子',
    '知乎日报', '知乎', '网络文明', '群众路线', '宣传', '峰会', '论坛',
    '大会', '可持续发展', '盘中', '股市', 'A股', '美股', '涨停', '跌停',
    '情书', '娱乐圈', '粉丝', '广告', '促销', '天猫', '京东', '双11',
})

ALL_KEYWORDS = {
    'game': GAME_KW, 'tech': TECH_KW, 'economy': ECONOMY_KW,
    'safety': SAFETY_KW, 'politics': POLITICS_KW, 'junk': JUNK_KW,
}

# ── AC 自动机加速（v5.2.0） ───────────────────────────────────────────
try:
    import ahocorasick
    _HAS_AC = True
except ImportError:
    _HAS_AC = False

_AC_CACHE: dict[str, "ahocorasick.Automaton"] = {}
_AC_WARNED = False


def get_ac(tag: str, kw_set: frozenset):
    if tag in _AC_CACHE:
        return _AC_CACHE[tag]
    A = ahocorasick.Automaton()
    for k in kw_set:
        A.add_word(k, k)
    A.make_automaton()
    _AC_CACHE[tag] = A
    return A


def has_keyword_match(text: str, tag: str, kw_set: frozenset) -> bool:
    global _AC_WARNED
    if _HAS_AC:
        return next(get_ac(tag, kw_set).iter(text), None) is not None
    if not _AC_WARNED:
        print('[INFO] ahocorasick 未安装，使用线性匹配（推荐 pip install pyahocorasick）', file=__import__('sys').stderr)
        _AC_WARNED = True
    return any(k in text for k in kw_set)


def has_keyword_match_ci(text: str, tag: str, kw_set: frozenset) -> bool:
    """Case-insensitive variant — lowercases both pattern and text."""
    text_lower = text.lower()
    if _HAS_AC:
        return next(get_ac(f'{tag}_ci', frozenset(k.lower() for k in kw_set)).iter(text_lower), None) is not None
    return any(k.lower() in text_lower for k in kw_set)
