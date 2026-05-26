#!/usr/bin/env python3
"""
sanity_check.py — 发布前拦截器（Interceptor）

在 pipeline_orchestrator 最后一步运行，对即将推送的简报执行：
0. 编排器前言剥离 — 移除编排器状态行（push_id / deep_analysis / 迁移错误等）再检查
1. 禁语扫描 — 检测 AI 废话（"As an AI language model" 等）
2. 死链检测 — HEAD 请求前 3 个链接，404 标记 EXIT_PARTIAL
3. 敏感词脱敏 — 特定 domain 合规性脱敏
4. HTML 残留 — 检测未清理的 <br>/<div>/``` 等标记

编排器前言示例（这些行会被自动剥离，不参与禁语/格式检查）：
  编排器完成，状态 ok（push_id=morning，needs_deep_analysis=false，无需深度分析）
  record_fingerprints 遇到非致命 SQL 迁移错误，不影响简报内容
  开始输出简报正文：

用法:
  $PYTHON scripts/sanity_check.py < rendered_briefing.md  # stdin 模式
  $PYTHON scripts/sanity_check.py --push-id noon           # 主动检测

退出码:
  0 = 通过
  2 = 有警告但不阻塞
  3 = EXIT_PARTIAL（死链/格式问题，可降级推送）
  99 = EXIT_FATAL（禁语/内容问题，拒绝推送）
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── 禁语表 — 任何一条命中 → EXIT_FATAL ──────────────────────
BANNED_PHRASES = [
    "As an AI language model",
    "As an AI,",
    "Here is your report",
    "Here is the report",
    "Here's your",
    "I hope this",
    "Let me know if",
    "Feel free to",
    "If you have any",
    "I've generated",
    "I have generated",
    "Below is",
    "The following is",
    "Certainly!",
    "Sure! Here",
    "Of course!",
]

# ── 编排器前言 — 匹配 pipeline_orchestrator 输出的状态行 ───
# 这些行是编排器元数据，不是简报正文，剥离后再做禁语/格式检查。
# 典型输出：
#   编排器完成，状态 ok（push_id=morning，needs_deep_analysis=false，无需深度分析）
#   record_fingerprints 遇到非致命 SQL 迁移错误，不影响简报内容
#   开始输出简报正文：
ORCHESTRATOR_PREAMBLE_PATTERNS = [
    # 编排器状态行
    r'^编排器完成.*$',
    r'^编排器.*状态.*$',
    # 非致命错误/警告行
    r'^record_fingerprints\s+遇到非致命.*$',
    r'遇到非致命.*不影响.*$',
    # 简报正文开始标记
    r'^开始输出简报正文[：:]?\s*$',
    # pipeline 通用状态标记
    r'^\[PIPELINE\].*$',
    r'^\[ORCHESTRATOR\].*$',
]

# ── HTML/标记残留 ──────────────────────────────────────────
HTML_RESIDUE_PATTERNS = [
    (r'<br\s*/?>', '<br> 标签'),
    (r'<div[^>]*>', '<div> 标签'),
    (r'</div>', '</div> 标签'),
    (r'<p[^>]*>', '<p> 标签'),
    (r'</p>', '</p> 标签'),
    (r'```[a-z]*', '代码块残留'),
    (r'\|[-:\s|]+\|', '表格残留'),
    (r'<script', '<script> 标签'),
]

# ── 敏感词脱敏（per-domain） ────────────────────────────────
DOMAIN_SENSITIVE = {
    'foreign_china': [
        (r'(台湾)(?!海峡|问题|同胞|地区)', r'\1地区'),
        (r'(西藏)(?!高原|自治区)', r'\1自治区'),
    ],
}


def _extract_urls(text: str, limit: int = 3) -> list[str]:
    """Extract URLs from markdown links."""
    urls = re.findall(r'\]\((https?://[^)\s]+)\)', text)
    return urls[:limit]


def strip_orchestrator_preamble(text: str) -> tuple[str, list[str]]:
    """剥离编排器前言状态行，返回 (clean_text, stripped_lines)。

    编排器在输出简报前可能打印状态信息：
    - "编排器完成，状态 ok（push_id=...）"
    - "record_fingerprints 遇到非致命 SQL 迁移错误，不影响简报内容"
    - "开始输出简报正文："

    这些行是编排器元数据，不是简报内容。剥离后再做禁语/格式检查，
    否则编排器的正常输出（如 "Below is" 的翻译）会误触禁语。
    """
    stripped = []
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        if any(re.match(p, line) for p in ORCHESTRATOR_PREAMBLE_PATTERNS):
            stripped.append(line)
        else:
            clean_lines.append(line)
    return '\n'.join(clean_lines), stripped


def check_banned_phrases(text: str) -> list[str]:
    """Scan for banned AI phrases. Returns list of matches."""
    hits = []
    for phrase in BANNED_PHRASES:
        if phrase.lower() in text.lower():
            hits.append(phrase)
    return hits


def check_html_residue(text: str) -> list[str]:
    """Scan for un-stripped HTML/markup tags. Returns list of descriptions."""
    hits = []
    for pattern, desc in HTML_RESIDUE_PATTERNS:
        if re.search(pattern, text):
            hits.append(desc)
    return hits


def check_dead_links(text: str, timeout: int = 5) -> list[str]:
    """HEAD request first 3 URLs. Returns list of dead links (404/connection error)."""
    urls = _extract_urls(text)
    dead = []

    def _check_one(url):
        try:
            req = urllib.request.Request(url, method='HEAD')
            req.add_header('User-Agent', 'TrendRadar/2.0 SanityCheck')
            urllib.request.urlopen(req, timeout=timeout)
            return None  # OK
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return f"{url} → 404"
            return None  # 403/500/etc — not our problem
        except Exception:
            return f"{url} → unreachable"

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {ex.submit(_check_one, url): url for url in urls}
        for fut in as_completed(futures, timeout=timeout + 2):
            result = fut.result()
            if result:
                dead.append(result)

    return dead


def apply_sensitive_filter(text: str, domain: str) -> tuple[str, list[str]]:
    """Apply per-domain sensitive word filter. Returns (filtered_text, changes_made)."""
    changes = []
    patterns = DOMAIN_SENSITIVE.get(domain, [])
    for pattern, replacement in patterns:
        matches = re.findall(pattern, text)
        if matches:
            text = re.sub(pattern, replacement, text)
            changes.append(f"{domain}: {pattern} → {replacement} ({len(matches)} occurrences)")
    return text, changes


def main():
    parser = argparse.ArgumentParser(description='发布前内容拦截器')
    parser.add_argument('--push-id', help='当前推送时段 (用于 domain 脱敏)')
    parser.add_argument('--check-links', action='store_true', default=True,
                        help='检测死链 (默认开启)')
    parser.add_argument('--no-check-links', dest='check_links', action='store_false',
                        help='跳过死链检测')
    parser.add_argument('--json', action='store_true',
                        help='输出 JSON 结果')
    parser.add_argument('--file', type=str,
                        help='从文件读取简报（默认 stdin）')
    args = parser.parse_args()

    # Read input
    if args.file:
        text = Path(args.file).read_text(encoding='utf-8')
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"pass": True, "warnings": []}, ensure_ascii=False))
        return 0

    # 0) Strip orchestrator preamble before checking
    text, stripped = strip_orchestrator_preamble(text)
    if stripped:
        print(f"[SANITY] Stripped {len(stripped)} orchestrator preamble line(s)", file=sys.stderr)

    issues = []
    warnings = []
    fatal = False

    # 1) Banned phrase check
    banned = check_banned_phrases(text)
    if banned:
        fatal = True
        for b in banned:
            issues.append(f"FATAL: 禁语 '{b}'")

    # 2) HTML residue
    residue = check_html_residue(text)
    for r in residue:
        warnings.append(f"HTML残留: {r}")

    # 3) Dead link check
    if args.check_links:
        dead = check_dead_links(text)
        for d in dead:
            warnings.append(f"死链: {d}")

    # 4) Sensitive word filter
    if args.push_id:
        # Determine domain from push_id context
        text, changes = apply_sensitive_filter(text, 'foreign_china')
        for c in changes:
            warnings.append(f"脱敏: {c}")

    # Output
    if args.json:
        result = {
            "pass": not fatal and len(warnings) == 0,
            "fatal": fatal,
            "issues": issues,
            "warnings": warnings,
        }
        print(json.dumps(result, ensure_ascii=False))
    else:
        for i in issues:
            print(f"[SANITY] ❌ {i}", file=sys.stderr)
        for w in warnings:
            print(f"[SANITY] ⚠️ {w}", file=sys.stderr)
        if not issues and not warnings:
            print("[SANITY] ✅ Passed", file=sys.stderr)

    if fatal:
        sys.exit(99)  # EXIT_FATAL
    elif warnings:
        sys.exit(3)   # EXIT_PARTIAL
    return 0


if __name__ == '__main__':
    main()
