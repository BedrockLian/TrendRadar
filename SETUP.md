# TrendRadar 部署与运行

## 1. 安装

Windows：

```powershell
.\ops\codex\setup.ps1 -Python "C:\Users\ASUS\AppData\Local\Python\bin\python.exe"
```

跨平台：

```text
sh ops/codex/setup.sh
```

也可以直接执行：

```text
python -m pip install -e ".[dev]"
python -m trendradar.pipeline.pipeline_orchestrator --check-version
python ops/codex/health_check.py
```

## 2. 运行目录

未设置 `TRENDRADAR_HOME` 时，仓库内运行使用 `.runtime/`；设置后，数据、缓存、日志、归档、输出和锁文件都写入该目录。

```text
TRENDRADAR_HOME=D:\TrendRadar-runtime
```

路径统一由 [`src/trendradar/runtime/paths.py`](src/trendradar/runtime/paths.py) 解析，不要在脚本中重新定义。

## 3. 计划任务

任务时间、描述、入口、时区和预算唯一维护在 [`src/trendradar/config/plan.json`](src/trendradar/config/plan.json)。生成 Codex 计划提示：

```text
python -m trendradar.cli.gen_cron_prompt
```

## 4. 验收

```text
python -m trendradar.pipeline.pipeline_orchestrator --list-steps
python -m trendradar.pipeline.pipeline_orchestrator --push-id morning --skip-fetch --output json
python ops/codex/output_watchdog.py --slot morning
python -m pytest tests -q
```

日报结果必须包含 `stats.budget.within_budget=true`；失败时检查 `TRENDRADAR_HOME/data/run_log.jsonl`、`errors` 和输出产物。

完整设计见 [`docs/OPERATIONS.md`](docs/OPERATIONS.md)。
