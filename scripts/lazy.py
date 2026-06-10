"""lazy.py — 线程安全的惰性初始化 (Sprint 2 P1-14)

从 common.py 拆出。替代手写双检查锁（5 处重复, P1-15）。
"""
import threading


class Lazy:
    """线程安全的惰性初始化（双检查锁）。

    用法:
        _config = Lazy(lambda: json.loads(Path('config.json').read_text()))
        config = _config.get()  # 首次调用时初始化, 后续直接返回缓存

    替代模式（5 处手写重复, P1-15）:
        global _CONFIG_VAL
        if _CONFIG_VAL is not None:
            return _CONFIG_VAL
        with _CONFIG_LOCK:
            if _CONFIG_VAL is not None:
                return _CONFIG_VAL
            _CONFIG_VAL = expensive_init()
            return _CONFIG_VAL
    """
    __slots__ = ('_factory', '_lock', '_value', '_initialized')

    def __init__(self, factory):
        self._factory = factory
        self._lock = threading.Lock()
        self._value = None
        self._initialized = False

    def get(self):
        if self._initialized:
            return self._value
        with self._lock:
            if self._initialized:
                return self._value
            self._value = self._factory()
            self._initialized = True
            return self._value

    def reset(self):
        """重置缓存（测试或热重载时用）"""
        with self._lock:
            self._value = None
            self._initialized = False
