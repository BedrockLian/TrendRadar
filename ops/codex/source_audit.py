#!/usr/bin/env python3
"""评估 RSS 来源的质量、权威度、更新频率和传输风险。

静态评分来自 source_evaluation.json；使用 --live 时，频率分由当前 RSS
最新条目年龄计算。聚合器和第三方中转不会因为原媒体品牌高而自动获得
官方直连等级，替代来源通过 fallback_ids 显式记录。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

CONFIG_DIR = PROJECT_ROOT / "src" / "trendradar" / "config"
SOURCES_PATH = CONFIG_DIR / "sources.json"
EVALUATION_PATH = CONFIG_DIR / "source_evaluation.json"


def load_scorecard() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8")).get("data_sources", [])
    evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    return sources, evaluation


def _merge_source(source: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    defaults = evaluation["category_defaults"].get(source.get("category"), {})
    override = evaluation.get("overrides", {}).get(source["id"], {})
    row = {**defaults, **source, **override}
    row["source_id"] = source["id"]
    row["quality_score"] = int(override.get("quality", defaults.get("quality", 3)))
    row["authority_score"] = int(override.get("authority", defaults.get("authority", 3)))
    if "cadence_target_hours" in override:
        cadence_target_hours = override["cadence_target_hours"]
    elif "freshness_days" in source:
        cadence_target_hours = int(source["freshness_days"]) * 24
    else:
        cadence_target_hours = defaults.get("cadence_target_hours", 24)
    row["cadence_target_hours"] = int(cadence_target_hours)
    row["source_kind"] = override.get(
        "source_kind", source.get("source_kind", defaults.get("source_kind", "publisher"))
    )
    row["transport_kind"] = override.get(
        "transport_kind", source.get("transport_kind", "official")
    )
    row["decision"] = override.get("decision", defaults.get("decision", "supplement"))
    row["official_url"] = override.get("official_url", source.get("official_url", source["feed_url"]))
    row["verification_url"] = override.get("verification_url", "")
    row["fallback_ids"] = list(override.get("fallback_ids", source.get("fallback_ids", [])))
    row["replacement_status"] = override.get(
        "replacement_status", source.get("replacement_status", "not_required")
    )
    row["notes"] = override.get("notes", "")
    return row


def freshness_score(age_hours: float | None, target_hours: int) -> int:
    if age_hours is None:
        return 0
    if age_hours <= target_hours:
        return 5
    if age_hours <= target_hours * 2:
        return 4
    if age_hours <= target_hours * 4:
        return 3
    if age_hours <= target_hours * 7:
        return 2
    return 1


def _weighted_score(row: dict[str, Any]) -> float | None:
    freshness = row.get("freshness_score")
    if freshness is None:
        return None
    dimensions = row["dimensions"]
    score = (
        dimensions["quality"] * 0.4
        + dimensions["authority"] * 0.4
        + freshness * 0.2
    )
    return round(score, 2)


def _make_row(source: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    merged = _merge_source(source, evaluation)
    return {
        "source_id": merged["source_id"],
        "name": merged["name"],
        "category": merged["category"],
        "quality_score": merged["quality_score"],
        "authority_score": merged["authority_score"],
        "cadence_target_hours": merged["cadence_target_hours"],
        "freshness_score": None,
        "weighted_score": None,
        "source_kind": merged["source_kind"],
        "transport_kind": merged["transport_kind"],
        "feed_url": merged["feed_url"],
        "official_url": merged["official_url"],
        "verification_url": merged["verification_url"],
        "fallback_ids": merged["fallback_ids"],
        "replacement_status": merged["replacement_status"],
        "decision": merged["decision"],
        "notes": merged["notes"],
        "status": "static",
        "items": None,
        "latest_age_hours": None,
    }


def _live_check(source: dict[str, Any]) -> dict[str, Any]:
    from trendradar.config.proxy import needs_proxy
    from trendradar.sources.fetch_feeds import _fetch_one

    freshness_days = int(source.get("freshness_days", 1))
    use_proxy = bool(source["needs_proxy"]) if "needs_proxy" in source else needs_proxy(source["feed_url"])
    try:
        _, items = _fetch_one(source["name"], source["feed_url"], freshness_days, use_proxy)
        now = datetime.now(timezone.utc)
        ages: list[float] = []
        for item in items:
            timestamp = item.get("timestamp")
            if not timestamp:
                continue
            try:
                published = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                ages.append(max(0.0, (now - published).total_seconds() / 3600))
            except ValueError:
                continue
        return {
            "status": "ok" if items else "empty_or_failed",
            "items": len(items),
            "latest_age_hours": round(min(ages), 1) if ages else None,
        }
    except Exception as exc:  # pragma: no cover - network dependent
        return {"status": "error", "items": 0, "latest_age_hours": None, "error": str(exc)[:160]}


def audit(live: bool = False) -> dict[str, Any]:
    sources, evaluation = load_scorecard()
    rows = [_make_row(source, evaluation) for source in sources if source.get("enabled", True)]
    source_by_id = {source["id"]: source for source in sources}

    if live:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            checks = list(executor.map(_live_check, [source_by_id[row["source_id"]] for row in rows]))
        for row, check in zip(rows, checks):
            row.update(check)
            row["freshness_score"] = freshness_score(
                row["latest_age_hours"], row["cadence_target_hours"]
            )
            row["weighted_score"] = _weighted_score({"dimensions": {
                "quality": row["quality_score"],
                "authority": row["authority_score"],
            }, "freshness_score": row["freshness_score"]})

    return {
        "protocol_version": 1,
        "status": "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "live": live,
        "source_count": len(rows),
        "summary": {
            "core": sum(row["decision"] == "core" for row in rows),
            "supplement": sum(row["decision"] == "supplement" for row in rows),
            "specialist": sum(row["decision"] == "specialist" for row in rows),
            "fallback_only": sum(row["decision"] == "fallback_only" for row in rows),
            "failed": sum(row["status"] in {"empty_or_failed", "error"} for row in rows),
        },
        "rows": rows,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# TrendRadar RSS 来源评判表",
        "",
        f"> 检查时间：`{result['checked_at']}`；实时检查：`{str(result['live']).lower()}`；来源数：`{result['source_count']}`",
        "",
        "| 来源 | 类别 | 质量 | 权威 | 频率 | 综合 | 传输 | 决策 | 状态 | 替代/备注 |",
        "|---|---|---:|---:|---:|---:|---|---|---|---|",
    ]
    for row in result["rows"]:
        freshness = "—" if row["freshness_score"] is None else str(row["freshness_score"])
        weighted = "—" if row["weighted_score"] is None else f"{row['weighted_score']:.2f}"
        latest = ""
        if row["latest_age_hours"] is not None:
            latest = f"最新 {row['latest_age_hours']}h"
        elif row["status"] != "static":
            latest = "无有效条目"
        note = row["replacement_status"]
        if row["fallback_ids"]:
            note += "；fallback=" + ",".join(row["fallback_ids"])
        if latest:
            note += "；" + latest
        lines.append(
            f"| [{row['name']}]({row['official_url']}) | {row['category']} | "
            f"{row['quality_score']} | {row['authority_score']} | {freshness} | {weighted} | "
            f"{row['transport_kind']} | {row['decision']} | {row['status']} | {note} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    from trendradar.runtime.output_protocol import configure_utf8_stdio

    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Audit TrendRadar RSS sources")
    parser.add_argument("--live", action="store_true", help="fetch every enabled source and score freshness")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    result = audit(live=args.live)
    if args.format == "markdown":
        print(render_markdown(result), end="")
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
