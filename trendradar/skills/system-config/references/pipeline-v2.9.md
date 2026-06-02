# Pipeline v2.9.0: Subprocess → Direct Function Call

## 架构变更

v2.8.0 及之前：pipeline_orchestrator 对每个 stage 启动子进程 (`subprocess.run(cmd)`)。

v2.9.0：所有 stage 改为直接 import + 函数调用。

```
# v2.8 (old)
prep_cmd = [PYTHON, "push_prepare.py", "--push-id", push_id]
prep = run_stage("push_prepare", prep_cmd)  # spawns subprocess

# v2.9 (new)
from trendradar.scripts.push_prepare import run_curation
prep = run_stage("push_prepare", run_curation, push_id)  # direct call
```

## run_stage() 签名变更

```python
# v2.8
def run_stage(name: str, cmd: list, timeout: int = 300) -> dict

# v2.9
def run_stage(name: str, func, *args, timeout: int = 300, **kwargs) -> dict
    # Returns: {'ok': bool, 'result': any, 'elapsed': float, 'error': str|None}
```

## 各 Stage 提取的纯函数

| Stage | 脚本 | 提取函数 | 签名 |
|-------|------|---------|------|
| 0 | push_slot_detect.py | `detect_current_slot()` | `-> dict \| None` (keys: push_id, dedup_flag, ...) |
| 1 | push_prepare.py | `run_curation(push_id)` | `-> dict` (已存在) |
| 2 | track_events.py | `load_curated()` + `compare()` | 内联 lambda |
| 3 | ai_translate.py | `process_curated(push_id)` | `async -> dict` (已存在) |
| 4 | render_markdown.py | `render_briefing(push_id)` | `-> str` (新增) |
| 5 | fragment_push.py | `split_fragments(markdown)` | `-> list[str]` (已存在) |
| 6 | record_fingerprints.py | `record(push_id)` | 副作用 (已存在) |

## 异步阶段处理

ai_translate 为串行阶段（batch_fetch 已移除）：

```python
def _run_translate():
    from trendradar.scripts.ai_translate import process_curated
    return asyncio.run(process_curated(push_id))

def _run_fetch():
    return asyncio.run(bf(push_id))

with ThreadPoolExecutor(max_workers=2) as executor:
    fut_translate = executor.submit(lambda: run_stage("translate", _run_translate))
    fut_fetch = executor.submit(lambda: run_stage("fetch", _run_fetch))
    translate_result = fut_translate.result()
    fetch_result = fut_fetch.result()
```

## 删除的 dead code

- `_run()` — subprocess runner
- `detect_slot()` / `detect_push_id()` — subprocess-based slot detection
- `_ALLOWED_ENV` / `_ENV` — env var whitelist for subprocess (no longer needed)
- `import subprocess`

## push_slot_detect.py 重构

原版有模块级副作用（`import` 时读 timeline.yaml、`sys.exit`）。重构后：
- `detect_current_slot()` — 纯函数入口
- `_load_slots()` — 带缓存的 YAML 解析
- `main()` — CLI 入口（保留 --minutes-until / --next-slot 模式）

## 回退兼容

CLI 子进程模式仍可通过 `python3 pipeline_orchestrator.py --push-id noon` 运行，但内部已全部走直接调用。Cron 无需任何改动。
