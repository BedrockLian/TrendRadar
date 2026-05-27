# 来源多样性管理

## 问题模式

当某个来源（如虎嗅）在单 slot 中占比 ≥40% 时触发集中警报。具体症状：
- 晚间 slot 虎嗅 40%（6/15条）
- 覆盖多个板块：top_headlines、tech、economy 均有虎嗅条目
- 即使有 per-domain 的 MAX_SAME_SOURCE=3 减半惩罚，跨板块仍会累积

## 解决方案：三层递进

### 第一层：全局硬上限（代码层）

`curate_all()` 中新增全局来源多样性检查：

```python
MAX_SOURCE_PCT = 0.30  # 任何单来源占比不得超过 30%/slot
```

在 per-slot 总量截断之前执行：统计所有板块中各来源的出现次数，对超标来源自动剔除最低分条目。

### 第二层：稀释策略（供给端）

当某个来源持续超标时，添加更多同类高质量源：

| 添加的源 | 分类 | 接入方式 |
|----------|------|----------|
| 36氪 (36kr) | tech | plink.anyfeeder.com/36kr |
| 界面新闻 (jiemian) | news | a.jiemian.com RSS |

遵循 sources.json 格式添加即可生效，无需重启。

### 第三层：权重调整（评分端）

降低过度集中源的 `authority` 评分权重：
- 虎嗅 authority 从 3 降至 2
- 同等条件下评分会倾向其他源

## 检查方法

```bash
# 查看某日某 slot 的来源分布
python3 -c "
import json
from collections import Counter
data = json.load(open('data/curated_evening_20260526.json'))
sections = ['top_headlines','foreign_china','tech','economy','gaming']
src_counts = Counter()
total = 0
for sec in sections:
    for item in data.get(sec, []):
        src = str(item.get('source_platform','') or '').lower()
        src_counts[src] += 1
        total += 1
for src, cnt in src_counts.most_common():
    print(f'  {src}: {cnt} ({cnt/total*100:.0f}%)')
"
```

## 注意事项

- 不需要给优化报告的集中度建议后手动加新源——代码层的 30% 硬上限会自动处理超限情况
- 但若某源连续多天接近 30% 阈值，应在优化报告中标注以便考虑扩大供给端
