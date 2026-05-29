"""pytest fixtures for TrendRadar测试。"""
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# 把 scripts/ 和项目根目录加入 sys.path 以便导入被测模块
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
ROOT_DIR = SCRIPTS_DIR.parent  # trendradar/
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CST = timezone(timedelta(hours=8))
TEST_DATE = datetime.now(CST).strftime('%Y%m%d')


@pytest.fixture
def tmp_db():
    """创建临时目录，内含 fingerprints.db（含完整表结构），返回 (conn, tmp_dir)。"""
    import shutil
    tmp_dir = Path(tempfile.mkdtemp())
    db_path = tmp_dir / 'fingerprints.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute('''CREATE TABLE IF NOT EXISTS fingerprints (
        fingerprint TEXT PRIMARY KEY,
        title TEXT,
        summary TEXT,
        source_platform TEXT,
        url TEXT,
        push_id TEXT,
        push_time TEXT,
        created_at TEXT
    )''')
    conn.commit()
    yield conn, tmp_dir
    conn.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def sample_curated():
    """返回一个最小但合法的 curated JSON dict（模拟某时段精选结果）。"""
    return {
        'top_headlines': [
            {
                'title': '中国发布新一代AI芯片突破性进展',
                'summary': '中国科研团队在AI芯片领域取得重大突破',
                'source_platform': '路透社',
                'url': 'https://reuters.com/ai-china',
                'timestamp': f'{TEST_DATE}T09:00:00Z',
            },
            {
                'title': '普京访华签署多项合作协议',
                'summary': '中俄双方签署能源贸易等多项协议',
                'source_platform': 'BBC',
                'url': 'https://bbc.com/putin-china',
                'timestamp': f'{TEST_DATE}T08:30:00Z',
            },
        ],
        'foreign_china': [
            {
                'title': 'US weighs new chip export restrictions',
                'summary': 'The Biden administration is considering tighter semiconductor export controls targeting China.',
                'source_platform': 'Reuters',
                'url': 'https://reuters.com/us-chips',
                'timestamp': f'{TEST_DATE}T10:00:00Z',
            },
        ],
        'tech': [
            {
                'title': 'GPT-6 训练成本曝光',
                'summary': 'OpenAI内部文件显示GPT-6训练成本超50亿美元',
                'source_platform': 'The Verge',
                'url': 'https://theverge.com/gpt6',
                'timestamp': f'{TEST_DATE}T11:00:00Z',
            },
        ],
        'economy': [
            {
                'title': '4月青年失业率降至16.3%',
                'summary': '国家统计局公布4月青年失业率数据',
                'source_platform': '新华社',
                'url': 'https://xinhua.com/youth-employment',
                'timestamp': f'{TEST_DATE}T09:30:00Z',
            },
        ],
        'gaming': [
            {
                'title': '黑神话悟空DLC即将公布',
                'summary': '游戏科学将在下月公布黑神话悟空首个DLC',
                'source_platform': '机核',
                'url': 'https://gcores.com/wukong-dlc',
                'timestamp': f'{TEST_DATE}T12:00:00Z',
            },
        ],
    }
