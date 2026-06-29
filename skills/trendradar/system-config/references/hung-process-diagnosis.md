# 卡住进程诊断协议（faulthandler + SIGALRM 自动 dump）

适用场景：Python 进程看起来"挂死"——0% CPU、`Sl` 状态、无输出、无子线程。可能是：
- 单线程自递归锁（`Lock` 不可重入 → re-acquire 阻塞）
- GIL 切换死锁（free-threaded + GIL-unsafe C 扩展）
- 死循环/无限等待 I/O

普通 `kill -SIGUSR1` / `SIGABRT` 在 Python 3.12+ 可能**直接杀掉不 dump**（faulthandler 默认未启用）。**`-X faulthandler` 启动标志 + SIGABRT 才是可靠组合**。

## 1. 启动时启用 faulthandler（推荐）

```bash
python3 -X faulthandler -u script.py
```

`SIGABRT` 会触发 `faulthandler.dump_traceback_later()` 输出所有线程 stack 到 stderr，**SIGUSR1 在 3.12+ 行为不一致**（部分版本会静默杀掉）。如果想用 SIGUSR1，加显式 dump：

```bash
kill -SIGUSR1 <pid>  # 仅在 faulthandler 已 dump_traceback 注册时输出 stack
```

## 2. 启动后启用（脚本里加 faulthandler + 定时自 dump）

如果进程已经启动且卡死，把这段塞到脚本开头重启跑——15 秒后自动 dump stack 并退出。

```python
import faulthandler, signal, sys
faulthandler.enable()

def _dump_and_exit(sig, frame):
    faulthandler.dump_traceback()
    sys.exit(1)

signal.signal(signal.SIGALRM, _dump_and_exit)
signal.alarm(15)  # 15s 后自动触发
```

## 3. py-spy 备选（需 sudo 或 ptrace_scope=0）

```bash
# 检查 ptrace 限制
cat /proc/sys/kernel/yama/ptrace_scope  # 1 = 需同 uid 进程
# 临时放宽（WSL 需要 sudo，但 sudo 可能不可用）
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# dump 当前 stack
py-spy dump --pid <pid>
```

**WSL 限制**: ptrace_scope=1 时 py-spy 同 uid 进程能 attach，但 dump 时常需 CAP_SYS_PTRACE。**sudo 不通时优先用 faulthandler**。

## 4. /proc 调查（无 root 也能用）

```bash
# 当前 wchan（等待的内核资源）
cat /proc/<pid>/wchan
# 常见: futex_wait_queue (锁等待), do_wait (子进程), pipe_wait
ps -p <pid> -o stat,wchan

# 线程数
cat /proc/<pid>/status | grep -E "State|Threads|VmRSS"

# 打开的文件描述符（看是否 socket 死等）
ls -la /proc/<pid>/fd | grep -E "socket|pipe"
```

## 5. strace（看系统调用）

```bash
strace -p <pid> -e trace=read,write,connect -c
# 统计各 syscall 频率 → 知道在等啥
```

## 6. 解读 dump_traceback 输出

输出形如：
```
Current thread 0x... (most recent call first):
  File "/path/file.py", line N in <func>
  File "/path/file.py", line M in <func>
  ...
  File "/path/main.py", line X in <module>
```

**从底向上读**：`<module>` 入口 → 一连串调用 → 停在某个栈帧的某一行。该行就是卡死点。

## 案例：domain_metadata RLock 自递归死锁

症状：push_prepare 在 "读取 N 条 raw" 后卡 40s+，0% CPU，单线程无子进程。

dump 显示：
```
File "/.../domain_metadata.py", line 48 in _sources
File "/.../domain_metadata.py", line 121 in _foreign_sources
File "/.../classifier.py", line 15 in classify_items
```

读栈：`_foreign_sources` 在 `with _INIT_LOCK` 块内调 `_sources()` → `_sources()` 内部也 `with _INIT_LOCK` → 同一线程二次 acquire 同一把 `Lock()` 永久阻塞。

修复：`Lock` → `RLock`。

## 案例：pytest subprocess timeout 冒泡

症状：维护脚本标 cron error，看 log 显示 "delivered to wecom" 但 last_status=error。

根因：`subprocess.run(timeout=60)` 超时时抛 `subprocess.TimeoutExpired` 但**没 try/except 包裹** → 异常冒泡到 `__main__` → `sys.exit(1)` → cron 标 error。

修复：在调用处加 `try/except TimeoutExpired` 标记软失败，**不能让测试失败阻断主流程**（备份/清理/vacuum 已成功的部分不应被废弃）。

## 关键陷阱

- **`-X faulthandler` 启动标志比 `kill` 信号更可靠**——3.12+ 默认行为已变
- **`SIGUSR1` 在 3.14 可能直接杀进程不 dump**——优先 SIGABRT 或显式 `signal.signal(SIGALRM, dump)`
- **pkill -f 会杀自己**——别在后台 shell 里用 `pkill -f <my_script>` 调试
- **WSL `ptrace_scope=1`**——py-spy / strace 可能 Permission Denied，**默认走 faulthandler 路线**
- **child process 转 strace 看 hang 在哪个 syscall**——`strace -f -p <parent>` 跟踪 fork
