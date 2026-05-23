#!/usr/bin/env python3
"""存储管理层 — 统一的文件读写抽象。
计划逐步迁移现有脚本到本工具类。
当前状态：✅ API 就绪，尚未集成到各脚本。"""

import json, sqlite3, time
from pathlib import Path
from typing import Any, Union

class Storage:
    def __init__(self, base_dir: Union[str, Path]):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _r(self, path):
        p = Path(path)
        return p if p.is_absolute() else self.base_dir / p

    def read_json(self, path, default=None):
        p = self._r(path)
        if not p.exists(): return default
        try: return json.loads(p.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError): return default

    def write_json(self, path, data, **kw):
        p = self._r(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, **kw), encoding='utf-8')

    def read_text(self, path, default=''):
        p = self._r(path)
        return p.read_text(encoding='utf-8') if p.exists() else default

    def write_text(self, path, content):
        p = self._r(path); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')

    def exists(self, path): return self._r(path).exists()

    def list_files(self, pattern='*'):
        return sorted(self.base_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    def remove_older_than(self, pattern, hours):
        now = time.time(); c = 0
        for f in self.base_dir.glob(pattern):
            if f.is_file() and (now - f.stat().st_mtime) > hours * 3600:
                f.unlink(); c += 1
        return c

    @staticmethod
    def db(path): return sqlite3.connect(str(path))

    def data_path(self, fn): return self._r(f'data/{fn}')
    def cache_path(self, fn): return self._r(f'cache/{fn}')
    def output_path(self, fn): return self._r(f'output/{fn}')
