<!-- version: 2.9.0 | last-reviewed: 2026-05-27 -->

# 已知陷阱

> 编号对应发现顺序。仅含当前有效的陷阱。历史已修复陷阱见 `traps-archive.md`。

## 1. Cron 模板变量陷阱
`{PUSH_ID}` 不会被 scheduler 展开。**修复**：步骤 0 先跑 `push_slot_detect.py` 获取真实参数。

## 2. delegate_task max_iterations 崩溃
非晚间误触发时子代理消耗 50 calls 后崩溃。**修复**：仅 evening 时段调用。

## 3. 英文摘要残留
外媒摘要必须翻译中文。**修复**：`data/sources.json` 中 `language` 字段定义翻译规则。

## 4. WeCom 分片丢失
>4000 字符 WeCom 静默截断。按板块分片，片间 1.5s。delegate_task 结果独立投递。cron 中通过 final response 自动投递，非 send_message。

## 5. 零前置文本违规
LLM 输出 "Now let me" / "Here is" 等过程描述会被推送到 WeCom。cron prompt 顶部禁止此类短语。

## 6. AC 自动机 + Free-Threaded 的 GIL
`pyahocorasick` C 扩展未声明 `Py_MOD_GIL_NOT_USED`。`PYTHON_GIL=0` 强制保持。

## 7. zstd 压缩副本单向
`write_compressed()` 写 `.json.zst` 但无脚本读——冷备份用途，非热数据路径。

## 8. Bracketless except 限制
`except A, B, C as e:` 是语法错误。需括号：`except (A, B, C) as e:`。

## 9. python3.14t 环境不完整
`--disable-gil` 编译的 Python ABI 不兼容标准 wheel。两个必需修复：
- **C 扩展缺失**：`_zstd`/`feedparser` 需 `python3.14t -m pip install zstandard feedparser`
- **PYTHONPATH 缺失**：cron prompt 必须 `export PYTHONPATH=/home/asus/.hermes`，否则 `ModuleNotFoundError: No module named 'trendradar'`。pyproject.toml 的 `[tool.pdm]` 配置对子 shell 无效。

## 10. translate.yaml 源名与 sources.json 不同步
重构 sources.json 时 translate.yaml 的旧源名不会自动失效——翻译静默跳过无报错。
**修复**：改 sources.json 后跑 `pytest tests/ -k translate_config`。

## 13. Gateway 崩溃 → 推送丢失但脚本报"成功"
Pipeline 报告投递成功，但 Gateway 同时崩溃消息未达 WeCom。
**信号**：`hermes gateway status` 显示 `failed`，用户反馈没收到但 cron 日志 ok。
**修复**：重启 Gateway → 补推 bypass（直接 render→fragment→final response 自动投递）。

## 14. Cron 技能名不匹配
技能重命名后 cron `skills` 列表仍引用旧名 → `⚠️ Skill(s) not found and skipped`。
**修复**：`cronjob action=update job_id=xxx skills=[...]`。重命名后必须同步 cron skills 列表 + SKILL.md companion_skills + system-config 文档。

## 15. Cron prompt 与 skill 内容不同步
cron prompt 是独立文本字段。skill 更新脚本名/步骤后 prompt 不自动更新。Agent 看到 skill 内容但优先执行 prompt 中的旧命令。
**信号**：prompt 引用已删除脚本（如 `render_briefing.py`）、旧技能名（`trendradar-news-secretary`）。
**修复**：`cronjob action=update job_id=xxx prompt="..."` 单独更新。每次改 pipeline 脚本名后检查所有 cron prompt。

## 16. tirith 安全扫描拦截中文命令 [已关闭]
中文/Unicode 内容触发规则匹配 → terminal 命令被拦截。**修复**：`hermes config set security.tirith_enabled false`。

## 17. push_slot_detect 返回 NO_SLOT 跳过推送
补推或跨时段手动触发时有时效窗口限制。**修复**：绕过 slot 检测，直接 render→fragment→final response 自动投递。不要重跑完整 pipeline（会变更数据状态）。

## 19. references/ 目录在 workdir 不存在
skill 内 `cat references/xxx.md` 依赖 workdir references/。如果不存在返回空。
**修复**：`cp -r ~/TrendRadar/trendradar/references/ ~/.hermes/trendradar/`。
**预防**：同步时确保 `~/.hermes/trendradar/references/` 与 `~/TrendRadar/trendradar/references/` 一致。

## 20. Cron prompt 引用已删除的辅助脚本
`blind_spot_audit.py` / `aggregate_monthly.py` 被周报/月报 prompt 引用但可能不存在。
**修复**：确认脚本存在于 workdir，或从仓库恢复。

## 22. Cron context 下投递机制 [已弃用 send_message]
`send_message` 工具在 cron 运行时**不可用**。pipeline 应始终将渲染好的简报作为 final response 输出，由系统自动投递到 WeCom。不要尝试在 cron 中用 send_message 逐片投递。
**信号**：日志有 "send_message isn't available" + agent 回退到 LLM 重新生成内容。
**修复**：cron prompt 指定——将 BRIEFING 作为最终输出，系统自动投递。详见 `cron-sendmessage-fallback.md`。

## 27. 健康检查子进程调用用错 Python 解释器
`trendradar_health_check.py` 的 `check_pipeline()` 在子进程中用 `sys.executable`（系统 python3）调用脚本。系统 python3 缺少 `feedparser`、`zstandard` 等仅装在 python3.14t 上的依赖 → 导入检查误报 `ModuleNotFoundError`。同时 `push_slot_detect` 也需要 `PYTHONPATH` 才能 `import trendradar.scripts.settings`。
**修复**：所有子进程调用统一走 `$PYTHON` 环境变量（fallback `/usr/local/bin/python3.14t`），设 `PYTHONPATH` + `PYTHON_GIL=0`。
```python
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TR.parent)
penv.setdefault('PYTHON_GIL', '0')
subprocess.run([pipeline_python, ...], env=penv)
```

## 28. DeepSeek API 服务端流中断 [持续发生]
`RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`，上游 `server=openresty`。DeepSeek 的 openresty 反向代理在 HTTP 200 响应中途断连。近期（5/24）一天出现 4 次。
**影响**：自动重试（3 次）兜住了大部分情况。但 12:02 那次 cron 日报因流中断只返回了 stub response，半篇丢失。
**信号**：`errors.log` 中 `Stream drop` + `RemoteProtocolError` + `upstream=[server=openresty]`。
**修复**：服务器端问题，本地无解。确认自动重试生效（3 次尝试），偶发的 stub response 需人工补推。
**检测**：健康检查已新增 `check_api()` 验证 DeepSeek 可达性。

## 29. WeCom WebSocket 频繁断连 [环境问题]
`[Wecom] WebSocket error: WeCom websocket closed` → 2s 后自动重连。今日已断开 10 次，间隔 12-20 分钟。
**影响**：自动重连始终成功（≤2.3s），推送丢失概率低。但 Gateway 崩溃信号（推送丢失）需要靠看门狗区分 WebSocket 断连和 Gateway 崩溃。
**信号**：`agent.log` 中 `WebSocket error` + 紧跟 `Reconnected` 即为正常 flapping。仅 `Reconnected` 缺失才考虑 Gateway 崩溃。
**修复**：环境正常现象。`delivery_watchdog.py` 已兼容此模式，不会因短暂断连误报。

## 30. 缓存文件过期未清理 [发现 2026-05-25]

## 31. 直连互联网中断 → Cron "Request timed out" [发现 2026-05-27]

**症状**：多台 LLM cron job 同时 `RuntimeError: Request timed out`。no_agent 脚本类 cron 正常（不依赖 web 工具）。WeCom 在线。

**根因**：WSL 环境下直连互联网不可用（`Network is unreachable`），但代理 `127.0.0.1:7890` 正常。Hermes web 工具（`web_search`/`web_extract`）无代理 env vars 时尝试直连 → 超时 → agent 超时 → cron 超时。TrendRadar pipeline 脚本内部已有 `PROXY_URL` 配置不受影响。

**诊断**：
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 https://www.google.com
# → 000 = 直连断
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 -x http://127.0.0.1:7890 https://www.google.com
# → 200 = 代理正常
```

**修复**：向 gateway systemd override.conf 注入 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`：
```ini
# ~/.config/systemd/user/hermes-gateway.service.d/override.conf
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,api.deepseek.com"
```
重载重启：`systemctl --user daemon-reload && systemctl --user restart hermes-gateway.service`

**注意**：如果直连恢复（Google 可达），代理 env vars 不会造成破坏——只是所有外网请求多走一个代理跳转，不影响功能。不要因为直连恢复就移除代理 env vars。
`remove_older_than()` 仅清理 data/ 目录的匹配文件。但 `cache/` 目录下的 RSS 原始缓存和 fetch 快照不受此管控，可能无限堆积。
**信号**：`cache/` 目录文件数持续增长，磁盘空间缓慢下降。
**修复**：维护脚本 `trendradar_maintenance.py` 应增加对 `cache/*.json` 的过期清理（保留 48h）。Storage.vacuum() 每周清理 DB 碎片。
