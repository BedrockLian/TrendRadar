# Git 仓库同步 — 完整流程

## 三处路径

每处修改需要同步到所有相关位置：

| # | 位置 | 路径示例 | 用途 |
|---|------|---------|------|
| 1 | **Hermes 运行时** | `~/.hermes/trendradar/scripts/` | cron & pipeline 实际加载的版本 |
| 2 | **Hermes 中心脚本** | `~/.hermes/scripts/trendradar_*.py` | no_agent cron 脚本 |
| 3 | **Git 发布仓** | `~/TrendRadar/` | 版本控制 & 分发 |

## 同步命令

```bash
# ── 1. 核心代码 ──
cp -r ~/.hermes/trendradar/scripts/   ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/config/    ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/migrations/ ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/references/ ~/TrendRadar/trendradar/

# ── 2. 依赖文件 ──
cp ~/.hermes/trendradar/pyproject.toml    ~/TrendRadar/trendradar/
# requirements.txt 从 pyproject.toml 手动维护一致

# ── 3. 中心脚本 ──
cp ~/.hermes/scripts/trendradar_*.py     ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/delivery_watchdog.py ~/TrendRadar/hermes-scripts/

# ── 4. Skills（SKILL.md + references/ 子目录） ──
for skill in news-secretary self-healing performance-optimizer weekly-report monthly-report system-config; do
    cp -r ~/.hermes/skills/trendradar/$skill/ ~/TrendRadar/trendradar/skills/
done

# ── 5. 提交 ──
cd ~/TrendRadar && git add -A
git diff --cached --stat   # 确认变更内容无误
git commit -m "<描述>"
git push
```

## 验证步骤

每次同步后执行，确认无遗漏：

```bash
# 1. diff stat 检查 — 期望的 files changed 数量
cd ~/TrendRadar && git diff --stat HEAD~1..HEAD

# 2. 引用文件完整性 — 确认新加文件都入库
# 特别检查 skills 的 references/ 子目录（单独的 git add 步骤）
git ls-files --others --exclude-standard   # 不应有未跟踪文件

# 3. 依赖一致性检查
diff <(grep "^    \"[a-z]" ~/.hermes/trendradar/pyproject.toml | sort) \
     <(grep "^[a-z]" ~/.hermes/trendradar/requirements.txt | grep -v "^#" | sort)
# 输出为空 = 一致；差异行 = 需要手动对齐
```

## 常见遗漏模式

| 遗漏 | 后果 | 如何发现 |
|------|------|---------|
| skill 的 `references/` 子目录未 `git add` | 参考文件只在 Hermes 运行时存在，仓库无记录 | `git status` 显示 `??` 未跟踪 |
| `pyproject.toml` 改了但 `requirements.txt` 没同步 | 新人 `pip install -r requirements.txt` 得到不同版本 | 依赖一致性检查 |
| cron 脚本改了但中心脚本没复制 | 提仓的脚本是旧版，重装后功能异常 | 对比 `diff ~/.hermes/scripts/trendradar_*.py ~/TrendRadar/hermes-scripts/` |
| skill SKILL.md 修改了但 cron skills 列表没更新 | cron 报 `⚠️ Skill not found` | `hermes cron list` 对比技能目录名 |
