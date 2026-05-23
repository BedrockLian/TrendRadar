#!/usr/bin/env python3
"""
render_deep_analysis.py — 格式化 Pro 深度分析用于 WeCom 推送。

清洗 LLM 输出中的 WeCom 不支持元素，保留自然段落结构。

用法:
  cat analysis.txt | python3 render_deep_analysis.py --topic "AI · 科技趋势"
"""
import re, sys, argparse


def clean(text: str) -> str:
    """Strip WeCom-unsupported markdown, keep natural structure."""
    # Remove code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove tables (lines with | separators)
    text = re.sub(r'^\|[^\n]+\|\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\|[-\s:|]+\|\s*$', '', text, flags=re.MULTILINE)
    # Remove horizontal rules
    text = re.sub(r'\n\s*[-*_]{3,}\s*\n', '\n\n', text)
    # Remove inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


_EMOJI_MAP = {
    '趋势': '📈', '方向': '🎯', '分析': '🔍',
    '总结': '📌', '结论': '📌', '影响': '⚡',
    '风险': '⚠️', '机会': '💡', '观点': '💭',
    '启示': '✨', '展望': '🔭',
}

def format_analysis(text: str, topic: str = "深度分析") -> str:
    """Format analysis text for WeCom push."""
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
        # Detect section heading
        for kw, emoji in _EMOJI_MAP.items():
            if kw in first and len(first) < 25:
                parts.append(f"{emoji} **{first}**")
                if len(cleaned) > 1:
                    parts.append('\n'.join(cleaned[1:]))
                break
        else:
            parts.append('\n'.join(cleaned))
    result = '\n\n'.join(parts)
    if len(result) > 1600:
        result = result[:1580]
        last_nl = result.rfind('\n\n')
        if last_nl > 600:
            result = result[:last_nl]
    return result


def main():
    parser = argparse.ArgumentParser(description='格式化 Pro 深度分析')
    parser.add_argument('--topic', default='深度分析')
    args = parser.parse_args()
    text = sys.stdin.read()
    print(format_analysis(text, args.topic))


if __name__ == '__main__':
    main()
