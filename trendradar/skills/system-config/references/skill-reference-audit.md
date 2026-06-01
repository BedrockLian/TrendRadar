# SKILL.md 参考文档路径审计

> 记录于 2026-05-30。SKILL.md 中 `references/` 开头的参考文档分两类，路径解析规则不同。

## 两类参考文档

| 类型 | 实际位置 | SKILL.md 中正确写法 | 示例 |
|------|---------|-------------------|------|
| **Skill 本地** | `skills/<name>/references/xxx.md` | `references/xxx.md` | `references/fix-recipes.md` |
| **Root 级** | `trendradar/references/xxx.md` | `../../references/xxx.md` | `../../references/TRAPS.md` |

> 注意：cron 副本（`~/.hermes/skills/trendradar/`）的目录结构与工作树（`~/TrendRadar/trendradar/skills/`）不同，但 `../../references/` 在工作树中正确解析到 `trendradar/references/`。Agent 通过 `skill_view` 加载 skill 后使用绝对路径或当前工作目录访问文件，不受 SKILL.md 相对路径影响。

## 审计命令

检查所有 SKILL.md 中 `.md` 引用是否可解析：

```bash
cd ~/TrendRadar/trendradar/skills
python3 -c "
import re, os
for name in ['news-secretary','report-generator','self-healing','system-config']:
    path = f'{name}/SKILL.md'
    content = open(path).read()
    refs = re.findall(r'\`([^\`]*\.md)\`', content)
    for ref in refs:
        ref = ref.strip()
        if ref.startswith('~') or ref.startswith('/') or '/' not in ref: continue
        if 'YYYY' in ref or 'cat /' in ref: continue
        resolved = os.path.normpath(os.path.join(name, ref))
        if not os.path.exists(resolved):
            print(f'  BROKEN {name}: {ref} -> {resolved}')
"
```

## 批量修复命令

```bash
cd ~/TrendRadar/trendradar/skills
for skill_dir in news-secretary self-healing system-config; do
  for ref in TRAPS ARCHITECTURE PIPELINE SETUP "REPO-SYNC" MAINTENANCE "DELIVERY-WATERMARK" INDEX; do
    sed -i "s|references/${ref}.md|../../references/${ref}.md|g" $skill_dir/SKILL.md
  done
done
# 修复可能产生的双重前缀
sed -i 's|../../../../references/|../../references/|g' */SKILL.md
```
