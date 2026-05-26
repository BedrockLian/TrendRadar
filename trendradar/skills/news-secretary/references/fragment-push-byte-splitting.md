# 字节级分片技术

`fragment_push.py` v2.0 — UTF-8 字节计数 + 三级递降拆分。

## 限制

- WeCom 硬限制：4096 字节/条消息
- 安全边界：3800 字节（留 296B 给 JSON wrapper + 元数据）
- 超过 3800B 的 fragment 自动触发子分片

## 拆分策略（三级递降）

1. **段落边界** `\n\n` — 在 3800B 内找最后一个段落分隔
2. **句子边界** `。\n` / `。` — 在 3800B 内找最后一个句号
3. **硬切** — 在 3800B 处截断 + `...(续)` 标记，循环至全部 ≤3800B

## 关键陷阱：`_find_last` 的 `len()` vs `bytes`

详见 `system-config` skill 的 `references/pitfalls-utf8-bytes.md`。

核心问题：`len(text)` 返回字符数，中文 1 字符 = 3 字节。用字符数做字节限制的搜索窗口会严重超出。
