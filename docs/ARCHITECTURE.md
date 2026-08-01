# 架构

## 边界

```text
src/trendradar/config/    静态配置、关键词、来源和计划
src/trendradar/pipeline/  日报编排和管线阶段
src/trendradar/sources/   RSS 来源适配器
src/trendradar/intelligence/ 分类、评分、热度和翻译
src/trendradar/reporting/ Markdown、报告和审计
src/trendradar/runtime/   路径、存储、日志、锁和公共工具
src/trendradar/cli/       Codex 和人工命令入口
.runtime/data/             指纹、运行记录和缓存索引
.runtime/outputs/          面向用户的 Markdown 产物
ops/codex/       体检、维护和看门狗
skills/          薄任务说明，引用本目录
```

依赖方向为 `ops/codex -> trendradar.pipeline/reporting -> trendradar.sources/intelligence/runtime -> trendradar.config`。业务模块不依赖计划平台；它们只返回数据、写入产物并输出 JSON。

## 运行时布局

`paths.py` 是路径单一来源：

- 仓库内运行：`<repo>/.runtime/` 保存可变状态。
- 设置 `TRENDRADAR_HOME`：使用显式运行目录。
- 配置优先从显式运行目录的 `config/` 读取；不存在时回退到源码 `src/trendradar/config/`。

## 模块职责

- `fetch_feeds.py`：并行抓取和解析来源。
- `push_prepare.py`：原始缓存、去重、分类和精选。
- `ai_translate.py`：按来源语言批量翻译。
- `render_markdown.py`：纯函数式 Markdown 渲染。
- `pipeline_orchestrator.py`：按时段编排并生成统一结果。
- `output_protocol.py`：预算、结果信封和运行日志。
- `execution_lock.py`：防止同一日报并发执行。

外部平台不进入业务代码；Codex 计划任务消费结果协议。
