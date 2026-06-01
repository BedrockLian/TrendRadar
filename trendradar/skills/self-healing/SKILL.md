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

详见 `../../references/ARCHITECTURE.md`。

核心检查：DB (WAL + Storage 统一接入) → 脚本 (21个) → 配置 → Cron → Gateway → API → 数据时效 → 盲点审计 → 拦截器 → 全链路 → 记忆 → 进程。

## 6 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `90a2866775df` | 日报推送 | LLM |
| `cab79825520e` | 推送看门狗（含空投补发） | no_agent |
| `68db70cd8556` | 每日维护 | no_agent |
| `c987a2883174` | 自动体检 | no_agent |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 使用名称子串匹配（`CRON_JOB_NAMES`），不依赖硬编码 ID。

## 健康检查脚本陷阱

详见 `references/health-check-pitfalls.md`。

### health_check.py 中 PYTHON_GIL=0 注入陷阱

`trendradar_health_check.py` 在多个 `subprocess.run()` 前有 `env.setdefault('PYTHON_GIL', '0')`。Python 3.14t 不支持 GIL 禁用，该行会导致子进程 `config_read_gil: not supported by this build` 崩溃。

**修复**：删除所有 `env.setdefault('PYTHON_GIL', '0')` 行。若 cron 环境需要 PYTHON_GIL，它已通过 systemd override 注入——不需要脚本再设默认值。

**受影响子检查**：`check_sanity_interceptor()`、`check_pipeline()`（push_slot_detect + import check）、`check_blind_spot()`。

### push_slot_detect NO_SLOT 正常视为失败陷阱

`push_slot_detect.py` 在非推送时段输出 `NO_SLOT` 并 exit=1。health_check 的判断逻辑 `if r.returncode != 0` 会误报 `push_slot_detect 执行失败`。

**修复**：`if r.returncode != 0 and r.stdout.strip() != 'NO_SLOT'` — 仅在 stdout 不是 `NO_SLOT` 时才报失败。

## 投递失败自动补发

详见 `../../references/DELIVERY-WATERMARK.md`。

## 常见故障

详见 `../../references/TRAPS.md`。

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

**修复**：补充 `~/.config/systemd/user/hermes-gateway.service.d/override.conf` 中的代理 env vars，然后重启 gateway。详见 `../system-config/references/proxy-config.md` 的 **Gateway 级别代理** 章节。

**原理**：TrendRadar pipeline 脚本内部已有 `PROXY_URL` 配置（RSS 采集走代理），不受影响。但 Hermes web 工具（`web_search`/`web_extract`）由 cron job 的 LLM agent 调用，需要系统级 `HTTP_PROXY` 环境变量才能走代理。直连断时，web 工具超时 → agent 超时 → cron 报 "Request timed out"。

## 烟雾测试

每日维护 (`68db70cd8556`) 内含 `pytest tests/` 运行。测试失败会推送到 WeCom。

手动运行:
```bash
cd ~/TrendRadar/trendradar && python -m pytest tests/ -v --tb=short
```

测试维护 + 失败模式速查：`../../references/MAINTENANCE.md`（含 **9 种** 常见失败模式及修复方法，包括 import 死锁零输出超时 #8）。

## 翻译管线专项诊断

详见 `../news-secretary/SKILL.md` 翻译管线章节及 `../../references/TRAPS.md`。

## 参考文档

| 文件 | 内容 |
|------|------|
| `../../references/TRAPS.md` | 陷阱全集 + 维护陷阱 |
| `../../references/ARCHITECTURE.md` | 体检设计：检查项表 + cron ID 表 |
| `../../references/PIPELINE.md` | DeepSeek 断流 & WeCom WS 抖动 |
| `../../references/MAINTENANCE.md` | 烟雾测试维护：常见失败模式 + 修复方法 + Skill 审计 |
| `../../references/SETUP.md` | 缓存清理规程 |
| `references/foreign-china-expansion.md` | foreign_china 域扩展：新增源/关键词/验证方法 |
