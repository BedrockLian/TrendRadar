<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 编排器可靠性注意事项

## fragment_push 输出解析
`fragment_push.py` 将 JSON 数组写入 stdout，日志写入 stderr。但某些环境下日志可能泄漏到 stdout。
编排器解析时找到第一个以 `[` 开头、`]` 结尾的行为 JSON，其余忽略。
故障时回退为单片段（整篇简报作为一条消息）。

## 并行阶段的 ThreadPoolExecutor
`ai_translate` 和 `batch_fetch` 通过 `concurrent.futures.ThreadPoolExecutor(max_workers=2)` 并行。
这是进程内并行（非 subprocess），所以两者共享同一进程的 GIL 状态。
使用 `PYTHON_GIL=0`（python3.14t）时无 GIL 竞争。

## NEW_COUNT 检测
`push_prepare.py --dedup` 在 JSON 后输出 `NEW_COUNT=N`。编排器从 stdout 行解析。
如果 0，pipeline 不渲染——直接返回 `[SILENT]`。

## 时段检测回退
编排器优先 `push_slot_detect.py`（±10 分钟宽容窗口）。
`--push-id` 手动指定时跳过检测，直接使用指定 slot。

## 错误处理
每阶段独立 try/subprocess。一个阶段失败不会中断后续（仅记录 error）。
渲染失败时整个 pipeline 标记为 error 并返回错误 JSON。
