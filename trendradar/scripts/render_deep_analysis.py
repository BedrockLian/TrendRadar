#!/usr/bin/env python3
from trendradar.scripts.common import CST
"""
render_deep_analysis.py — 格式化 Pro 深度分析用于 WeCom 推送。

v2.0: 新增实体提取 + 历史关联（知识图谱化）
- 提取公司名、技术词、人物
- 查询 fingerprints.db 过去 7 天相似条目
- 在分析末尾追加 "📌 相关回顾" 行

用法:
  cat analysis.txt | python3 render_deep_analysis.py --topic "AI · 科技趋势"
  python3 render_deep_analysis.py --topic "趋势" --push-id evening --file analysis.txt
"""
import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import Counter

from trendradar.scripts.file_utils import get_data_dir
DATA_DIR = get_data_dir()


# ── 实体提取 ──────────────────────────────────────────────────
# 技术/公司/人物关键词（可扩展）
ENTITY_PATTERNS = {
    'company': re.compile(
        r'\b(NVIDIA|Apple|Google|Microsoft|Meta|OpenAI|Anthropic|DeepSeek|'
        r'Tesla|BYD|Huawei|AMD|Intel|Qualcomm|TSMC|Samsung|'
        r'腾讯|阿里|字节|百度|华为|比亚迪|宁德时代|小米)\b',
        re.IGNORECASE
    ),
    'tech': re.compile(
        r'\b(GPU|CPU|AI|LLM|RAG|transformer|diffusion|Blackwell|Hopper|'
        r'H100|B200|GPT|Claude|Gemini|ChatGPT|Copilot|AGI|'
        r'大模型|芯片|半导体|自动驾驶|量子|核聚变)\b',
        re.IGNORECASE
    ),
    'person': re.compile(
        r'\b(黄仁勋|Sam Altman|Elon Musk|Jensen Huang|Satya Nadella|'
        r'Sundar Pichai|Tim Cook|李彦宏|雷军|任正非|张一鸣)\b',
        re.IGNORECASE
    ),
}


def extract_entities(text: str) -> dict[str, list[str]]:
    """Extract companies, tech terms, and persons from analysis text."""
    entities = {}
    for category, pattern in ENTITY_PATTERNS.items():
        found = list(set(pattern.findall(text)))
        if found:
            entities[category] = found
    return entities


def find_historical_context(entities: dict[str, list[str]], push_id: str, days: int = 7) -> list[dict]:
    """Query fingerprints.db for historical items matching extracted entities.

    Returns list of {title, date, source} items, up to 3 most relevant.
    """
    db_path = DATA_DIR / 'fingerprints.db'
    if not db_path.exists():
        return []

    all_terms = []
    for cat_terms in entities.values():
        all_terms.extend(cat_terms)

    if not all_terms:
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now(CST) - timedelta(days=days)).isoformat()

        results = []
        seen_titles = set()

        for term in all_terms[:8]:  # limit search terms
            rows = conn.execute(
                """SELECT title, push_time, source_platform
                   FROM fingerprints
                   WHERE (title LIKE ? OR summary LIKE ?)
                     AND push_time > ?
                   ORDER BY push_time DESC
                   LIMIT 3""",
                (f'%{term}%', f'%{term}%', cutoff)
            ).fetchall()

            for row in rows:
                title = row['title']
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                try:
                    dt = datetime.fromisoformat(row['push_time'])
                    date_str = dt.strftime('%m月%d日')
                except (ValueError, TypeError):
                    date_str = '近期'

                source = (row['source_platform'] or '').split('+')[0].strip()[:15]
                results.append({
                    'title': title[:60],
                    'date': date_str,
                    'source': source,
                })

        conn.close()
        return results[:3]  # max 3 historical references
    except Exception:
        return []


def format_historical_context(historical: list[dict]) -> str:
    """Format historical items as '📌 相关回顾' section."""
    if not historical:
        return ""

    lines = ["", "📌 **相关回顾**"]
    for item in historical:
        lines.append(f"  [{item['date']}] {item['title']} ({item['source']})")
    return '\n'.join(lines)


# ── 原有格式化逻辑 ──────────────────────────────────────────


def clean(text: str) -> str:
    """Strip WeCom-unsupported markdown, keep natural structure."""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'^\|[^\n]+\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\|[-:\s:|]+\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n\s*[-*_]{3,}\s*\n', '\n\n', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


_EMOJI_MAP = {
    '趋势': '📈', '方向': '🎯', '分析': '🔍',
    '总结': '📌', '结论': '📌', '影响': '⚡',
    '风险': '⚠️', '机会': '💡', '观点': '💭',
    '启示': '✨', '展望': '🔭',
}


def format_analysis(text: str, topic: str = "深度分析",
                    push_id: str = None, add_context: bool = False) -> str:
    """Format analysis text for WeCom push.

    If add_context=True, extracts entities, queries historical context,
    and appends '📌 相关回顾' section at the end.
    """
    text = clean(text)
    parts = [f"🔬 **{topic}**"]
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if paragraphs and ('#' in paragraphs[0] or topic.replace('**', '') in paragraphs[0]):
        paragraphs = paragraphs[1:]
    for para in paragraphs:
        lines = para.split('\n')
        cleaned = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^[-*•]\s+', '', line)
            line = re.sub(r'^\d+[.、]\s+', '', line)
            line = re.sub(r'^[#*]+\s*', '', line).strip()
            if line:
                cleaned.append(line)
        if not cleaned:
            continue
        first = cleaned[0]
        for kw, emoji in _EMOJI_MAP.items():
            if kw in first and len(first) < 25:
                parts.append(f"{emoji} **{first}**")
                if len(cleaned) > 1:
                    parts.append('\n'.join(cleaned[1:]))
                break
        else:
            parts.append('\n'.join(cleaned))

    result = '\n\n'.join(parts)

    # ── Knowledge graph: historical context ─────────────────
    if add_context:
        entities = extract_entities(text)
        if entities:
            historical = find_historical_context(entities, push_id or 'evening')
            context_section = format_historical_context(historical)
            if context_section:
                result += '\n' + context_section

    # Truncation
    if len(result) > 1600:
        result = result[:1580]
        last_nl = result.rfind('\n\n')
        if last_nl > 600:
            result = result[:last_nl]
    return result


def main():
    parser = argparse.ArgumentParser(description='格式化 Pro 深度分析 + 知识图谱')
    parser.add_argument('--topic', default='深度分析')
    parser.add_argument('--push-id', help='推送时段 (用于历史关联查询)')
    parser.add_argument('--context', action='store_true',
                        help='启用历史关联（实体提取 + 相关回顾）')
    parser.add_argument('--file', type=str, help='从文件读取（默认 stdin）')
    args = parser.parse_args()

    if args.file:
        text = Path(args.file).read_text(encoding='utf-8')
    else:
        text = sys.stdin.read()

    print(format_analysis(text, args.topic, args.push_id, args.context))


if __name__ == '__main__':
    main()
