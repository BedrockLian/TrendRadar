#!/usr/bin/env python3
"""Generate the Codex plan prompt from the repository's two SSOT files."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from trendradar.runtime.common import CST
from trendradar.runtime.output_protocol import configure_utf8_stdio, performance_budget_seconds
from trendradar.runtime.paths import CONFIG_DIR

SCRIPTS_DIR = Path(__file__).resolve().parent
PLAN_PATH = CONFIG_DIR / "plan.json"
PYTHON = os.environ.get("PYTHON", sys.executable)


def load_plan() -> dict:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def get_pipeline_steps() -> dict:
    from trendradar.pipeline.pipeline_orchestrator import list_pipeline_steps, __version__

    result = list_pipeline_steps()
    result["version"] = __version__
    result["python"] = PYTHON
    return result


def generate_cron_prompt(steps: dict, plan: dict | None = None) -> str:
    plan = plan or load_plan()
    lines = [
        f"<!-- auto-generated: {datetime.now(CST).isoformat()} -->",
        "# TrendRadar Codex 计划任务",
        "",
        "> 本文件由 `src/trendradar/cli/gen_cron_prompt.py` 生成。",
        "> 计划清单唯一来源：`src/trendradar/config/plan.json`。",
        "",
        "## 执行约定",
        "",
        f"- 计划说明：{plan.get('description', 'TrendRadar Codex 本地任务计划')}。",
        f"- 时区：`{plan.get('timezone', 'Asia/Shanghai')}`。",
        f"- 日报全链路预算：`{plan.get('performance_budget_seconds', performance_budget_seconds())}` 秒。",
        f"- Python：`{PYTHON}`。",
        "- 运行入口只生成结构化 JSON 和 Markdown 文件；最终回复由 Codex 任务负责把 Markdown 本体直接输出到当前聊天框。",
        "- `status=silent` 时结束任务，不补造内容；`status=error` 时报告错误和产物路径。",
        "- `status=ok` 时直接使用 JSON 中的 `briefing` 作为聊天正文，并保留 `stats` 作为运行摘要；不要用本地预览、浏览器链接或 artifact 路径替代正文。",
        "",
        "## 任务清单",
        "",
        "| 任务 | 时间 | 入口 | 预算 | 描述 |",
        "|---|---|---|---:|---|",
    ]
    for job in plan.get("jobs", []):
        lines.append(
            f"| `{job['id']}` | `{job['schedule']}` | `{job['entrypoint']}` | "
            f"{job.get('timeout_seconds', '')}s | {job.get('description', '')} |"
        )

    lines.extend([
        "",
        "## 日报任务",
        "",
        "```text",
        f"{PYTHON} -m trendradar.pipeline.pipeline_orchestrator --output json",
        "```",
        "Codex 读取 stdout 的单个 JSON 对象：",
        "",
        "1. `status=ok`：将 `briefing` Markdown 本体直接输出到当前聊天框，并报告 `stats.budget` 是否在预算内。",
        "2. `status=silent`：记录本次没有新内容，不生成补充性文字。",
        "3. `status=busy`：等待或跳过本轮，保留已有任务运行。",
        "4. `status=error`：展示 `errors`，同时指出 `artifacts` 中可供诊断的文件。",
        "",
        "## 编排步骤",
        "",
        f"Pipeline v{steps.get('version', 'unknown')}：",
        "",
        "| # | 阶段 | 入口 | 说明 |",
        "|---:|---|---|---|",
    ])
    for step in steps.get("steps", []):
        lines.append(
            f"| {step.get('number', '?')} | {step.get('name', '?')} | "
            f"{step.get('script', step.get('func', ''))} | {step.get('description', '')} |"
        )

    lines.extend([
        "",
        "## 参考资料",
        "",
        "- `docs/INDEX.md`：文档入口。",
        "- `docs/PIPELINE.md`：数据流和输出协议。",
        "- `docs/OPERATIONS.md`：维护、体检和看门狗规则。",
        "- `docs/TRAPS.md`：已知风险和恢复方式。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    configure_utf8_stdio()
    print(generate_cron_prompt(get_pipeline_steps()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
