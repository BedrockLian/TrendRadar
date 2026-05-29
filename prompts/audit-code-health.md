# 代码健康审计

**目标：** 评估 TrendRadar 的代码质量 — 死代码、错误处理、可观测性、测试套件健康度。

**范围：** `scripts/`、`hermes-scripts/`、`tests/`、`migrations/` 中的 Python 代码。侧重运行时行为而非静态风格。

**审计方向（不限于）：**

1. **死代码与废弃路径** — 找从未被调用的函数、import 了但不用的模块、被注释掉的代码块、定义但未检查的常量（如 `sanity_check.py` 中的 `CN_AI_PATTERNS`）。`config/keywords.py` 中 505 个关键词有没有因域重构而废弃的条目？`migrations/` 的脚本都已应用过还是混有未执行的？

2. **错误处理模式** — 检查 `except: pass` / `except Exception: pass` 的数量和上下文。至少 3 处已知的异常吞噬（`_get_source_penalty`、`_get_health_penalty`、`_load_interests` 的 yaml 读取失败）。这些静默失败在什么场景下会掩盖真正的问题？

3. **可观测性** — 日志是否覆盖所有故障路径？关键决策点（精选数量不足、翻译空结果、所有 RRSHub 超时）是否有结构化日志（`[timestamp] [LEVEL] [module]` 格式）？`[WARNING]` 在实际运维中有人看吗？哪些应该升级为 `[ERROR]` 或退出码？

4. **测试套件健康度** — 测试套件长期挂起 7 个失败（async 不兼容、DB schema 不存在），这些是 should-fix 还是 should-deselect？`test_diversity_penalty_same_source` 依赖 `_load_interests()` 的运行时行为（兴趣配置变化会导致测试失败？），这是脆性测试还是合理集成测试？烟雾测试的过滤条件（`-k 'not slow and not ai_translate and not push_prepare and not TestRecordFingerprints'`）是否需要随代码变化而维护？

5. **import 与模块加载** — 已知 `test_push_prepare.py` 在特定 PYTHONPATH 下有 import 死锁。`trendradar` 包（有 `__init__.py`）和 `scripts/`（无 `__init__.py`）两条 import 路径的冲突历史。`sys.path.insert(0, ...)` 的脆弱性。

**输出格式：** 按目录分组，每条标注（🔴 运行时风险 / 🟡 维护负担 / 🔵 建议优化），附代码位置（文件名:行号）。
