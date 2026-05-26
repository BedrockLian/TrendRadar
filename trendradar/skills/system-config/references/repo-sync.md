# Git 仓库同步 — 完整流程

## 三处路径

每处修改需要同步到所有相关位置：

| # | 位置 | 路径示例 | 用途 |
|---|------|---------|------|
| 1 | **Hermes 运行时** | `~/.hermes/trendradar/scripts/` | cron & pipeline 实际加载的版本 |
| 2 | **Hermes 中心脚本** | `~/.hermes/scripts/trendradar_*.py` | no_agent cron 脚本 |
| 3 | **Git 发布仓** | `~/TrendRadar/` | 版本控制 & 分发 |

## 同步命令（推荐 rsync）

**运行时 → Git 发布仓**（最常用：运行时修改了代码，回写仓库）：

```bash
rsync -av \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.env' \
  --exclude='cache/' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='mail_queue/' \
  --exclude='output/' \
  --exclude='config/sources.json' \
  --exclude='skills/' \
  --exclude='监管趋势深度分析_*.md' \
  /home/asus/.hermes/trendradar/ \
  /home/asus/TrendRadar/trendradar/
```

rsync 优于 `cp -r`：自动处理新增目录/文件、排除运行时数据（cache/data/logs/output/mail_queue）、保留本地独有的 sources.json 和 skills/。

**Git 发布仓 → 运行时**（重装后还原）：

```bash
rsync -av \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  /home/asus/TrendRadar/trendradar/ \
  /home/asus/.hermes/trendradar/
```

**中心脚本同步**（no_agent cron 脚本）：

```bash
cp ~/.hermes/scripts/trendradar_*.py     ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/delivery_watchdog.py ~/TrendRadar/hermes-scripts/
```

**Skills 同步**：

```bash
for skill in news-secretary self-healing performance-optimizer weekly-report monthly-report system-config; do
    cp -r ~/.hermes/skills/trendradar/$skill/ ~/TrendRadar/trendradar/skills/
done
```

**提交**：

```bash
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
git ls-files --others --exclude-standard   # 不应有未跟踪文件

# 3. 依赖一致性检查
diff <(grep "^    \"[a-z]" ~/.hermes/trendradar/pyproject.toml | sort) \
     <(grep "^[a-z]" ~/.hermes/trendradar/requirements.txt | grep -v "^#" | sort)
# 输出为空 = 一致；差异行 = 需要手动对齐
```

## 常见遗漏模式

| 遗漏 | 后果 | 如何发现 |
|------|------|---------|
| `trendradar/references/` 新增文件未 `git add` | 统一参考文件在仓库缺失 | `git status` 显示 `??` 未跟踪 |
| `pyproject.toml` 改了但 `requirements.txt` 没同步 | 新人 `pip install -r requirements.txt` 得到不同版本 | 依赖一致性检查 |
| cron 脚本改了但中心脚本没复制 | 提仓的脚本是旧版，重装后功能异常 | 对比 `diff ~/.hermes/scripts/trendradar_*.py ~/TrendRadar/hermes-scripts/` |
| skill SKILL.md 修改了但 cron skills 列表没更新 | cron 报 `⚠️ Skill not found` | `hermes cron list` 对比技能目录名 |
