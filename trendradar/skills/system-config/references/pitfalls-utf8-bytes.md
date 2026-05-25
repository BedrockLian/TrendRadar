# UTF-8 字节计数陷阱：`_find_last` 修复记录

## 问题

`fragment_push.py` 的 `_find_last()` 函数需要在一个文本中搜索分隔符（`\n\n`、`。`），
但限制搜索范围不能超过 `MAX_BYTES`（3800 bytes）。

### 错误实现（v1）

```python
def _find_last(text: str, delimiter: str, max_bytes: int) -> int | None:
    search_end = min(len(text), max_bytes)      # ❌ 比较 char 和 bytes
    idx = text.rfind(delimiter, 0, search_end)
    ...
```

**Bug**: `len(text)` 返回字符数，`max_bytes` 是字节数。中文每个字符 3 bytes。
对于 2000 个中文字符：`len(text)=2000`, `max_bytes=3800` → `search_end=2000`。
但 2000 个中文字符 = 6000 bytes，远超 MAX_BYTES。

结果：`_split_overlong` 产生 >10000 bytes 的 fragment，被 WeCom 静默截断。

### 修复后（v2）

```python
def _find_last(text: str, delimiter: str, max_bytes: int) -> int | None:
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        idx = text.rfind(delimiter)
        return idx + len(delimiter) if idx != -1 else None

    # 截断到 max_bytes，找到安全的字符边界
    truncated = encoded[:max_bytes]
    for trim in range(4):
        try:
            char_limit = len(truncated.decode('utf-8'))
            break
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    else:
        return None

    idx = text.rfind(delimiter, 0, char_limit)
    ...
```

**关键**：先用 `encode('utf-8')` 截取字节，再 `decode('utf-8')` 找到安全字符边界，
避免截断多字节 UTF-8 序列。

## 通用原则

任何时候比较 `len(text)` 和 `byte_count` 时都需要注意：
- 英文/ASCII: `len(text) == byte_count`（1 char = 1 byte）
- 中文: `len(text) * 3 ≈ byte_count`（1 char = 3 bytes）
- Emoji: `len(text) * 4 ≈ byte_count`（1 char = 4 bytes）

**规则**：涉及字节限制时，始终用 `len(text.encode('utf-8'))` 而非 `len(text)`。
