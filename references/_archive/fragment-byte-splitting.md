# UTF-8 字节精确分片 — pitfall 与三级递降策略

`fragment_push.py` 必须确保每片 ≤ 3800 UTF-8 bytes（WeCom 硬限 4096）。

## 致命 Pitfall: `len()` vs `bytes`

**问题**: `len(text)` 返回字符数，不反映 UTF-8 字节数。中文 1 字符 = 3 bytes。

```python
# ❌ 错误 — 搜索窗口是字符数，导致 CJK 文本窗口 3x 过大
search_end = min(len(text), max_bytes)
idx = text.rfind(delimiter, 0, search_end)

# ✅ 正确 — 从字节截断反推字符位置
encoded = text.encode('utf-8')
truncated = encoded[:max_bytes]
# 处理被截断的多字节字符
for trim in range(4):
    try:
        char_limit = len(truncated.decode('utf-8'))
        break
    except UnicodeDecodeError:
        truncated = truncated[:-1]
idx = text.rfind(delimiter, 0, char_limit)
```

**调试线索**: 单片仍然超过 MAX_BYTES → 检查搜索函数是否用了 `len()` 而非字节精确的 `char_limit`。

## 三级递降拆分策略

按优先级尝试，前一策略失败才降级：

| 优先级 | 分隔符 | 适用场景 |
|--------|--------|---------|
| 1 | `\n\n`（段落边界） | 正常的 Markdown 分段 |
| 2 | `。\n` 或 `。`（句子边界） | 长段落无自然分段 |
| 3 | 硬切 + 迭代循环 | 纯文本无任何分隔符（如超长日文标题串） |

硬切时保留 CONT_MARKER（`...(续)`），并在 while 循环中继续切分剩余部分，
直到所有片段 ≤ MAX_BYTES。

## 熔断保护

`_find_safe_cut()` 对硬切的 byte offset 做 UTF-8 安全解码，逐字节回退（最多 4 字节）
确保不在多字节字符中间截断。若仍失败则 `_split_overlong` 返回原文本以防死循环。
