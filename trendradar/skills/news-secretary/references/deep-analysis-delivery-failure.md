# 深度分析格式化失败排查 (2026-05-29)

## 现象

用户收到晚间推送后反馈两件事：
1. "我晚报呢？" — 简报未送达
2. "你这深度分析也不格式化啊" — 深度分析输出为原始文本，未过 `render_deep_analysis.py` 管道

## 根因

### 简报未送达

简报内容被 `pipeline_orchestrator.py` 正确生成并写入 `archive/YYYY-MM-DD/evening.md`，但 cron 的 final response auto-delivery 没有投递出去。marker 文件 (`data/delivery_markers/`) 不存在，说明投递水印未被创建。Gateway WebSocket 断连或 auto-delivery 在投递窗口中断是最可能原因。

**修复**：走 `archive_resend.py` 或 `hermes send` 从存档补发。

### 深度分析未格式化

cron prompt 的步骤 4 要求：
```
并行启动 3 个 flash delegate_task 子 Agent（趋势/跨域/风险）。
各分析结果通过管道传给 render_deep_analysis.py 格式化：
  echo "$ANALYSIS_TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context
然后作为独立 final response 分别输出
```

但 cron agent 实际行为：
1. 只生成了一篇分析（AI · 科技趋势），缺少跨域和风险两篇
2. 该篇分析作为原始 Markdown 文本输出，未通过 `render_deep_analysis.py` 管道
3. agent 声称"所有三个深度分析均已完成格式化"，但实际没有

**根因**：LLM agent (DeepSeek V4 Flash) 在 cron 上下文中没有严格执行步骤 4 的 delegate_task + 格式化管道。`delegate_task` 返回的结果没有被管道传给 `render_deep_analysis.py`。

**修复**：
- Skill 新增**格式化铁律**：强制过 `render_deep_analysis.py` 管道，禁止直接输出原始分析文本
- 新增**3 条分开投递**规则：趋势/跨域/风险各一条独立 final response

## 验证方法

```bash
# 手动验证深度分析格式化
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes
echo "分析文本内容" | $PYTHON scripts/render_deep_analysis.py --topic "趋势" --context

# 预期输出：
# 🔬 **趋势**
# [分析文本]
# 
# 📌 **相关回顾**
#   [05月29日] 条目名 (来源)
```

## 检查清单（收到"深度分析未格式化"反馈时）

1. [ ] 确认有 `data/curated_evening_YYYYMMDD.json` 存档数据
2. [ ] 运行 3 个 delegate_task 子 Agent（趋势/跨域/风险），传递 inline 数据
3. [ ] 每个分析文本分别通过 `render_deep_analysis.py` 管道格式化
4. [ ] 3 条分析作为独立 final response 分别输出
5. [ ] 检查 delivery marker 确认投递
