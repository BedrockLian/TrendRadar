# render_deep_analysis.py `**` 残留清理（2026-06-02 经验）

## 问题
flash sub-agent 输出的章节标题常带未闭合的 `**`（如 `一、AI 从虚拟溢出…**` 末尾多写一个 `**`，或段中 `X** Y` 当粗体起点）。WeCom 不解析未配对 `**`，原样输出，视觉上"右边多 `**`"。

## 教训：不要假设渲染端不解析
第一次修复直接 `re.sub(r'\*\*', '', text)` 全剥——**错了**。evening 简报里的 `**共 15 条**` 是合法成对 `**`，WeCom 渲染为加粗（用户纠正"其实 WeCom 可以正常解析加粗"）。**全剥会破坏所有成对加粗。**

## 用户方案（2026-06-02 23:15）：末尾残留就地闭合
LLM 想加粗没闭合 → 不剥，反而补成对，让 WeCom 真加粗。

| LLM 输入 | 输出 | WeCom 渲染 |
|---|---|---|
| `X**`（末尾孤儿） | `**X**` | X 加粗 ✓ |
| `**X`（开头孤儿） | `X`（剥） | 剥掉（避免错位） |
| `**X**`（成对） | `**X**` | 加粗 ✓ |
| `**X****`（堆俩） | `**X**`（2 对） | 加粗 ✓ |
| `X** Y`（段中粗体起点） | `X Y`（剥孤儿） | 剥（避免乱加粗） |

## 算法（按行扫描 + 奇偶判定）

```python
# 1) 保护已成对的 **X**（X 内不出现 **）
text = re.sub(r'\*\*([^*\n]{0,80}?)\*\*',
              lambda m: f'\x00OPEN\x00{m.group(1)}\x00CLOSE\x00', text)

# 2) 按行处理剩余 **
def _process_line(line: str) -> str:
    if '**' not in line:
        return line
    parts = line.split('**')
    n_stars = len(parts) - 1
    if n_stars == 0:
        return line
    if n_stars % 2 == 0:
        # 偶数：保留所有，按开-闭-开-闭配对
        out = parts[0]
        for i in range(1, len(parts)):
            out += '**' + parts[i]
        return out
    # 奇数：末尾孤儿
    out = parts[0]
    for i in range(1, len(parts)):
        out += '**' + parts[i]
    if out.endswith('**'):
        # 末尾孤儿 → 移到文本前形成 **X**
        stripped = out[:-2]
        return '**' + stripped + '**'
    # 段中孤儿（如 "X** Y"）→ 剥掉
    return out.replace('**', '', 1)

text = re.sub(r'^[^\n]*', lambda m: _process_line(m.group(0)),
              text, flags=re.MULTILINE)

# 3) 还原 token
text = text.replace('\x00CLOSE\x00', '**').replace('\x00OPEN\x00', '**')
```

## 配套修复：format_analysis 行首 `**` 被误剥

`format_analysis()` 里的 `re.sub(r'^[#*]+\s*', '', line)` 会把行首成对 `**` 当 markdown 标题剥掉。**改为只剥 `#{1,6} ` 标题前缀**：

```python
# 错误：会把 **埃博拉** 剥成 埃博拉
line = re.sub(r'^[#*]+\s*', '', line).strip()
# 正确：只剥 markdown 标题
line = re.sub(r'^#{1,6}\s+', '', line).strip()
```

## 验证

```bash
# 单元测试已固化（tests/test_render_deep_analysis.py，7 个 case）
cd ~/.hermes/trendradar
export PYTHONPATH=/home/asus/.hermes/trendradar
python3.14t -m pytest trendradar/tests/test_render_deep_analysis.py -v

# 端到端：跑今晚 archived 报告的实际输入
python3.14t -c "
import sys
sys.path.insert(0, 'scripts')
from render_deep_analysis import format_analysis
text = open('archive/2026-06-02/evening.deep.md', encoding='utf-8').read()
out = format_analysis(text, topic='测试', push_id='evening')
assert out.count('**') % 2 == 0, f'** 数量奇数: {out}'
print('OK, paired:', out.count('**') // 2)
"
```

## 排查清单
收到"右侧多 `**`"反馈时：
1. 跑端到端，确认 `**` 数量成对
2. 若奇数：检查 `archive/YYYY-MM-DD/evening.deep.md` 实际输入（flash sub-agent 自由生成）
3. 提一条独立 fix：保护已配对 → 按行扫描 → 奇偶判定

## 复盘
- **第一版（错）**：全剥 → 破坏成对加粗
- **第二版（错）**：用 `out = trailing_stars + stripped + trailing_stars` 把 `X**` 改 `**X**` —— 但同时跑行首函数双重叠加，把 `**一、AI**` 变成 `****一、AI****`（4 个）
- **第三版（对）**：先按行 split 重建，**只在末尾有 `**` 时**才把 `**` 移到前面；行首/段中孤儿走剥掉路径
- 用户两次纠正（"其实 WeCom 可以正常解析加粗" + "不如把末尾残留的也加粗了"）才找到正确行为。**先验证渲染假设，再动手。**
