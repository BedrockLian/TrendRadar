#!/usr/bin/env python3
"""存储管理层 — 统一的文件读写抽象 + 数据库接入（WAL 强制）。

所有模块通过 Storage 接入 fingerprints.db，确保一致的 PRAGMA 配置：
- journal_mode=WAL（支持高并发读写）
- synchronous=NORMAL（平衡安全与性能）
- busy_timeout=5000（5秒等待而非立即 SQLITE_BUSY）

当前状态：✅ API 就绪，record_fingerprints.py 已接入 Storage。
"""

import json, sqlite3, time, threading
from pathlib import Path
from typing import Any, Union, Optional


class Storage:
    """统一的文件 + 数据库存储抽象。

    Usage:
        store = Storage("/path/to/data")
        store.write_json("curated_noon.json", data)
        conn = store.db("fingerprints.db")
    """

    def __init__(self, base_dir: Union[str, Path]):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._db_connections: dict[str, sqlite3.Connection] = {}
        self._db_lock = threading.Lock()

    def _r(self, path):
        p = Path(path)
        return p if p.is_absolute() else self.base_dir / p

    # ── File I/O ────────────────────────────────────────────

    def read_json(self, path, default=None):
        p = self._r(path)
        if not p.exists(): return default
        try: return json.loads(p.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError): return default

    def write_json(self, path, data, **kw):
        from trendradar.scripts.settings import atomic_write_json
        p = self._r(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(p, data, **kw)

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

    def move(self, src: str, dst: str):
        """原子移动/重命名文件。跨文件系统时退化为 copy+delete。"""
        s = self._r(src); d = self._r(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.move(str(s), str(d))

    def rename(self, old: str, new: str):
        """重命名文件（同 move）。"""
        self.move(old, new)

    def delete(self, path: str) -> bool:
        """删除文件。返回是否实际删除了文件。"""
        p = self._r(path)
        if p.exists():
            p.unlink()
            return True
        return False

    # ── Database ─────────────────────────────────────────────

    def db(self, filename: str, row_factory: Optional[type] = None) -> sqlite3.Connection:
        """打开（或复用）数据库连接，强制启用 WAL 模式。

        Args:
            filename: 数据库文件名（相对于 base_dir）或绝对路径
            row_factory: 可选的行工厂（如 sqlite3.Row）

        Returns:
            sqlite3.Connection with WAL + NORMAL sync + 5s busy_timeout
        """
        db_path = str(self._r(filename))

        with self._db_lock:
            if db_path in self._db_connections:
                conn = self._db_connections[db_path]
                try:
                    conn.execute("SELECT 1")
                    if row_factory is not None:
                        conn.row_factory = row_factory
                    return conn
                except sqlite3.ProgrammingError:
                    # Connection was closed — reopen
                    del self._db_connections[db_path]

            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA cache_size=-8000")       # 8MB
            conn.execute("PRAGMA foreign_keys=ON")

            if row_factory is not None:
                conn.row_factory = row_factory

            self._db_connections[db_path] = conn
            return conn

    def vacuum(self, filename: str):
        """VACUUM 数据库，回收 delete/update 产生的碎片空间。
        
        建议在低峰时段（如每周维护窗口）调用。
        """
        conn = self.db(filename)
        conn.execute("VACUUM")
        # VACUUM 会重建数据库文件，需要重建连接
        self.close_db(filename)

    def checkpoint_db(self, filename: str):
        """将 WAL 内容合并回主 DB 文件 (TRUNCATE mode)。

        定期调用防止 WAL 文件无限增长。建议每 10 次写入后调用。
        """
        conn = self.db(filename)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def close_db(self, filename: Optional[str] = None):
        """关闭数据库连接。不传 filename 则关闭全部。"""
        with self._db_lock:
            if filename is None:
                for conn in self._db_connections.values():
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass
                self._db_connections.clear()
            else:
                db_path = str(self._r(filename))
                conn = self._db_connections.pop(db_path, None)
                if conn:
                    try:
                        conn.close()
                    except sqlite3.Error:
                        pass

    # ── Path helpers ─────────────────────────────────────────

    def data_path(self, fn): return self._r(f'data/{fn}')
    def cache_path(self, fn): return self._r(f'cache/{fn}')
    def output_path(self, fn): return self._r(f'output/{fn}')
