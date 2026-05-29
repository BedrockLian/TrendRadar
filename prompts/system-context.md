## 系统背景

基于 Hermes Agent（LLM-driven cron 框架）的自动化新闻简报系统 TrendRadar。

**部署环境：** WSL2，外网通过 HTTP 代理访问。多个 cron job，核心日报每天 9/12/21 三个时段自动运行。

**核心 pipeline：**
1. RSS 多源异步抓取（~50 个源，中/英/日）
2. AC 自动机关键词分类（5 域：头条/科技/经济/游戏/外媒看华）
3. 综合评分 + 来源多样性惩罚 → 精选排序
4. AI 批量翻译 + 中文短摘要扩写
5. 纯脚本渲染 Markdown → 字节分片投递企业微信
6. 晚间额外 3 并行子 Agent 深度分析

**代码仓库：** `~/TrendRadar/`（工作副本，推 GitHub）+ `~/.hermes/trendradar/`（cron 运行时副本，有时不同步），TRENDRADAR_HOME 指向后者，pipeline_orchestrator.py 入口。

**关键文件：**
- `scripts/curate_and_push.py`（519行） — 评分/精选/多样性惩罚混合在一个文件
- `scripts/settings.py` — 配置中心（MIN_SCORE/MAX_PER_DOMAIN/MAX_SAME_SOURCE/TRENDRADAR_HOME）
- `scripts/pipeline_orchestrator.py` — pipeline 编排（7 阶段串联）
- `scripts/sanity_check.py` — 发布前拦截器（前言剥离 + 禁语/死链/敏感词）
- `scripts/validate_output.py` — 新增的 cron agent 输出格式验证
- `scripts/gen_cron_prompt.py` — 从 pipeline 步骤定义自动生成 cron prompt
- `scripts/ai_translate.py` — 批量翻译 + 中文摘要扩写（BATCH_SIZE=5）
- `hermes-scripts/delivery_watchdog.py` — 投递看门狗
- `hermes-scripts/trendradar_maintenance.py` — 每日备份+清理+烟雾测试
- `trendradar/config/keywords.py` — 505 关键词 × 6 域
- `trendradar/config/ai_interests.yaml` — 兴趣偏好（正面加分/排除过滤）

**已知工程问题：**
1. **两副本不同步** — 工作副本改完要手动 rsync 到 cron 副本，容易漏
2. **LLM 输出超标** — cron agent 偶尔在简报前加"好消息——所有三个深度分析均已格式化"等前缀破坏 WeCom 格式
3. **静默投递失败** — pipeline 返回 ok 但消息未送达（Gateway WebSocket 断连等），看门狗之前 22:00 才查
4. **PYTHON_GIL 冲突** — 环境变量 PYTHON_GIL=0 导致 hermes send 崩溃
5. **测试套件有 7 个长期挂起失败** — ai_translate(async 不兼容) + record_fingerprints(DB schema 不存在) 混在烟雾测试里
6. **gen_cron_prompt.py 有语法错误** — f-string 引号嵌套问题，从未真正跑通过
