# WSL 磁盘空间管理

WSL + Docker Desktop + TrendRadar (uv/npm/pip 缓存) 的组合容易快速耗尽 C 盘。典型大项及清理方法：

## 可清理目标

| 目标 | 位置 | 典型大小 | 清理方法 |
|------|------|---------|---------|
| uv cache | `AppData\Local\uv\cache` | 30-45G | `uv cache clean` |
| Docker data | `AppData\Local\Docker\wsl\disk\docker_data.vhdx` | 15-20G | 停 Docker Desktop 后删整个 `Docker\` 目录 |
| npm cache | `AppData\Local\npm-cache` 或 `~/.npm` | 3-5G | `npm cache clean --force` |
| pip cache | `AppData\Local\pip\cache` | 300-500M | `pip cache purge` |
| NVIDIA DXCache | `AppData\Local\NVIDIA\DXCache` | 10-15G | 删目录下所有 `.nvph` 文件（自动重建） |
| Windows Temp | `Windows\Temp` + 用户 Temp | 6-8G | `del /s /q` |
| Cinebench/Redshift | `AppData\Roaming\MAXON\...\Cache` | 4-5G | 删 Cache 目录 |
| DeliveryOptimization | `Windows\ServiceProfiles\...\DeliveryOptimization\Cache` | 20-30G | 管理员: `net stop DoSvc` → 删目录 |
| hiberfil.sys | C:\ | 12-15G | 管理员: `powercfg /h off` |
| DriverStore 旧驱动 | `Windows\System32\DriverStore\FileRepository` | 10-15G | 管理员: `Dism /Cleanup-Image /StartComponentCleanup` |
| WinSxS | `Windows\WinSxS` | 20-25G | 管理员: `Dism /Cleanup-Image /StartComponentCleanup /ResetBase` |
| Package Cache | `ProgramData\Package Cache` | 3-5G | 直接删目录 |
| NVIDIA App update | `ProgramData\NVIDIA Corporation\NVIDIA App\UpdateFramework` | 3-4G | 直接删目录 |

## 分析工具

用 WizTree 扫描 C 盘后导出 CSV，用 Python 解析大项：

```python
import csv
with open('wiztree.csv', encoding='utf-8-sig') as f:
    next(f); reader = csv.DictReader(f)
    items = [(int(r.get('大小',0) or 0), r['文件名称'].strip('"'))
             for r in reader if int(r.get('大小',0) or 0) > 100*1024**2]
    items.sort(key=lambda x: -x[0])
    for s, p in items[:50]:
        print(f'{s/1024**3:.1f}G  {p[:90]}')
```

## 从 WSL 执行 Windows 清理命令

- 路径含空格/中文：用 `powershell.exe -Command "..."` 而非 cmd
- 大目录删除：放 `terminal(background=True, notify_on_complete=True)`
- PS1 脚本：去掉 if/else 分支，用 `-ErrorAction SilentlyContinue` 吞错
- `2>$null` 易导致解析错误 → 用 `2>nul`（小写、不加 $）
- WSL 读 `/mnt/c/` 大文件可能 IO 错误 → 先 `cp` 到 `/tmp/`
- 管理员权限操作（DISM、powercfg）：只能从管理员 PowerShell 执行
