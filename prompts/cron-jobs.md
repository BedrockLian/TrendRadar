# TrendRadar Cron Jobs

共 7 个 job，其中 3 个 LLM 驱动（agent），4 个纯脚本（no_agent）。

---

## LLM 驱动（3）

### 1. 日报推送（早/午/晚）
- **job_id:** 90a2866775df
- **schedule:** `0 9,12,21 * * *`（每天 09:00 / 12:00 / 21:00）
- **model:** deepseek-v4-flash / deepseek
- **deliver:** wecom
- **skills:** news-secretary, multi-search-engine
- **workdir:** ~/.hermes/trendradar
- **tools:** terminal, web, delegation
- **上次状态:** ok（2026-05-29 21:30）

### 2. 周报推送（深度研究员）
- **job_id:** c20e2c82deda
- **schedule:** `30 9 * * 1`（每周一 09:30）
- **model:** deepseek-v4-pro / deepseek
- **deliver:** wecom
- **skills:** multi-search-engine, deep-research-cli, weekly-report
- **workdir:** ~/.hermes/trendradar
- **tools:** terminal, web
- **上次状态:** ok（2026-05-25 09:42）

### 3. 月度趋势报告
- **job_id:** 0b14c67429ba
- **schedule:** `0 9 1 * *`（每月 1 日 09:00）
- **model:** deepseek-v4-pro / deepseek
- **deliver:** wecom
- **skills:** multi-search-engine, deep-research-cli, monthly-report
- **workdir:** ~/.hermes/trendradar
- **tools:** terminal, web
- **上次状态:** 从未运行

---

## 性能优化器（LLM 驱动）
- **job_id:** 718b663e8c04
- **schedule:** `15 21 * * *`（每天 21:15，日报晚间推送后）
- **model:** 无（跟随主配置）
- **deliver:** wecom
- **skills:** performance-optimizer, multi-search-engine, news-secretary
- **workdir:** ~/.hermes/trendradar
- **tools:** terminal, file, web
- **上次状态:** ok（2026-05-29 21:18）

---

## 纯脚本（no_agent, 4 个）

### 5. 每日维护（备份+清理）
- **job_id:** 68db70cd8556
- **schedule:** `0 3 * * *`（每天 03:00）
- **script:** trendradar_maintenance.py
- **deliver:** wecom
- **上次状态:** ❌ error（2026-05-29 03:00）— 烟雾测试失败

### 6. 推送降级看门狗
- **job_id:** cab79825520e
- **schedule:** `0,30 10,14,21,22 * * *`（每天 10:00/10:30/14:00/14:30/21:00/21:30/22:00/22:30）
- **script:** delivery_watchdog.py
- **deliver:** local（不推 WeCom，静默巡检）
- **上次状态:** ok（2026-05-29 22:30）

### 7. 自动体检
- **job_id:** c987a2883174
- **schedule:** `0 15 * * *`（每天 15:00）
- **script:** trendradar_health_check.py
- **deliver:** wecom
- **上次状态:** ok（2026-05-29 15:00）
