# `_load_interests()` 滑窗停用词陷阱

## 问题

`curate_and_push.py` 的 `_load_interests()` 函数（line 60-124）从 `ai_interests.yaml` 加载正面/排除关键词时，使用**中文滑窗**提取所有 2-3 字子串：

```python
chars = list(re.findall(r'[\u4e00-\u9fff]', content))
for i in range(len(chars)):
    for wlen in (2, 3):
        if i + wlen <= len(chars):
            word = ''.join(chars[i:i+wlen])
            if word not in stopwords:
                (negative if in_negative else positive).add(word)
```

这意味着 `ai_interests.yaml` 中任意排除短语会被拆解成全部 2-3 字组合进入排除集。

## 示例：2026-05-28 烟雾测试失败

`ai_interests.yaml` 排除规则：
```yaml
negative:
- 游戏评测（除非是行业重大新闻）
```

滑窗从「除非是行业重大新闻」提取的 2 字子串包括：
```
除非 非是 是行 行业 业重 重大 大新 新闻
```

「新闻」作为排除关键词 → 任何标题含「新闻」二字的条目全部 score=0、pass=False → 测试标题「科技新闻标题第0号」被误杀。

## 停用词列表

`stopwords` 集合在 `curate_and_push.py:100-108`。以下词必须保持在停用词中以防止误触：

```
新闻, 游戏, 体育, 行业, 重大, 娱乐, 明星
```

新增排除短语时，检查其 2-3 字拆解产物是否会混入通用词。如果会，先确认该通用词已在 stopwords 中。

## 诊断

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
from curate_and_push import _load_interests
pos, neg = _load_interests()
bad = {'新闻','游戏','体育','行业','重大','娱乐','明星'} & neg
if bad:
    print(f'❌ 通用词误入排除集: {bad}')
else:
    print('✅ 排除集干净')
print(f'排除集共 {len(neg)} 个关键词')
"
```

## 测试用例

`tests/test_curate_and_push.py::TestScore::test_strong_item_passes` — 如果标题含「新闻」时该用例失败，说明排除集出问题了。

## 修复记录

2026-05-28: 将 `新闻/游戏/体育/行业/重大/娱乐/明星` 加入 stopwords（`curate_and_push.py` line 108）。
