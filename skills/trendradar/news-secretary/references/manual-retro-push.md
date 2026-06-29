# 手动补推工作流（2026-06-29 更新）

> **背景**：`slot_direct_push.py` 已不再存在。补投改用 `fragment_push + hermes send` 协议。

## 触发条件

- 用户说"补推早报/午报/晚报"、"今天没收到日报"、"重新推一下"
- health_check 显示 "archive 存在但 marker 缺失"

## 准备工作流

```bash
# 1. 验证 archive 存在
ls -l "$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)/"*.md

# 2. 验证 marker 不存在（否则看门狗会认为是重复投递）
ls -l "$TRENDRADAR_HOME/data/delivery_markers/"delivered_$(date +%Y%m%d)*

# 3. 确认 gateway 在跑
hermes gateway status
```

## 补投协议（archive 已有）

```bash
PY="$HERMES_HOME/hermes-agent/venv/Scripts/python.exe"
PYTHONPATH="$TRENDRADAR_HOME" "$PY" -c "
import json, subprocess, hashlib
from pathlib import Path
from datetime import datetime
from trendradar.scripts.fragment_push import split_fragments

SLOT = 'noon'  # 改为 morning / evening / noon
archive = Path('$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)') / f'{SLOT}.md'
if not archive.exists():
    print(f'❌ archive not found: {archive}')
    exit(1)

content = archive.read_text(encoding='utf-8')
fragments = split_fragments(content)
print(f'📤 {len(fragments)} fragments, {len(content.encode(\"utf-8\"))}B total')

for i, frag in enumerate(fragments):
    sz = len(frag.encode('utf-8'))
    print(f'  frag {i+1}/{len(fragments)} ({sz}B)...')
    r = subprocess.run(['hermes','send','--to','wecom:bl'],
        input=frag, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        print(f'  ❌ frag {i+1} failed: {r.stderr[:200]}')
        exit(1)
    print(f'  ✅ frag {i+1} delivered')

# Write marker
today = datetime.now().strftime('%Y%m%d')
run_id = f'{today}_{SLOT}'
marker_data = json.dumps({'status':'ok','fragments':len(fragments),'ts':datetime.now().isoformat()})
marker_dir = Path('$TRENDRADAR_HOME/data/delivery_markers')
marker_dir.mkdir(parents=True, exist_ok=True)
h = hashlib.md5(marker_data.encode()).hexdigest()[:8]
marker_path = marker_dir / f'delivered_{run_id}_{h}.marker'
marker_path.write_text(marker_data)
print(f'✅ marker: {marker_path.name}')
"
```

## 补投 evening deep analysis

deep analysis 由 sub-agent 各自用 `hermes send --to wecom:bl --subject "🔍 深度 · <主题>"` 投递，独立一条消息。
不需要走 fragment_push（每条深度分析不到 4KB）。

## 验证

```bash
# 重新跑 health_check 确认所有项正常
python3 "$HERMES_HOME/scripts/trendradar_health_check.py"
# 期望输出：静默（空输出 = 健康）
```
