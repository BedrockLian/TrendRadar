---
name: self-healing
slug: self-healing
version: 3.6.0
description: 自动体检 TrendRadar 各组件：DB/配置/API/Gateway/记忆。修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)。有异常推送 WeCom，健康静默。

## 检查项（14项 + 4 个子检查）

详见 `references/ARCHITECTURE.md`。

核心检查：DB (WAL + Storage 统一接入) → 脚本 (21个) → 配置 → Cron → Gateway → API → 数据时效 → 盲点审计 → 拦截器 → 全链路 → 记忆 → 进程。

## 7 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `90a2866775df` | 日报推送 | LLM |
| `718b663e8c04` | 性能优化器 | LLM |
| `cab79825520e` | 推送看门狗（含空投补发） | no_agent |
| `68db70cd8556` | 每日维护 | no_agent |
| `c987a2883174` | 自动体检 | no_agent |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 使用名称子串匹配（`CRON_JOB_NAMES`），不依赖硬编码 ID。

## 健康检查脚本陷阱

### 1. `check_cron()` 不支持 `--json` 参数
**现象**：`hermes cron list --json` 返回 `unrecognized arguments: --json`（Hermes CLI 无 JSON 输出模式），所有 job 报"未在输出中找到"的假阳性。

**修复**（2026-05-28）：去掉 `--json`，改解析 CLI 表格输出中的 `Name: xxx` 行（正则 `\s+Name:\s+(.+)` → job_names 集合）。按 `CRON_JOB_NAMES` 做子串匹配（"日报推送"匹配"TrendRadar 日报推送（早/午/晚）"）。

**CRON_JOB_NAMES 必须与实际 job 名称匹配**：`hermes cron list` 的实际名称含前缀（"TrendRadar 日报推送"等），缩写名（"推送看门狗"→"推送降级看门狗", "月度报告"→"月度趋势报告"）会漏检。2026-05-28 修正后的实际名称：`日报推送`, `性能优化器`, `推送降级看门狗`, `每日维护`, `自动体检`, `周报推送`, `月度趋势报告`。

### 2. `check_gateway()` 通过 `ps aux | grep 'hermes gateway'` 找不到 systemd 服务
**现象**：Gateway 作为 systemd user service 运行，`ps aux` 中进程名是 `python -m hermes_cli.main gateway run`，不包含 "hermes gateway" 字符串 → 假阳性。

**修复**（2026-05-28）：改用 `systemctl --user is-active hermes-gateway.service` 直接查询 systemd 状态。兜底：`hermes gateway status`。无 systemd 环境（Docker 等）回落 socket 文件检查。

### 3. `check_stale_processes()` 引用了未定义的 `CRON_JOBS`
**现象**：`NameError: name 'CRON_JOBS' is not defined` → 健康检查崩溃，exit code 1。

**修复**（2026-05-28）：改为 `CRON_JOB_NAMES`（模块级已定义变量）。

### 4. `check_pipeline()` RSS 连通性：随机采样 + localhost 源假阳性
**现象**：健康检查随机抽 3 个 RSS 源做 socket 连通性测试，抽到 `localhost:1200`（本地 RSSHub 通常未运行）的源时报 `RSS 源不可达`，导致每次运行结果不一致（有时通过有时报错）。

**修复**（2026-05-28）：
- 采样前过滤掉 `feed_url` 含 `localhost` 的源（RSSHub 非必需）
- 改为确定性取前 3 个源而非 `random.sample`（同一机器每次结果一致）
- 同时过滤 `enabled=False` 的源（之前未过滤）
- 不再遇到第一个失败就 `break` 退出——改为检查全部 3 个源，统计失败数：
  - **全部 3 个失败** → 报 WARN（全链路问题）
  - **部分失败** → 仅 debug 日志 + stderr 提示（单个源临时不可达是常态，不报健康检查警告）

### 5. `check_api()` httpbin.org 检测假阳性
**现象**：`check_api()` 检查 `httpbin.org` 和 `api.deepseek.com/v1/models`。由于 `HTTP_PROXY` 环境变量的存在，httpbin.org 走代理（代理节点全部 i/o timeout → 000），而 DeepSeek 在 NO_PROXY 中直连可达（401）。导致"外网出口 不可达"的假阳性。

**根因**：WSL 无直连互联网，所有外网流量必须走 `http://127.0.0.1:7890` 代理。健康检查在 cron 环境运行时，`HTTP_PROXY`/`NO_PROXY` 环境变量可能被继承也可能没有，行为不一致。

**修复**（2026-05-28）：
- 删除 httpbin.org 检测（走代理必超时，无信息量）
- DeepSeek 检测时清除所有 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量后直连，确保 cron 环境也可靠

## 投递失败自动补发

`delivery_watchdog.py` 额外承担 auto-delivery 空投检测（2026-05-26 新增）：

1. **调度**：每日 10:00 / 14:00 / 22:00（cron `cab79825520e`），22:00 距晚间推送仅 1h
2. **检测**：对比 `push_log.json` 最新 evening 条目与 `data/delivery_markers/` 目录
3. **补发**：未标记即自动重新渲染 → sanity_check → `hermes send --to wecom:bl` 补投
4. **循环防护**：补发后写 `delivered_{run_id}.marker`，同一 run_id 只补一次
5. **时效**：仅补发 6 小时内的推送

诊断详见 `../../news-secretary/references/DELIVERY-WATERMARK.md  # was delivery-failure-debug → delivery`。

## 常见故障

详见 `references/TRAPS.md` 和 `references/TRAPS.md`。

### Cron 任务 "Request timed out" — 直连互联网中断

**症状**：多台 LLM cron job 同时报 `RuntimeError: Request timed out`，但 no_agent 脚本类 cron 正常。WeCom 在线。

**诊断**：
```bash
# 1. 验证直连是否正常
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 https://www.google.com
# → 000 / exit 28 / "Network is unreachable" = 直连断

# 2. 验证代理是否正常
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 -x http://127.0.0.1:7890 https://www.google.com
# → 200 = 代理正常

# 3. 检查 DeepSeek API 可达性（直连路由可能例外）
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 https://api.deepseek.com/v1/models
# → 401 = 正常（无 token 的预期响应）
```

**修复**：补充 `~/.config/systemd/user/hermes-gateway.service.d/override.conf` 中的代理 env vars，然后重启 gateway。详见 `../../system-config/references/proxy-config.md` 的 **Gateway 级别代理** 章节。

**原理**：TrendRadar pipeline 脚本内部已有 `PROXY_URL` 配置（RSS 采集走代理），不受影响。但 Hermes web 工具（`web_search`/`web_extract`）由 cron job 的 LLM agent 调用，需要系统级 `HTTP_PROXY` 环境变量才能走代理。直连断时，web 工具超时 → agent 超时 → cron 报 "Request timed out"。

## 烟雾测试

每日维护 (`68db70cd8556`) 内含 `pytest tests/` 运行。测试失败会推送到 WeCom。

手动运行:
```bash
cd ~/TrendRadar/trendradar && python -m pytest tests/ -v --tb=short
```

测试维护 + 失败模式速查：`references/SKILL-AUDIT.md  # was smoke-test-maintenance → skill audit`（含 **9 种** 常见失败模式及修复方法，包括 import 死锁零输出超时 #8）。

## 翻译管线专项诊断

翻译大面积缺失时的排查顺序：
1. `_load_source_languages()` 是否返回空 → 检查 `_SOURCES_PATH` 是否用 `get_data_dir()`
2. `get_source_lang()` 对已知外媒平台是否返回 None → 检查 `sources.json` 中对应源的 `language` 字段
3. **`data/sources.json` 是否存在？** — git clean/reset 会删除它 → `_load_source_languages()` 静默返回空 frozensets → `get_source_lang()` 全部 None → 0 条翻译。从备份恢复：`cp backups/trendradar/$(date +%Y%m%d)/sources.json data/`
3. `_load_and_scan` 文件选择是否正确 → 检查是否读到正确日期版文件（三层回退）
4. `ai_translate.py` 是否实际运行 → 手动跑一次验证:
```bash
cd ~/TrendRadar/trendradar && PYTHONPATH=/home/asus/TrendRadar /usr/local/bin/python3.14t scripts/ai_translate.py --push-id {slot}
```
5. **BATCH_SIZE 导致的假翻译** — 摘要正确但标题保持原文不变 (`title_cn == title`)。DeepSeek batch >5 时只翻摘要不翻标题。`BATCH_SIZE = 5`。先清理假 `title_cn` 再重跑。
7. **源被预分类错域** — 特定源的文章一直在 `fetch_all` 中被抓取（检查 raw cache）但从未出现在简报中，可能在 `_preclassify` 阶段被关键词误匹配到 tech/gaming 域 → LLM 精选时被其他专业源挤掉。检查 `_likely_domain` 是否正确，在 `_preclassify()` 的 `SOURCE_DOMAIN_OVERRIDE` 字典中加条目强制分配正确域。
8. **预分类 category fallback 缺失** — `foreign_china` 类别源（BBC 世界/中国、NPR 国际、路透社·国际）掉到 `other`。检查 `_preclassify` 的 fallback 是否覆盖了所有 sources.json 中的 category 值。
9. **短关键词子串误触** — `config/keywords.py` 中 2 字符关键词（FF/AI/AR）通过子串匹配误触任何英文单词中的字母组合。`_likely_domain` 大面积为 tech/gaming 而非预期域时检查此问题。
7. **源 RSS 源可用性** — 直接 `curl localhost:1200/{route}` 测试 RSSHub 响应。若 HTTP 200 有内容但 fetch_feeds 抓不到，可能是代理池耗尽或 aiohttp session 配置问题。单独测试 `_fetch_one()` 可确认。

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/TRAPS.md` | 陷阱全集 |
| `references/ARCHITECTURE.md` | 体检设计：检查项表 + cron ID 表 |
| `references/TRAPS.md` | 维护陷阱（含 git clean 恢复 #9、嵌套包路径 #10、PYTHONPATH import 死锁 #11） |
| `references/PIPELINE.md  # was api-diagnosis → pipeline troubleshooting` | DeepSeek 断流 & WeCom WS 抖动 |
| `references/ARCHITECTURE.md  # was import-architecture → architecture` | 导入架构修复 |
| `references/ARCHITECTURE.md  # was migration-mechanism → architecture` | 迁移引擎架构 |
| `references/ARCHITECTURE.md  # was migration-rollback → architecture` | 迁移回滚约定 |
| `references/TRAPS.md  # was migration-idempotency-bug → traps` | 迁移幂等性 Bug |

| `references/SKILL-AUDIT.md  # was smoke-test-maintenance → skill audit` | 烟雾测试维护：常见失败模式 + 修复方法 |
| `references/SETUP.md  # was cache-cleanup → setup` | 缓存清理规程 |
| `references/foreign-china-expansion.md` | foreign_china 域扩展：新增源/关键词/验证方法 |
