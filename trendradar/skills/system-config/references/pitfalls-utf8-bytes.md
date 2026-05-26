# UTF-8 字节计数陷阱

## `_find_last` 的 `len()` vs `bytes` 混用

**现象**：超大中文段落（"长文本"×2000）的硬切只执行 2 次就停了，残留 10459B 的 fragment 远超 3800B 限制。

**根因**：

```python
# ❌ 错误 — len() 是字符数，中文 3 bytes/char
def _find_last(text, delimiter, max_bytes):
    search_end = min(len(text), max_bytes)  # 2000 chars vs 3800 bytes → 取 2000
    idx = text.rfind(delimiter, 0, search_end)  # 搜索了全部 2000 字符 = 6000 bytes！
```

`len("长文本"*2000)` = 2000 个字符。`max_bytes` = 3800 字节。`min(2000, 3800) = 2000`。但 2000 个中文字符 = 6000 字节，远超 3800B 限制。搜索窗口错误，导致超大段落未被切割。

**修复**：

```python
# ✅ 正确 — 按字节截断再解码回字符边界
def _find_last(text, delimiter, max_bytes):
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text.rfind(delimiter) + len(delimiter)
    truncated = encoded[:max_bytes]
    for trim in range(4):  # max 4 bytes for a single UTF-8 char
        try:
            char_limit = len(truncated.decode('utf-8'))
            break
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    idx = text.rfind(delimiter, 0, char_limit)
    return idx + len(delimiter) if idx != -1 else None
```

**教训**：涉及 UTF-8 字节限制时，所有长度计算必须走 `len(text.encode('utf-8'))`，不能依赖 `len(text)`。

## `_split_overlong` 的迭代硬切

原始实现在 `else` 分支只有一次硬切就 `break`，导致巨型纯文本段落只切一次后残留仍超标。修复为 `while` 循环持续硬切直到每个 piece ≤ MAX_BYTES。
