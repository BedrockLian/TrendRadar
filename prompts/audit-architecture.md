# 架构审计

**目标：** 评估 TrendRadar 系统的架构质量 — 模块边界、数据流、依赖耦合、单点故障。

**范围：** `scripts/`、`hermes-scripts/`、`trendradar/config/`、cron 配置、双副本部署结构、Hermes Agent 集成层。

**审计方向（不限于）：**

1. **模块依赖图** — pipeline 各阶段之间是真正的松耦合还是假解耦？`curate_and_push.py` 同时做评分、精选、多样性惩罚、来源健康惩罚、兴趣偏好过滤，这个文件的内聚性如何？该不该拆？

2. **数据流** — `TRENDRADAR_HOME`（→`~/.hermes/trendradar/`）与 `~/TrendRadar/` 两条路径在全系统中的使用一致性。哪些脚本用 `__file__` 解析路径，哪些读环境变量，哪些硬编码？两副本设计是必要隔离还是偶然的历史遗留？

3. **错误传播与容错** — pipeline 失败时的退化策略（编排器→fallback 手动管线→[SILENT]）。看看这个链条是不是每层都真的能兜住下一层。特别关注: 外部 API 超时（DeepSeek/rsshub）、网络中断（WSL 代理场景）、WeCom Gateway 断连。

4. **单点故障** — `settings.py` 作为全局配置中心，哪些参数应该可热加载？如果 `pipeline_orchestrator.py` 崩了，fallback 手动管线是真独立还是共享同一批脆弱的 import？

5. **Hermes 框架依赖** — 哪些逻辑深度耦合在 Hermes Agent 的 cron/delivery/auto-delivery 机制上？如果要迁移到非 Hermes 环境，哪些地方要改？

**输出格式：** 列表式标注风险等级（🔴 严重 / 🟡 警告 / 🔵 观察），每条附一至两句话的判断依据。
