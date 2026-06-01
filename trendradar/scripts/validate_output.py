#!/usr/bin/env python3
"""validate_output.py — cron agent 最终输出格式验证。

cron prompt 步骤 3.5 管道使用：agent 输出 | validate_output.py --push-id {slot}

检查规则：
1. 内容以 `### Hermes日报` 开头（纯简报）或 `🔬` 开头（深度分析）
2. 不含 AI 废话前缀（"好消息"、"以下是"、"已格式化"、"所有三个深度分析"）
3. 不含编排器元数据行（"Pipeline returned"、"status=" 等）

不符合时自动回退：重新渲染存档 + 从 archive 取内容。
"""

import argparse
import json
import os
import re
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger('validate-output')

from trendradar.scripts.common import CST
TRENDRADAR_HOME = Path(os.environ.get(
    'TRENDRADAR_HOME',
    Path.home() / '.hermes' / 'trendradar'
))

# 违规前缀模式 — 命中则触发 fallback
BAD_PREFIXES = re.compile(
    r'^(好消息|以下[是]|所有|这里[是]|已经|已[经完]成|'
    r'Pipeline returned|Orchestrator|Outputting|'
    r'\\[SILENT\\]|DB schema|No deep analysis|'
    r'[=]{3,}|编排器执行完成|输出简报正文|无需深度分析|简报正文)',
    re.IGNORECASE,
)

# 违规模板 — 含这些必 fallback（非前缀匹配，全文扫描）
BAD_PATTERNS = re.compile(
    r'(所有三个深度分析|三条Pro深度分析|三篇深度分析)',
    re.IGNORECASE,
)

# 预期合法开头
GOOD_STARTS = re.compile(r'^(### Hermes日报|🔬|📊|—{3,})')

# 编排器元数据行
META_LINES = re.compile(
    r'^(Pipeline returned|\\[PIPELINE\\]|\\[SILENT\\]|'
    r'status=|errors?=|DB schema|No deep analysis|'
    r'---$)',
    re.IGNORECASE,
)


def validate(text: str) -> list[str]:
    """返回所有违规范式列表（空 = 合规）。"""
    violations = []

    stripped = text.strip()
    if not stripped:
        violations.append("内容为空")
        return violations

    # 1. 检查开头
    first_line = stripped.split('\n')[0].strip()
    if not GOOD_STARTS.match(first_line):
        violations.append(f"开头格式异常: {first_line[:80]}")

    # 2. 检查完全文禁语
    if BAD_PATTERNS.search(stripped):
        violations.append("包含违规模板")

    # 3. 逐段检查前缀
    for line in stripped.split('\n'):
        line_s = line.strip()
        if BAD_PREFIXES.match(line_s):
            violations.append(f"含违规前缀行: {line_s[:60]}")
            break  # 一条足矣

    return violations


def fallback(push_id: str) -> str:
    """从 archive 读取存档作为回退内容。"""
    today = datetime.now(CST).strftime('%Y-%m-%d')
    archive_path = TRENDRADAR_HOME / 'archive' / today / f'{push_id}.md'

    if archive_path.exists():
        content = archive_path.read_text(encoding='utf-8').strip()
        if content:
            return content

    # 再试一次：重新渲染
    try:
        python_bin = os.environ.get('PYTHON', sys.executable)
        import subprocess
        result = subprocess.run(
            [python_bin, str(TRENDRADAR_HOME / 'scripts' / 'render_markdown.py'),
             '--push-id', push_id],
            capture_output=True, text=True, timeout=30,
            env={
                'PYTHONPATH': str(TRENDRADAR_HOME.parent),
                'PYTHON_GIL': '0',
                'PATH': os.environ.get('PATH', ''),
                'HOME': os.environ.get('HOME', ''),
            },
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        log.warning("重渲染失败: %s", e)

    # 完全不可用
    print(f"[VALIDATE ERROR] 无法生成 {push_id} 简报 — 存档和渲染均失败", file=sys.stderr)
    return ''


def main():
    parser = argparse.ArgumentParser(description='Validate cron agent output format')
    parser.add_argument('--push-id', required=True,
                        choices=['morning', 'noon', 'evening'])
    args = parser.parse_args()

    # 读取 stdin（agent 的输出）
    agent_output = sys.stdin.read()

    violations = validate(agent_output)

    if not violations:
        # 合规 — 直接透传
        print(agent_output)
        return

    # 不合规 — 记录日志 + fallback
    print(
        f"[VALIDATE] {datetime.now(CST).strftime('%H:%M:%S')} "
        f"{args.push_id} 输出格式违规 ({'; '.join(violations)}) → fallback",
        file=sys.stderr,
    )

    fallback_content = fallback(args.push_id)
    if not fallback_content:
        # 彻底失败 — 输出原始内容（至少比空好）
        print(agent_output)
        sys.exit(1)

    print(fallback_content)


if __name__ == '__main__':
    main()
