"""Load AI interests configuration from ai_interests.yaml/txt.

Parses interest config, extracting positive and negative keyword frozensets
using Chinese sliding-window and English keyword extraction.
"""

import re
from pathlib import Path
from functools import lru_cache

from trendradar.scripts.settings import TRENDRADAR_HOME


@lru_cache(maxsize=1)
def load_interests() -> tuple[frozenset, frozenset]:
    """加载 config/ai_interests.yaml，返回 (正面关键词, 排除关键词) 两个 frozenset。
    
    中文用滑窗提取 2-3 字关键片段，英文保留专有名词/缩写。
    回退支持旧版 .txt 格式。
    """
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
