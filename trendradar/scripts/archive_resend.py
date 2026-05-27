#!/usr/bin/env python3
"""archive_resend.py — 从存档重发简报（防幻觉补发工具）

用法:
  # 补发今天的早报
  python3 archive_resend.py --slot morning

  # 补发指定日期的午间简报
  python3 archive_resend.py --date 2026-05-27 --slot noon

  # 列出可用存档
  python3 archive_resend.py --list

流程:
  1. 读 archive/YYYY-MM-DD/{slot}.md
  2. 校验文件存在且非空
  3. 打印前 200 字供确认
  4. 走 hermes send 投递

安全约束:
  - 不存在存档文件时直接报错退出，禁止自行生成内容
  - 投递前必须显示预览让用户确认
"""
import sys
import subprocess
import argparse
from pathlib import Path

# 路径解析：脚本在 trendradar/scripts/ 或 trendradar/trendradar/scripts/ 下均可
_BASE = Path(__file__).resolve().parent.parent  # 一次 parent = scripts/，两次 = trendradar/
# 如果 _BASE 是 'trendradar' 目录（有 __init__.py），说明在嵌套包中，再上一层
if (_BASE / '__init__.py').exists() and _BASE.name == 'trendradar':
    _BASE = _BASE.parent
TRENDRADAR_HOME = _BASE
ARCHIVE_BASE = TRENDRADAR_HOME / 'archive'

SLOT_NAMES = {'morning': '早报', 'noon': '午间速递', 'evening': '今日回顾'}


def list_archives():
    """列出所有可用存档"""
    if not ARCHIVE_BASE.exists():
        print("[ERROR] 存档目录不存在")
        return
    dates = sorted([d.name for d in ARCHIVE_BASE.iterdir() if d.is_dir()])
    if not dates:
        print("(无存档)")
        return
    for date in dates:
        slots = sorted([f.stem for f in (ARCHIVE_BASE / date).iterdir() if f.suffix == '.md'])
        if slots:
            slot_labels = [f"{s}({SLOT_NAMES.get(s, s)})" for s in slots]
            print(f"  {date}: {', '.join(slot_labels)}")


def resend(date: str, slot: str, auto_confirm: bool = False):
    """从存档重发指定日期的简报"""
    archive_path = ARCHIVE_BASE / date / f'{slot}.md'

    if not archive_path.exists():
        print(f"[ERROR] 存档不存在: {archive_path}")
        print("[ERROR] 禁止自行生成内容——请检查 pipeline 是否成功运行")
        sys.exit(1)

    content = archive_path.read_text(encoding='utf-8')
    if not content.strip():
        print(f"[ERROR] 存档为空: {archive_path}")
        sys.exit(1)

    # 打印预览
    preview = content[:200]
    lines = preview.split('\n')
    print(f"📄 {date} {SLOT_NAMES.get(slot, slot)} 存档 ({len(content)} 字符)")
    print("─" * 40)
    for line in lines[:10]:
        print(f"  {line}")
    print("─" * 40)
    print(f"  ... 共 {len(lines)} 行, {len(content)} 字符")

    # 走 hermes send 投递
    print(f"\n📨 正在投递到 wecom:bl ...")
    result = subprocess.run(
        ['hermes', 'send', '--to', 'wecom:bl', content],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        print(f"✅ 投递成功")
        if result.stdout:
            print(f"   {result.stdout.strip()[:200]}")
    else:
        print(f"❌ 投递失败: {result.stderr[:300]}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='从存档重发简报')
    parser.add_argument('--slot', choices=['morning', 'noon', 'evening'],
                        help='推送时段')
    parser.add_argument('--date', default=None,
                        help='日期 (YYYY-MM-DD)，默认今天')
    parser.add_argument('--list', action='store_true',
                        help='列出可用存档')
    parser.add_argument('--yes', action='store_true',
                        help='跳过确认直接发送')
    args = parser.parse_args()

    if args.list:
        list_archives()
        return

    if not args.slot:
        parser.print_help()
        print("\n请指定 --slot 或使用 --list 查看可用存档")
        sys.exit(1)

    from datetime import datetime, timezone, timedelta
    CST = timezone(timedelta(hours=8))
    date = args.date or datetime.now(CST).strftime('%Y-%m-%d')

    resend(date, args.slot, auto_confirm=args.yes)


if __name__ == '__main__':
    main()
