<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 性能瓶颈模式

> 性能维度已移除常规调优，保留已知瓶颈供排查。

## TCP 连接池耗尽

**症状**：RSS源 aiohttp 超时但 curl 正常。
**案例**(2026-05-21): `RSSHUB=12 + EXTERNAL=20 = 32 > TCPConnector(30)` → 6/38超时。修复: 0超时，29.9s→5.0s。
**修复**: `TCPConnector(limit) >= sum(所有Semaphore)`，留20%余量。

## Script 并行

互不依赖脚本用 `& wait`:
```bash
python3 scripts/ai_translate.py & T1=$!
python3 scripts/batch_fetch.py & T2=$!
wait $T1 $T2
```
收益 = max(T1,T2) 替代 T1+T2。

## 三步审计

1. 脚本 — 死代码/重复（grep import + grep调用点）
2. cron — job重叠/静默运行
3. 配置 — 零引用文件/零值字段

用 delegate_task 3路并行，读文件 + search_files 交叉验证。
