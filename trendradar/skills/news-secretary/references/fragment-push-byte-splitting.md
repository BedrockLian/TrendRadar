# fragment_push.py 字节级分片技术

## 问题

企业微信单条消息硬限制 4096 字节（UTF-8）。超长消息被静默截断，无报错。
旧实现按 `### ` 标题分割，不检查字节数 → 中文密集板块单片可达 10KB+。

## 解决方案

三级递降解构，每级严格检查 `len(text.encode('utf-8'))`：

### 1. 段落边界 (`\n\n`)
优先在自然段落处分片，保持可读性。

### 2. 句子边界 (`。\n` / `。`)
段落不存在时退到句号切分。

### 3. 硬切 + 迭代 (`_find_safe_cut`)
纯长文本（无段落无句号）时在 3800 字节处硬切，附 `...(续)` 标记。
关键：`while remaining` 循环迭代直到所有片段 ≤ 3800 字节。

## 核心陷阱：`_find_last` 的字节-vs-字符混淆

### Bug 表现
`_find_last(text, '\n\n', 3800)` 对 `"长文本" * 2000`（6000 字符 = 18000 字节）返回的切割点远超 3800 字节。

### 根因
```python
# ❌ 错误 — len() 是字符数，max_bytes 是字节数
search_end = min(len(text), max_bytes)  # 中文: len=6000 > max_bytes=3800
idx = text.rfind(delimiter, 0, search_end)  # 实际搜索了 3800 字符 = 11400 字节！
```

中文 1 字符 = 3 字节（UTF-8），`len()` 返回的是字符数。`rfind` 的第三个参数是字符位置。直接用 `max_bytes` 作为字符搜索上限，对 ASCII 安全（1:1），但中文下窗口放大了 3 倍。

### 修复
```python
# ✅ 正确 — 先编码为字节，截断，再解码回字符边界
encoded = text.encode('utf-8')
truncated = encoded[:max_bytes]
for trim in range(4):  # 最多 4 字节回退（UTF-8 单字符最大 4 字节）
    try:
        char_limit = len(truncated.decode('utf-8'))
        break
    except UnicodeDecodeError:
        truncated = truncated[:-1]

idx = text.rfind(delimiter, 0, char_limit)
```

### 教训
**任何涉及 `len(text)` 和字节计数的混合运算必须转换为同一种度量。**
先 `encode('utf-8')` → 用字节度量做所有判断 → 最后 `decode` 回字符位置。
绝不要假设 1 char = 1 byte，尤其在 CJK 文本处理中。

## 安全边界

- `MAX_BYTES = 3800`（4096 硬限制留 296 字节给 JSON wrapper + 元数据）
- `_find_safe_cut` 用 4 字节回退裕度（UTF-8 单码点最大 4 字节）
- `CONT_MARKER = "\n...(续)"`（~10 字节，计入切割预留）

## 相关测试

`tests/test_pipeline_e2e.py::TestFragmentsByteCounting` — 6 项测试覆盖：
- 短简报不触发分片
- 超大单体段落迭代切割
- 标题仅在第 1 片
- 尾注仅在最后 1 片
- 空输入
- UTF-8 安全硬切（不切断多字节字符）
