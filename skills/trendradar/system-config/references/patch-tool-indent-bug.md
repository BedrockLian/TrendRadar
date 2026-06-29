# patch 工具 new_string 缩进 bug 复现手册（2026-06-02 反复踩坑）

`patch` 工具（`mode='replace'`）的 diff 引擎对 **`new_string` 中带前导空格的行**会无脑 dedent。在 SKILL.md 已写
明根因和修复（见 `../SKILL.md` "patch 工具陷阱" 章节第 2 节），本文件是**完整复现案例**——遇到同样症状
时可以快速对照定位。

## 症状指纹

1. `patch` 工具返回 success（无错误）
2. 改完后 `python3.14t -m py_compile <file>` 报 `SyntaxError` 或 `IndentationError`
3. `od -c` 看到 raw bytes 里**一整段**（不只一行）前导空格被剥
4. `git diff` 显示新文件内容**与 new_string 不一致**（缩进被吃掉的部分）

## 复现 1：.py 字符串里嵌入多行 markdown

**触发场景**：在 `.py` 文件里给 `lines.append("...")` 字符串新增多行内容。

**示例**（真实踩坑，`gen_cron_prompt.py` 加降级路径时）：

```python
# 调用
patch(
    path='gen_cron_prompt.py',
    old_string='    lines.append("## Deep Analysis (evening only)")',
    new_string='''    lines.append("## Deep Analysis (evening only)")

Only when `push_id=evening` and `needs_deep_analysis=true`:

1. Launch 3 flash sub-agents
   - Model: deepseek-v4-flash
   - 降级路径: 60s timeout → 主 agent 自己用 flash 生成'''
)
```

**问题**：上面 `new_string` 里第 3 行起全是 0 缩进，patch 视为"diff 上下文"没影响。但
**如果你每行都写 4 空格缩进**（如嵌入到 Python list / dict），patch 视为"diff 增量"——前导
空格被剥掉。

**修复**：每行**前导空格数 = 0**（不缩进），改完用 `python3.14t -m py_compile` 验证。

## 复现 2：try/except 块大改

**触发场景**：重写整个 try/except 块的 4 行代码。

**示例**：
```python
patch(
    path='storage.py',
    old_string='''    try:
        conn.close()
    except Exception:
        pass''',
    new_string='''    try:
        with self._lock:
            conn.close()
    except Exception as e:
        log.error(f"close failed: {e}")
        self._cleanup_on_error()'''
)
```

**问题**：new_string 的 6 行全部带 4 空格缩进——patch 视为 diff 缩进"上下文"——剥掉。

**修复**：用 `sed -i` 代替 patch（`sed -i '/try:/,/except/s/^/    /' storage.py`），
或全文件 `write_file` 重写。

## 复现 3：函数体大改

**触发场景**：重写整个函数体。

**示例**：
```python
patch(
    path='processor.py',
    old_string='''def process(items):
    result = []
    for item in items:
        result.append(transform(item))
    return result''',
    new_string='''def process(items, batch_size=10):
    result = []
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        result.extend([transform(x) for x in batch])
    return result'''
)
```

**问题**：new_string 整段都 4 空格缩进，patch 剥掉。

**修复**：`write_file` 全文件重写，或 `sed -i` 处理。

## 验证（任何 patch 之后必跑）

```bash
# 1) py_compile 验证 Python 语法
python3.14t -m py_compile <file>

# 2) od -c 看 line 1 raw bytes（read_file 不可信！）
head -1 <file> | od -c | head -1
# 期望: 0000000   #   !   /   u   s   r   /   ...  （无 N| 前缀）

# 3) md5sum vs git HEAD（确认这次 patch 没把文件破坏到 git diff 显示）
md5sum <file>
git show HEAD:<file> | md5sum
```

**为什么 read_file 救不了你**：

`read_file` 工具的输出格式是 `LINE|CONTENT`（N 是行号）——**这是工具的展示格式不是文件内容**。
当 raw bytes 是 `1|#!/usr/bin/env python3` 时：

- 正确读法：line 1 = `#!/usr/bin/env python3`（`1|` 是 read_file 加的行号）
- 误读：line 1 = `1|#!...`（把行号当真内容看）

**判断方法**：用 `od -c` 一次性确认 raw bytes 是 `#!` 还是 `1|#!`。

## 已踩坑案例

| 日期 | 文件 | 症状 | 修复方式 |
|------|------|------|---------|
| 2026-06-02 22:30 | `gen_cron_prompt.py` | 加降级路径段，patch 剥 4 空格缩进 → `lines.append("")` 之外出现 raw markdown | `git restore` + `sed -i` 改两行 |
| 2026-06-02 22:00 | `health_check.py` | 500 行重写，patch 剥缩进 → line 1 变 `1|#!...` | `write_file` 全量重写 |
| 2026-06-02 21:00 | `gen_cron_prompt.py` | 第一次 `lines.append("...## Deep Analysis")` 修，patch 剥缩进 | `git restore` + 改用 `sed -i` |

## 修复工具优先级

| 场景 | 推荐工具 | 备选 |
|------|---------|------|
| 单行替换 | `patch` | `sed -i 's/.../.../'` |
| 2-3 行同缩进 | `patch`（小心）| `sed -i` |
| 4+ 行同缩进 | `sed -i` 或 `write_file` | **绝对不要** `patch` |
| 整个函数 / 块 | `write_file` 全文件 | — |
| 多文件批量 | `execute_code` 写 Python `str.replace()` | — |

## 真实污染诊断流程（污染已发生）

1. `python3.14t -m py_compile <file>` 报 SyntaxError
2. `head -1 <file> | od -c` 看 raw bytes 确认污染
3. `git show HEAD:<file> | head -1` 对比看 HEAD 里是不是也污染（如果 HEAD 也污染 → 历史 commit 错了，需要 `git filter-branch` 或 `git rebase -i`）
4. **HEAD 没污染**：从 HEAD 恢复 `git show HEAD:<file> > <file>`
5. **HEAD 也污染**：找上一个干净 commit，`git show <sha>:<file> > <file>`
6. 重新应用 patch（这次用 `sed -i` 或 `write_file`）
7. `python3.14t -m py_compile` 验证 OK
8. `md5sum <file>` vs `git show HEAD:<file> | md5sum` 确认 raw bytes 一致
