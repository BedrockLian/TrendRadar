# References 一致性维护指南

> 指导 Agent 消除 Skill references/ 与根 references/ 之间的内容冲突。

## 两套 references 的关系

TrendRadar 存在两套 references 目录：

```
trendradar/
├── references/                     ← 根目录（项目级真相源）
├── skills/news-secretary/references/   ← Skill 目录中同名副本
├── skills/self-healing/references/     ← 又一份副本
```

**Hermes Agent 加载 Skill 时，只读 Skill 目录下的 `references/`**。根目录是维护者编辑的位置。

修改根目录后，必须同步到所有 Skill 副本（每个 Skill 有自己的 linked files 列表）：

```bash
cd ~/TrendRadar/trendradar
cp references/xxx.md skills/news-secretary/references/xxx.md
find skills/*/references -name "xxx.md" -exec cp references/xxx.md {} \;
```

## 同步检查

```bash
# 检查所有同名文件是否一致
for f in TRAPS.md PIPELINE.md ARCHITECTURE.md SETUP.md; do
    echo "=== $f ==="
    find references/ skills/*/references/ -name "$f" -exec md5sum {} \;
done
```

## 检查流程（修改 references 后）

1. 受影响 Skill 列表：`news-secretary`、`self-healing`、`performance-optimizer`、`system-config`
2. `cp` 同步到每一个 Skill 的 references/
3. 运行 `find skills/ -name "xxx.md" -exec md5sum {} \;` 验证一致
4. `find skills/*/references/` 检查是否有残留的旧文件需要清理

---

# Skill 审计清单

每次修改 skill 后，按此清单验证。

## 必检项

```python
import os, re; from pathlib import Path
d = Path('/home/asus/.hermes/skills/trendradar')
for sd in sorted(d.iterdir()):
    if not sd.is_dir(): continue
    sm = sd / 'SKILL.md'
    if not sm.exists(): continue
    c = sm.read_text(); lc = len(c.split(chr(10)))
    refs = re.findall(r'`references/([^`]+)`', c)
    ref_dir = sd / 'references'
    dead = [r.split('#')[0].strip() for r in refs if not (ref_dir / r.split('#')[0].strip()).exists()]
    print(f'{"✅" if not dead else "❌"+str(len(dead))} {sd.name:25s} {lc:3d} lines')
```

## 审计维度

| 维度 | 检查 | 目标 |
|------|------|------|
| Dead references | `references/xxx.md` 文件是否存在 | 0 个 dead |
| 行数 | SKILL.md 总行数 | ≤80（≤50 更佳） |
| 触发段 | 包含 `## 触发` / `## 运行` / `## When to Use` | 必须有 |
| 描述 | 前 60 字符纯中文，不含 English code identifiers | 纯中文 |
| 版本 | 需与代码当前版本一致 | 无过期版本号 |
| Cron 同步 | prompt 中 `vX.Y` 与 skill version 一致 | 一致 |
| 引用解析 | prompt 中 `references/xxx.md` 可追溯到 skill 目录 | 全部可解析 |

## Cron prompt 同步

修改 skill 后必须单独更新 cron prompt：
```bash
cronjob action=update job_id=<JOB_ID> prompt="..."
```

日报 cron 的标准 prompt 文本在 `references/cron-prompt-canonical.md`。

## 常见坑

1. **References 复制遗漏**：共享 references (`~/.hermes/trendradar/references/`) 不会自动出现在 skill 目录下，需手动 `cp`。
2. **版本号滞后**：SKILL.md 更新后 cron prompt 不会自动同步版本号。
3. **行数膨胀**：长内容（>20 行）应拆到 references 文件，SKILL.md 只保留概览 + 触发条件 + 核心规则。
