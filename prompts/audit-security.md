# 安全 & 配置审计

**目标：** 检查 TrendRadar 的潜在安全风险 — 凭证管理、配置漂移、敏感数据暴露。

**范围：** `.env` 文件、`config/` 目录、`data/` 目录、shell 脚本中的凭证引用、git 跟踪的内容、跨环境路径假设。

**审计方向（不限于）：**

1. **API 凭证管理** — DEEPSEEK_API_KEY 的加载路径（`TRENDRADAR_HOME/.env` vs `~/.hermes/.env` vs 手动 `export`）。凭证有没有出现在 git 历史、日志、cron output 文件中？`gen_cron_prompt.py` 生成的 prompt 里是否暴露了任何秘密？

2. **Git 跟踪的数据** — `data/sources.json` 中是否含 API key / token？`config/` 下的 YAML 是否含凭据？如果有数据文件被 git 跟踪，`git reset --hard` / `git clean` 时用户是否会丢失运行时数据？目前的缓解措施够吗？

3. **跨环境配置漂移** — `settings.py`、`.env`、`ai_interests.yaml`、`sources.json` 之间的关系。哪些配置只在 `.env` 里，哪些在 git 里，哪些靠手动同步？新增环境（换台机器、CI runner）时最少要配置几步？

4. **shell 注入风险** — `subprocess.run(..., shell=True)` 的使用点、`f"export PYTHON={PYTHON}"` 这类字符串拼接的参数来源。如果某个配置项被意外写入特殊字符，什么会坏？

5. **权限与边界** — cron job 运行的 uid/gid、文件权限（cron output 是 `-rw-------`，这够吗？）、读写 `data/` 目录的所有路径是否一致。

**输出格式：** 按风险类型分组，每条标注（🔴 可被利用 / 🟡 需要加固 / 🔵 建议关注），附一句话判断依据。
