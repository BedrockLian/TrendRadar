#!/usr/bin/env python3
"""sync_files.py — rsync替代,用 robocopy 做 Windows 上的 rsync风格 exclude。
调用: python sync_files.py [--mirror] <src> <dst> [excludes...]
excludes 中含 . 的视为文件 pattern (/XF),否则视为目录 (/XD)。"""
import os, sys, subprocess
def main():
 args = sys.argv[1:]
 if not args or args[0] in ("-h", "--help"):
  print(__doc__); return
 mirror = False
 if args and args[0] == "--mirror":
  mirror = True; args = args[1:]
 if len(args) <2:
  print("usage: sync_files.py [--mirror] <src> <dst> [excludes...]"); return
 src, dst = args[0], args[1]
 excludes = args[2:]
 cmd = ["robocopy", src, dst, "/MIR" if mirror else "/E", "/R:0", "/W:0", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS"]
 for ex in excludes:
  cmd += ["/XF", ex] if "." in ex else ["/XD", ex]
 r = subprocess.run(cmd, capture_output=True)
 rc = r.returncode
 if rc >=8:
  print("robocopy ERROR rc=", rc); print(r.stdout.decode("utf-8", "replace")[:2000]); sys.exit(1)
 else:
  print("robocopy ok rc=", rc, "src=", src, "dst=", dst)
main()