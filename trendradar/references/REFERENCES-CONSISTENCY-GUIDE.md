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
for f in traps.md pipeline.md translate*.md render-format.md; do
    echo "=== $f ==="
    find references/ skills/*/references/ -name "$f" -exec md5sum {} \;
done
```

## 检查流程（修改 references 后）

1. 受影响 Skill 列表：`news-secretary`、`self-healing`、`performance-optimizer`、`system-config`
2. `cp` 同步到每一个 Skill 的 references/
3. 运行 `find skills/ -name "xxx.md" -exec md5sum {} \;` 验证一致
4. `find skills/*/references/` 检查是否有残留的旧文件需要清理
