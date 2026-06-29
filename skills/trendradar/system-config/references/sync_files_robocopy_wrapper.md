# sync_files.py — robocopy替代 rsync 的 Windows wrapper

> **来源**:2026-06-10 TrendRadar同步流程首次实装,因为 `rsync` 在 Windows 上没有(winget/choco/scoop 都找不到 cwRsync / Win32Rsync / sync 等包)。
>
> **位置**: `C:\Users\ASUS\trendradar-sync-tools\sync_files.py`(备份在 `$HOME/trendradar-sync-tools/`,跟 sync_repo.sh一起)

## 用法

```bash
python sync_files.py [--mirror] <src> <dst> [excludes...]
```

- `--mirror`: robocopy `/MIR`(默认)—— 等价 rsync `-a --delete`
- 不带 `--mirror`: robocopy `/E`—— 只 copy,不删 dst 多出文件
- excludes: 含 `.` 的视为**文件 pattern**(`/XF`),否则视为**目录**(`/XD`)

##完整源码

```python
#!/usr/bin/env python3
"""sync_files.py — rsync替代,用 robocopy 做 Windows 上的 rsync风格 exclude。
调用: python sync_files.py [--mirror] <src> <dst> [excludes...]
excludes 中含 . 的视为文件 pattern (/XF),否则视为目录 (/XD)。"""
import os, sys, subprocess

def main():
 args = sys.argv[1:]
 if not args or args[0] in ("-h", "--help"):
 print(__doc__)
 return
 mirror = False
 if args and args[0] == "--mirror":
 mirror = True
 args = args[1:]
 if len(args) <2:
 print("usage: sync_files.py [--mirror] <src> <dst> [excludes...]")
 return
 src, dst = args[0], args[1]
 excludes = args[2:]
 cmd = ["robocopy", src, dst, "/MIR" if mirror else "/E",
 "/R:0", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS"]
 for ex in excludes:
 cmd += ["/XF", ex] if "." in ex else ["/XD", ex]
 r = subprocess.run(cmd, capture_output=True)
 rc = r.returncode
 if rc >=8: # robocopy8+ = error;0/1/2/3 = success
 print("robocopy ERROR rc=", rc)
 print(r.stdout.decode("utf-8", "replace")[:2000])
 sys.exit(1)
 else:
 print("robocopy ok rc=", rc, "src=", src, "dst=", dst)

main()
```

## robocopy flags含义

| flag |作用 | rsync 等价 |
|------|------|-----------|
| `/MIR` |镜像(自动 delete dst 多出) | `--delete` |
| `/E` |递归 copy(不删 dst) | `-r` |
| `/R:0` | 重试0 次 | `--no-retry`(robocopy 默认重试1M 次) |
| `/W:0` | 重试间隔0 秒 | n/a |
| `/NFL` | 不输出文件名 | `--quiet` 部分 |
| `/NDL` | 不输出目录名 | `--quiet` 部分 |
| `/NJH` | 不输出 job header | n/a |
| `/NJS` | 不输出 job summary | n/a |
| `/NC` | 不输出 class | n/a |
| `/NS` | 不输出 size | n/a |
| `/XF <pattern>` |排除文件 | `--exclude='<pattern>'` |
| `/XD <pattern>` |排除目录 | `--exclude='<dir>/'` |

## robocopy exit code语义(跟 Unix exit 不一样!)

- `0` = no change
- `1` = files copied successfully
- `2` = extra files deleted
- `3` = both = success
- `8+` = failure / partial

Python wrapper 把 `>=8` 当作 error,`0-3` 都是 success。

##完整 EXCLUDES数组(TrendRadar 用)

```python
EXCLUDES = [
 "__pycache__", "*.pyc", "*.bak", ".pytest_cache", ".git",
 "data", "cache", "archive", "logs", "output", "mail_queue",
 ".env", ".env.local",
 "*.db", "*.db.backup", "*.db-shm", "*.db-wal",
 "*.json.zst", "*.marker",
 "*.broken", "*.swp", "*.swo", "*.tmp",
]
```

## 调用示例

```bash
# 把运行时 scripts/镜像到本地仓库(排除运行时数据 +临时文件)
python sync_files.py --mirror \
 "C:/Users/ASUS/AppData/Local/hermes/trendradar/scripts" \
 "C:/Users/ASUS/AppData/Local/hermes/repo trendradar/scripts" \
 __pycache__ *.pyc *.bak .pytest_cache .git \
 *.broken *.swp data cache archive logs \
 .env *.db *.json.zst *.marker

# robocopy 输出示例(成功时 stdout静默,只 stderr 一行)
# robocopy ok rc=1 src= ... scripts dst= ... scripts
```

##故障排查

|症状 |原因 |修复 |
|------|------|------|
| `robocopy: command not found` | robocopy 不在 PATH | Windows 默认在 `C:\Windows\System32\robocopy.exe`,手动添加 PATH 或调绝对路径 |
| `ERROR5 (0x00000005) Access is denied` | dst 有只读文件 /进程占用 | 关占用进程或 `robocopy /R:0 /W:0` 后 skip |
| `ERROR32 (0x00000020) The process cannot access the file` | 文件被 lock(常见于 `.git/objects/`还在用) | 加 `/XF .git/` 或先 close占用 |
| rc=16 | FATAL ERROR(参数错) | 检查 `/XD` 和 `/XF`后面跟 glob,不能跟绝对路径 |
| rc=8 |一些文件 copy失败 | 看 stdout,通常是 dst权限问题 |

##已知坑

1. **MSYS bash 下 robocopy 不接受单引号路径** —— `python sync_files.py --mirror 'C:/path with space'` 在 MSYS OK,但 robocopy 直接调(不走 Python wrapper)用 `'path with space'` 会报 path not found。用双引号包路径
2. **robocopy 中文输出乱码** —— Windows cmd 默认 GBK,robocopy 输出中文文件名乱码。Python wrapper 用 `r.stdout.decode("utf-8", "replace")` 也救不了(因为 cmd.exe 输出 GBK)。**不**用 stdout解析,只看 rc
3. **`.git` 不能被 robocopy MIR** —— `MIR` 会尝试进入 `.git/objects/` 然后失败(文件 lock)。EXCLUDES 必须含 `.git`
4. **NTFS 长路径 >260字符** —— robocopy 默认不处理超长路径。需要在 cmd启用 LongPathsEnabled 或用 `\\?\` 前缀
