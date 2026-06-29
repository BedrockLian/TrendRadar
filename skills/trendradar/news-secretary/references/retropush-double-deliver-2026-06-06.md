# 2026-06-06 早报补推翻车完整复盘

> 核心教训：**agent 在手动补推时会重复投递到 wecom，导致用户收到 2-3 份相同早报**。
> 触发场景：WSL 启动晚 → cron 跳点 → 用户说"补推"。

## 时间线

| 时刻 | 事件 | wecom 投递 | marker 状态 |
|---|---|---|---|
| 9:46 | WSL 启动，gateway 启动补跑 9:00 早报 cron（90a2866775df） | 0 片 | error（archive 未生成） |
| 9:46+ε | slot_direct_push 跑，发现 archive 不存在 → exit 2 | 0 片 | error marker 写入 |
| 9:55 | 用户说"补推早报"，**Agent 误判**：`crontab -l` 看到空 → 认为 cron 漏了 | — | — |
| 9:55 | Agent 跑 `pipeline_orchestrator --push-id morning` → archive 写入 + 直接裸调 `hermes send` 6 片 | **6 片** | 没写 marker（裸 hermes send 不写 marker） |
| 10:00 | delivery_watchdog 巡检：早报 marker 是 error 不是 ok → 触发补发 | **0 片**（watchdog 自己 `No module named 'trendradar'`，sys.path 没设） | — |
| 10:00 | watchdog 顺手把 5/5 午间 + 5/5 晚间 补发成功 | 6+6 片 | — |
| 10:23 | Agent 手测 `slot_direct_push.py --slot morning --date 2026-06-06` | **6 片** | ok 6/6 marker 覆盖 error |
| 10:23 | 第二次手测（同条命令） | **6 片** | （在写入 marker 前的快照中读 marker 误以为失败） |

**用户实际收到**：今早 9:00 早报 0 份正常版 + 9:55 的 6 片 + 10:23 的 6 片 + 10:23 第二次的 6 片 = **18 片重复早报**（按 6 片为一期 = 3 期重复）。

## 错在哪

### 错误 1：`crontab -l` 当成真相来源

```bash
$ crontab -l
no crontab for asus
```

Agent 看到这行就判断"cron 没装"。**错的**。Hermes cron 走的是**内置 gateway 调度器**（`hermes cron list` / `hermes cron status` 查看），不是系统 cron。系统 `crontab -l` 经常为空是**正常状态**。

正确诊断第一步：
```bash
hermes cron list          # 7 个 job 全列出
hermes cron status        # gateway 状态
```

### 错误 2：Agent 裸调 `hermes send` 投递，没用 `slot_direct_push.py`

`hermes send --to wecom:bl --file <frag>` 是**原子投递**——成功就发出去，但**不写 `delivery_markers/delivered_{date}_{slot}.marker`**。

后果：
- 下次 cron 跑时 `slot_direct_push` 看到 marker 不存在 → 重新投递
- 任何 watchdog 巡检看到 marker 不存在 → 触发补发
- 用户**永远**会收到多份

正确做法：
```bash
# 跑专用脚本，自动 split + 写 marker
python3 ~/.hermes/scripts/slot_direct_push.py --slot morning --date 2026-06-06
# 或 走 archive_resend（preview + 确认）
python3 -m trendradar.scripts.archive_resend --date 2026-06-06 --slot morning --yes
```

### 错误 3：手测时没确认上次 marker 状态，导致重复执行

10:23 第一次手测成功（6/6 + ok marker），**没有**通过 `cat marker` 确认就跑了第二次（10:23 第二次跑看到 6/6 是因为 marker 写入有 race，但 6/6 这次投递在 wecom 上还是发了）。

教训：**手测前先看 marker**：
```bash
cat ~/.hermes/trendradar/data/delivery_markers/delivered_{date}_{slot}.marker
# status=ok          → 别再投
# status=error       → 修原因后再投
# 文件不存在         → 可以投
```

## 实战修正清单

**已修**（本次）：
- `slot_direct_push.py` 加 retry：`archive not found` 时 sleep 5s × 3 = 15s 容忍窗口
- `delivery_watchdog.py` 加 `sys.path.insert(0, str(TRENDRADAR_HOME))`（line 232 前）——修 10:00 的 `No module named 'trendradar'`
- `tri_sync_verify.py` 重写 WORKTREE_SCRIPTS 解析（v2.1）：用 `_detect_worktree_scripts()` 探测式（git worktree list + 常见位置）代替硬编码 `Path(.../"scripts")` 拼接。原代码是 str/str 除法启动就 crash，修后实测 `python3 tri_sync_verify.py ai_translate.py` ✅；并发现 `pipeline_orchestrator.py` legacy 副本有 4 行 stale `[TRACE-ORCH]` debug（nested 无），已删，3 副本 md5 一致
- SKILL.md changelog v2.1 描述从"L31 修复"改为正确的探测式描述

**未修**（保留作历史记录）：
- 重复投递的 18 片无法撤回（wecom API 无便捷批量删除）

## 给未来 agent 的硬规则

1. **`hermes cron list` 是真相**，`crontab -l` 是噪音
2. **补推永远走 `slot_direct_push.py` 或 `archive_resend.py`**，**绝不**裸调 `hermes send`
3. **手测前 `cat marker`**，status=ok 就停
4. **`pipeline_orchestrator` 跑完** → 先 `ls archive/YYYY-MM-DD/{slot}.md` 确认文件 → 再 `slot_direct_push.py --slot <slot>`
5. **遇到"补推 X"请求时**先说"先看 cron 状态再决定怎么补"——不要直接开跑
6. **修 `tri_sync_verify.py` 这类 verifier 之后必跑**所有生产 .py 一次（`for f in scripts/*.py; do python3 tri_sync_verify.py $f; done`），因为 verifier 一旦能跑，会立即发现历史遗留的 silent mismatch（2026-06-06 实测：verifier 跑通后立即发现 `pipeline_orchestrator.py` legacy 副本有 4 行 stale `[TRACE-ORCH]` debug，nested 副本早已删，runtime 永远命中 nested 没暴露）。**verifier 修好不跑 = 失去"系统性盘点"的机会**

## 关联 references

- `references/slot-direct-push-protocol.md`：v6.6 投递架构
- `references/cron-failure-case-2026-06-02.md`：上一次晚间 cron 失败的 4 层根因
- `references/fix-recipes.md`：第 8 节新加"补推不重复投递"
