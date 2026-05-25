# 日报 cron prompt（标准版）
每次修改 news-secretary skill 后，必须同时更新 cron prompt（Trap 22-24, 37）。prompt 独立于 skill 内容，不会自动同步。

```bash
cronjob action=update job_id=90a2866775df prompt="..."
```

## 全文

按 news-secretary skill 执行本时段推送（v6.5 auto-delivery 模式）。

export PYTHON=/usr/local/bin/python3.14t
export PYTHONPATH=/home/asus/.hermes
export PYTHON_GIL=0

## 主流程

1. 运行编排器：RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)，捕获 stdout 中的 JSON
2. 解析 JSON 中的 status：
   - "silent" → 返回 [SILENT]
   - "error" → 输出 errors 字段内容
   - "ok" → 继续步骤 3

3. 输出 JSON 中的 briefing 字段内容（sanity_check.py 自动拦截违规前缀后缀）

4. 仅 push_id=evening（JSON 中 needs_deep_analysis=true）：
   并行启动 3 个 Pro delegate_task 子 Agent（趋势/跨域/风险）。
   各分析结果通过管道传给 render_deep_analysis.py 格式化：
     echo "$ANALYSIS_TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context
   然后作为独立 final response 分别输出——每条分析单独一条消息。

## 故障恢复

编排器失败时执行 fallback：
0. $PYTHON scripts/push_slot_detect.py
1. $PYTHON scripts/push_prepare.py --push-id {PUSH_ID} {DEDUP_FLAG}
2. [并行] $PYTHON scripts/ai_translate.py --push-id {PUSH_ID} & $PYTHON scripts/batch_fetch.py --push-id {PUSH_ID}; wait
3. BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})
4. NEW_COUNT=0 → [SILENT]
5. $PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}
6. 输出 BRIEFING

## Pre-flight

- cat references/render-format.md
- cat references/deep-analysis-format.md
- cat references/translation-pipeline-sync.md
- 空行规范：条目间 \n\n\n，板块标题后 \n\n\n
- 不要用 send_message，始终用 final response auto-delivery
- sanity_check.py 在推送前自动扫描禁语/死链/敏感词
