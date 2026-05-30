# 代码仓库多 Agent 并行审计

审计目标：工作区内的代码仓库。并行启动 5 个子 Agent，各自独立扫描后汇总。

## Agent 1 — 安全审计
扫描所有 Python 文件，找出安全风险。

## Agent 2 — 依赖与配置审计
检查依赖锁定、凭证泄漏、配置文件中的硬编码敏感值。

## Agent 3 — 代码质量、SKILL.md 与 reference 文档一致性
扫描 Python 代码的坏味道。同时检查 SKILL.md 的技能定义完整性，以及 reference 文档中的路径引用、命令示例、交叉引用是否与仓库实际文件一致。

## Agent 4 — 架构与设计
评估模块耦合度、职责划分、配置收敛、错误码体系。

## Agent 5 — 测试与可测性
分析测试覆盖率缺口、测试质量、CI 集成。

## 汇总格式

```
[CRITICAL] auth.py:42
[HIGH]    core.py:230
[MEDIUM]  helpers.py:15
[LOW]     __init__.py:3
```

每个条目一行，[严重度] 文件:行号 — 一句话简述。CRITICAL/HIGH 优先列出。
