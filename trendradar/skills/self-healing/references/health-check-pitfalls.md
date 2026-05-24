# 健康检查脚本维护陷阱

> 修复于 2026-05-24。以下陷阱在技能重组/脚本重命名后容易出现。

## 1. SKILL_DIR 路径过时
技能目录从 `skills/productivity/trendradar-news-secretary` 迁移到 `skills/trendradar/news-secretary` 后，`trendradar_health_check.py` 中的 `SKILL_DIR` 默认值未同步更新。
**修复**: 搜索所有脚本中的硬编码技能路径，与磁盘实际目录比对。
```bash
grep -rn "skills/" ~/.hermes/scripts/trendradar_health_check.py
ls -d ~/.hermes/skills/trendradar/*/
```

## 2. 导入检查使用旧式裸导入
健康检查的 `check_pipeline()` 用 `sys.path.insert(0, SCRIPTS); import mod_name` 做导入验证。导入架构改为全限定后（`from trendradar.scripts.xxx import`），旧式检查会误报。
**修复**: 改为 `python -c "import trendradar.scripts.{mod_name}"` + 设置 `PYTHONPATH`。
```python
env = os.environ.copy()
env['PYTHONPATH'] = str(TR.parent)
subprocess.run([sys.executable, '-c', f'import trendradar.scripts.{mod_name}'], env=env)
```

## 3. 新增脚本未加入检查列表
`check_scripts()` 和 `check_pipeline()` 的脚本列表需与新 pipeline 同步。添加新脚本后（如 `pipeline_orchestrator.py`），必须更新两处列表。
**检查**: 对比两个列表与实际文件：
```bash
grep "required = \[" ~/.hermes/scripts/trendradar_health_check.py -A10
grep "pipeline_steps = \[" ~/.hermes/scripts/trendradar_health_check.py -A5
ls ~/.hermes/trendradar/scripts/*.py | xargs -n1 basename | sort
```

## 4. 未导入模块致静默 NameError
`check_gateway()` 在异常路径用 `logging.debug()` 但未 `import logging`。错误路径极少触发，导致 NameError 被静默吞掉。
**预防**: 全局 grep 脚本中所有 `logging.` 调用，确认顶部已导入。
```bash
grep -n "logging\." ~/.hermes/scripts/trendradar_health_check.py
head -5 ~/.hermes/scripts/trendradar_health_check.py | grep "import logging"
```
