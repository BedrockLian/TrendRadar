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

# TRENDRADAR_HOME / ARCHIVE_BASE SSOT (审计 P1-5, 2026-06-20):
# 路径解析统一从 paths.py 取（ENV 优先 + fail-fast 校验）
from trendradar.scripts.paths import TRENDRADAR_HOME, ARCHIVE_DIR as ARCHIVE_BASE

SLOT_NAMES = {'morning': '早报', 'noon': '午间速递', 'evening': '今日回顾'}


def _import_cst():
    from trendradar.scripts.common import CST
    return CST


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


def resend(date: str, slot: str, auto_confirm: bool = False, skip_delivered: bool = True):
    """从存档重发指定日期的简报（按 WeCom 分片逐条投递）

    skip_delivered=True 时，先查 push_log.json 的 run_id 是否已标 delivered_*.marker 水印；
    命中则跳过整次投递（防重复推送）。
    """
    archive_path = ARCHIVE_BASE / date / f'{slot}.md'

    if not archive_path.exists():
        print(f"[ERROR] 存档不存在: {archive_path}")
        print("[ERROR] 禁止自行生成内容——请检查 pipeline 是否成功运行")
        sys.exit(1)

    content = archive_path.read_text(encoding='utf-8')
    if not content.strip():
        print(f"[ERROR] 存档为空: {archive_path}")
        sys.exit(1)

    # ── 去重水印检查（防 cron 重复推送）──
    if skip_delivered:
        marker_dir = TRENDRADAR_HOME / 'data' / 'delivery_markers'
        if marker_dir.exists():
            for m in marker_dir.glob(f'delivered_*{slot}*.marker'):
                if date in m.name or str(TRENDRADAR_HOME / 'archive' / date) in m.read_text(errors='ignore'):
                    print(f"[SKIP] {date} {slot} 已投递（{m.name}），跳过")
                    return

    # 用 fragment_push 的分片逻辑切割
    from trendradar.scripts.fragment_push import split_fragments
    from trendradar.config.delivery import WECOM_FRAGMENT_SAFE_BYTES
    fragments = split_fragments(content)

    # 打印预览
    preview = content[:200]
    lines = preview.split('\n')
    total_bytes = len(content.encode('utf-8'))
    print(f"📄 {date} {SLOT_NAMES.get(slot, slot)} 存档")
    print(f"   总 {total_bytes} bytes, 分 {len(fragments)} 片")
    print("─" * 40)
    for line in lines[:10]:
        print(f"  {line}")
    print("─" * 40)
    for i, frag in enumerate(fragments):
        b = len(frag.encode('utf-8'))
        label = " ⚠️ 超限" if b > WECOM_FRAGMENT_SAFE_BYTES else ""
        print(f"  片{i+1}: {len(frag)} chars / {b} bytes{label}")

    # 确认
    if not auto_confirm:
        try:
            confirm = input("\n发送以上分片到 wecom:bl ? [Y/n] ").strip().lower()
            if confirm and confirm != 'y' and confirm != 'yes':
                print("已取消")
                return
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return

    # 逐片投递
    success_count = 0
    for i, frag in enumerate(fragments):
        print(f"\n📨 片{i+1}/{len(fragments)} 投递中 ...")
        result = subprocess.run(
            ['hermes', 'send', '--to', 'wecom:bl', frag],
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=30,
        )
        if result.returncode == 0:
            status = result.stdout.strip()[:120] if result.stdout else "ok"
            print(f"  ✅ {status}")
            success_count += 1
        else:
            print(f"  ❌ 投递失败: {result.stderr[:200]}")
            # 继续下一片，不阻断整次补发

    print(f"\n✅ 全部 {len(fragments)} 片投递完毕，成功 {success_count}")

    # 写水印（防 cron 二次推送）
    if success_count == len(fragments) and success_count > 0:
        from datetime import datetime
        CST = _import_cst()
        marker_dir = TRENDRADAR_HOME / 'data' / 'delivery_markers'
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / f'delivered_{date}_{slot}.marker'
        marker.write_text(f"archive={archive_path}\nfragments={success_count}\n"
                          f"delivered_at={datetime.now(CST).isoformat()}\n")
        print(f"  📌 水印已写: {marker.name}")


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

    from datetime import datetime
    CST = _import_cst()
    date = args.date or datetime.now(CST).strftime('%Y-%m-%d')

    resend(date, args.slot, auto_confirm=args.yes)


if __name__ == '__main__':
    main()
