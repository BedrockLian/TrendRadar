# 深度分析子 Agent 沙箱陷阱

> 发现于 2026-05-26 晚间 cron

## 现象

晚间 cron 执行 3×Pro `delegate_task` 深度分析子 Agent。子 Agent 生成报告文件（如 `reports/risk_analysis_20260526_evening.md`），但格式化投递子 Agent 的 `terminal` 命令全部返回空——包括 `cat`, `ls -la`, `find`。

## 根因

`delegate_task` 子 Agent 运行在**独立的进程上下文**中，其文件系统工具（`terminal`, `read_file`）**无法访问父 session 的磁盘路径**。这不是路径不对的问题——即使是 `find /` 或 `pwd` 也会返回空。

## 修复

**永远不要通过文件路径让子 Agent 读取内容。** 必须通过 inline 传递：

```python
# 错误 ❌ — 子 Agent 读不到
delegate_task(goal="Read /path/to/report.md and format it")

# 正确 ✅ — 内容内联传递
report = open("/path/to/report.md").read()
delegate_task(
    goal="Format the following analysis report and return it",
    context=report  # 内容直接在 context 中
)
```

## 影响

- 晚间深度分析报告生成后无法自动格式化投递
- 子 Agent 静默失败（工具返回空但不报错），父 Agent 以为成功

## 检测

子 Agent 日志中连续出现空输出的 `terminal` 调用链 → `cat` 空 → `ls` 空 → `find` 空 → 子 Agent 困惑地尝试其他路径。此时应立即中止文件路径尝试，改用 inline 传参。
