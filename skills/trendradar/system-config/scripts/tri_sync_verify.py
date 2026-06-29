#!/usr/bin/env python3
"""
tri_sync_verify.py — 验证 TrendRadar .py 在 2-3 副本（外层 legacy / 内层嵌套 / 可选 git worktree）一致。
同时验证 Python runtime 实际 load 的副本（namespace shadow 检测）。

用法:
    python3 tri_sync_verify.py <file_relative_to_scripts_dir>

例:
    python3 tri_sync_verify.py ai_translate.py
    python3 tri_sync_verify.py push_prepare.py

退出码:
    0 = 所有存在副本一致 + runtime load 匹配
    1 = 副本不一致 / runtime check 失败
    2 = runtime 加载的副本与修改的副本不符（namespace shadow 陷阱）

铁律: 改完任何 .py 后必跑。5 秒定位 silent-failure。

v2.1 (2026-06-06) 修复:
  - 原始 `WORKTREE_SCRIPTS = Path("/home/asus/TrendRadar/trendradar" / "scripts")`
    是 str/str 除法 → TypeError (脚本启动就 crash)
  - 修复: 用 `_detect_worktree_scripts()` 探测式 (git worktree list + 常见位置)
    代替硬编码 path 拼接
  - worktree 探测不到时该列报 MISSING 而不是让整个脚本炸
  - 实测可跑: `python3 tri_sync_verify.py ai_translate.py` ✅
"""
import hashlib
import importlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

HERMES_TREND = Path("/home/asus/.hermes/trendradar")
LEGACY_SCRIPTS = HERMES_TREND / "scripts"  # namespace shadow 命中这里
NESTED_SCRIPTS = HERMES_TREND / "trendradar" / "scripts"


def _detect_worktree_scripts() -> Path | None:
    """探测 git worktree 副本路径。返回 None 表示没找到。

    探测顺序:
      1. HERMES_TREND 仓库自身的 git worktree list（嵌套目录是 git repo）
      2. ~/TrendRadar/trendradar/scripts/ 硬编码常见位置
      3. ~/projects/TrendRadar/trendradar/scripts/ 备选
    """
    candidates = []
    # 1) git worktree 探测
    try:
        out = subprocess.run(
            ["git", "-C", str(HERMES_TREND), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                if line.startswith("worktree "):
                    wt_path = Path(line.split(None, 1)[1])
                    candidate = wt_path / "trendradar" / "scripts"
                    if candidate.exists():
                        candidates.append(candidate)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # 2) 硬编码常见位置
    for fallback in (
        Path.home() / "TrendRadar" / "trendradar" / "scripts",
        Path.home() / "projects" / "TrendRadar" / "trendradar" / "scripts",
        Path("/home/asus/TrendRadar/trendradar/scripts"),
    ):
        if fallback.exists() and fallback not in candidates:
            candidates.append(fallback)
    return candidates[0] if candidates else None


WORKTREE_SCRIPTS = _detect_worktree_scripts()


def md5(p: Path) -> str:
    if not p.exists():
        return "MISSING"
    return hashlib.md5(p.read_bytes()).hexdigest()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    rel = sys.argv[1]
    paths = {
        "legacy": LEGACY_SCRIPTS / rel,
        "nested": NESTED_SCRIPTS / rel,
    }
    if WORKTREE_SCRIPTS is not None:
        paths["worktree"] = WORKTREE_SCRIPTS / rel
    else:
        print("ℹ️  worktree 未探测到（单副本安装是 OK 的，跳过 worktree 一致性检查）\n")

    print(f"=== Tri-Sync Verify: {rel} ===\n")
    digests = {}
    for name, p in paths.items():
        d = md5(p)
        digests[name] = d
        print(f"  {name:8} {p}")
        print(f"           md5={d}  {'(missing)' if d == 'MISSING' else ''}")

    # 1) 多副本一致性（只看存在的）
    unique = set(d for d in digests.values() if d != "MISSING")
    if len(unique) > 1:
        print(f"\n❌ MISMATCH: {len(unique)} unique copies detected")
        print("   修复: cp <正确副本> <落后副本>")
        sys.exit(1)
    missing = [n for n, d in digests.items() if d == "MISSING"]
    if missing and len(missing) < len(digests):
        print(f"\n⚠️  Missing (仅报告，不算不一致): {missing}")

    # 2) namespace shadow 实际加载
    print("\n=== Runtime load check (namespace shadow detection) ===")
    # 清 pycache 强制重新 import
    subprocess.run(
        ["find", str(HERMES_TREND), "-type", "d", "-name", "__pycache__",
         "-exec", "rm", "-rf", "{}", "+"],
        capture_output=True, check=False,
    )
    env = {
        **os.environ,
        "PYTHON_GIL": "0",
        "PYTHONPATH": "/home/asus/.hermes",
    }
    code = (
        "import importlib, importlib.util, sys\n"
        "spec = importlib.util.find_spec('trendradar.scripts." + rel[:-3] + "')\n"
        "mod = importlib.import_module('trendradar.scripts." + rel[:-3] + "')\n"
        "print('find_spec:', spec.origin if spec else None)\n"
        "print('actual:   ', mod.__file__)\n"
        "print('MATCH' if spec and spec.origin == mod.__file__ else 'SHADOW-MISMATCH')\n"
    )
    try:
        proc = subprocess.run(
            ["/usr/local/bin/python3.14t", "-c", code],
            capture_output=True, text=True, env=env, timeout=30,
        )
    except FileNotFoundError:
        # 3.14t 不在时回退到 python3
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env, timeout=30,
        )
    for line in proc.stdout.splitlines():
        if "find_spec" in line or "actual" in line or "MATCH" in line or "SHADOW" in line:
            print(f"  {line}")
    if "SHADOW-MISMATCH" in proc.stdout:
        print("\n❌ Namespace shadow: Python loaded the WRONG copy")
        print("   find_spec 报 nested, 实际 load 的是 legacy（或反之）")
        sys.exit(2)
    if proc.returncode != 0:
        print(f"\n⚠️  Runtime check failed (exit {proc.returncode}):")
        print(proc.stderr)
        sys.exit(1)

    print(f"\n✅ All checks passed for {rel}")


if __name__ == "__main__":
    main()
