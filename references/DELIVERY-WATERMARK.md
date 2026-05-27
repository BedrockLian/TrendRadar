<!-- version: 1.0.0 | created: 2026-05-27 -->

# 送达水印（delivery_marker）机制

## 概述

delivery_marker 系统提供了一种可靠的方式来追踪定时推送是否实际送达终端用户（企业微信）。由于 `pipeline_orchestrator.py` 报告 `status=ok` 并不能保证用户收到了简报，送达标记作为送达确认的可信依据。

## 架构

### MarkerDir

位置：`data/delivery_markers/`

每次推送创建名为 `{date}_{slot}.marker` 的标记文件，内容如下：
```json
{
  "push_id": "morning",
  "date": "2026-05-27",
  "pipeline_status": "ok",
  "fragment_count": 3,
  "delivered": true,
  "delivered_at": "2026-05-27T09:05:23+08:00",
  "verified_by": "delivery_watchdog"
}
```

### 标记状态

| 状态 | 含义 |
|------|------|
| `delivered: true` | 已确认送达企业微信 |
| `delivered: false` | 管道已运行但送达未确认 |
| 无标记文件 | 管道未运行或在创建标记前失败 |

## delivery_watchdog.py

送达看门狗（cron `cab79825520e`，以 `no_agent=true` 运行）定期检查 `push_log.json` 中最近的管道运行记录，并验证对应的送达标记是否存在且显示 `delivered: true`。

如果某次管道运行没有送达标记或显示 `delivered: false`，看门狗会触发自动补推：
1. 从 `archive/{date}/{slot}.md` 读取归档简报
2. 验证归档文件存在且非空
3. 通过相同的自动投递机制重新送达（最终回复到企业微信）
4. 用新的送达时间戳更新标记

### 看门狗调度
- 每 15 分钟运行一次
- 检查 push_log.json 中最近 2 小时的条目
- 验证早间（09:00）、午间（12:00）、晚间（21:00）时段的标记

## 手动标记送达

### 手动创建标记
```bash
mkdir -p data/delivery_markers
cat > data/delivery_markers/2026-05-27_morning.marker << 'EOF'
{
  "push_id": "morning",
  "date": "2026-05-27",
  "pipeline_status": "ok",
  "fragment_count": 3,
  "delivered": true,
  "delivered_at": "2026-05-27T09:05:23+08:00",
  "verified_by": "manual"
}
EOF
```

### 查看今日送达状态
```bash
ls -la data/delivery_markers/$(date +%Y-%m-%d)_*.marker
```

### 手动补推后标记送达
```bash
# 使用 archive_resend.py 补推后
echo '{"delivered": true, "delivered_at": "'$(date -Iseconds)'", "verified_by": "manual_resend"}' \
  | python3 -c "
import json, sys
from pathlib import Path
marker = Path('data/delivery_markers/2026-05-27_morning.marker')
data = json.loads(marker.read_text()) if marker.exists() else {}
data.update(json.loads(sys.stdin.read()))
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_text(json.dumps(data, ensure_ascii=False, indent=2))
"
```

## 与管道的集成

管道编排器（`pipeline_orchestrator.py`）在每次运行后写入 `push_log.json`。看门狗使用此日志作为触发源。

标记文件通过提供送达确认（而不仅仅是管道执行确认）来补充 `push_log.json`。

## 已知故障模式（触发补推的场景）

1. **送达窗口期间 Gateway WebSocket 断开**：管道运行，分片已生成，但 WebSocket 在最终回复送达前断开 → 标记显示 `delivered: false` → 看门狗从归档补推。

2. **DeepSeek API 流截断**：管道报告 `ok` 但内容不完整。看门狗无法修复内容，但确保已产出的内容能被送达。

3. **Cron agent 在管道完成后、送达前崩溃**：管道已完成，push_log.json 已更新，但 agent 在输出最终回复前崩溃 → 未发生送达。看门狗检测到标记缺失并补推。

## 与 archive_resend.py 的关系

`archive_resend.py` 是手动补推工具 — 需要人工触发。
`delivery_watchdog.py` 是自动补推工具 — 在 cron 上运行。

两者都从同一归档（`archive/{date}/{slot}.md`）读取，并且都在成功送达后创建/更新送达标记。
