# Cron 全量审计清单

当用户反馈推送异常或系统大修后，按以下六项逐条检查。

## ① Skills 引用完整性

```bash
hermes cron list | grep -E 'job_id|skills'
```

对每个 cron job，skills 列表中的每个 skill 名必须存在于：
```bash
ls ~/.hermes/skills/trendradar/
hermes skills list | grep <skill-name>
```

**常见问题：** skill 被重命名/整合后，cron job 的 skills 列表不会自动更新。需手动 `hermes cron update --job-id <id> --skills ...`

## ② 脚本文件存在性

对每个 LLM-driven job（`no_agent=false`），提取 prompt 中的 `scripts/*.py` 引用，确认文件存在且非空：

```bash
ls -la ~/.hermes/trendradar/scripts/<referenced-script>.py
```

**高危模式：** `render_briefing.py` 已被删除，prompt 中出现即过期引用。

## ③ no_agent 脚本检查

```bash
ls ~/.hermes/scripts/<script-name>
```

每个 no_agent job 引用的脚本必须在 `~/.hermes/scripts/` 下存在且可执行。

## ④ workdir 引用文件

```bash
ls ~/.hermes/trendradar/references/ | wc -l
```

skills 中的 `cat references/xxx.md` 依赖此目录。如果缺失：
```bash
cp -r ~/TrendRadar/trendradar/references/ ~/.hermes/trendradar/
```

## ⑤ 残留旧名扫描

```bash
grep -r 'render_briefing' ~/.hermes/skills/trendradar/ ~/.hermes/trendradar/references/
```

任何命中都是过期引用，需要清理。

## ⑥ Git 同步确认

```bash
cd ~/TrendRadar
git status --short
```
