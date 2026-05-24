# Git 仓库同步

## 同步命令

```bash
# 核心代码
cp -r ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/config/ ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/migrations/ ~/TrendRadar/trendradar/

# 中心脚本
cp ~/.hermes/scripts/trendradar_health_check.py ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/trendradar_maintenance.py ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/delivery_watchdog.py ~/TrendRadar/hermes-scripts/

# 提交
cd ~/TrendRadar && git add -A && git commit -m "<描述>" && git push
```

⚠️ Skills（SKILL.md）不在 repo 中。README/SETUP 中技能名称引用需手动更新，确保三处一致：目录名、frontmatter `name:`、cron `skills:` 列表。
