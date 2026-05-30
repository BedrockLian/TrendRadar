#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# TrendRadar 一键安装与迁移脚本 v2.0
# 用法: bash one-key-setup.sh
# ═══════════════════════════════════════════════════════════════
set -e

APP_NAME="TrendRadar"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
# 注意：TRENDRADAR_HOME 是运行时根路径（含 trendradar/ 包子目录）
TRENDRADAR_HOME="${TRENDRADAR_HOME:-$HERMES_HOME/trendradar}"
# 包路径（含 scripts/ config/ 等）
TRENDRADAR_PKG="$TRENDRADAR_HOME/trendradar"
PYTHON_TARGET="${PYTHON:-/usr/local/bin/python3.14t}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 $APP_NAME 一键部署开始..."
echo "   Hermes 目录:   $HERMES_HOME"
echo "   TrendRadar:    $TRENDRADAR_HOME"
echo "   包目录:        $TRENDRADAR_PKG"
echo "   Python:        $PYTHON_TARGET"

# ── 1. 环境预检 ─────────────────────────────────────────────
if [ ! -x "$PYTHON_TARGET" ]; then
    echo "❌ 未找到 $PYTHON_TARGET"
    echo "   请先安装 Python 3.14t free-threaded 版本。"
    echo "   参考: https://github.com/python/cpython"
    exit 1
fi

PY_VER=$("$PYTHON_TARGET" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "   Python 版本: $PY_VER"

if [ "$PY_VER" != "3.14" ]; then
    echo "⚠️  期望 Python 3.14，当前为 $PY_VER。部分功能（free-threading）可能不可用。"
fi

# ── 2. 目录初始化 ───────────────────────────────────────────
# 运行时数据在 TRENDRADAR_PKG/data/ 下
mkdir -p "$TRENDRADAR_PKG"/{data,cache,config}
mkdir -p "$HERMES_HOME"/{skills/trendradar,scripts}

echo "📁 目录已就绪"

# ── 3. Python 依赖 ─────────────────────────────────────────
echo "📦 安装 Python 依赖..."

REQ_FILE="$SCRIPT_DIR/requirements.txt"
if [ ! -f "$REQ_FILE" ]; then
    REQ_FILE="$TRENDRADAR_HOME/../requirements.txt"
fi

if [ -f "$REQ_FILE" ]; then
    "$PYTHON_TARGET" -m pip install --quiet --upgrade pip
    "$PYTHON_TARGET" -m pip install --quiet -r "$REQ_FILE"
else
    echo "⚠️  未找到 requirements.txt，跳过依赖安装"
    echo "   请手动安装: pip install zstandard aiohttp feedparser pyyaml pyahocorasick"
fi

# ── 4. 配置模板 ─────────────────────────────────────────────
echo "⚙️  初始化配置..."

# sources.json — 配置文件，放 config/ 下
if [ ! -f "$TRENDRADAR_PKG/config/sources.json" ]; then
    if [ -f "$SCRIPT_DIR/config/sources.json" ]; then
        cp "$SCRIPT_DIR/config/sources.json" "$TRENDRADAR_PKG/config/sources.json"
        echo "   ✅ sources.json 已从仓库复制到 config/"
    else
        # 也尝试 data/ 旧位置（迁移兼容）
        if [ -f "$SCRIPT_DIR/data/sources.json" ]; then
            cp "$SCRIPT_DIR/data/sources.json" "$TRENDRADAR_PKG/config/sources.json"
            echo "   ✅ sources.json 已从 data/ 迁移到 config/"
        else
            echo "   ⚠️  请手动配置 $TRENDRADAR_PKG/config/sources.json"
        fi
    fi
fi

# timeline.yaml
if [ ! -f "$TRENDRADAR_PKG/config/timeline.yaml" ]; then
    if [ -f "$SCRIPT_DIR/config/timeline.yaml" ]; then
        cp "$SCRIPT_DIR/config/timeline.yaml" "$TRENDRADAR_PKG/config/timeline.yaml"
    else
        cat > "$TRENDRADAR_PKG/config/timeline.yaml" << 'YAML'
slots:
  morning:
    time: "09:00"
    limit: 30
    dedup: false
    display: "🌅 早报"
  noon:
    time: "12:00"
    limit: 30
    dedup: true
    display: "☀️ 午报"
  evening:
    time: "21:00"
    limit: 20
    dedup: true
    display: "🌙 晚报"
YAML
    fi
    echo "   ✅ timeline.yaml 已创建"
fi

# ai_interests.yaml
if [ ! -f "$TRENDRADAR_PKG/config/ai_interests.yaml" ]; then
    cat > "$TRENDRADAR_PKG/config/ai_interests.yaml" << 'YAML'
positive:
  - AI 人工智能
  - 芯片 半导体
  - 新能源 电动车
  - 就业 失业率
  - 房价 房地产
  - 人工智能
  - GPU
  - LLM
negative:
  - 加密货币
  - NFT
YAML
    echo "   ✅ ai_interests.yaml 已创建"
fi

# source_health.json
if [ ! -f "$TRENDRADAR_PKG/data/source_health.json" ]; then
    echo '{"version": 1, "updated_at": "", "sources": {}}' > "$TRENDRADAR_PKG/data/source_health.json"
    echo "   ✅ source_health.json 已初始化"
fi

# ── 5. 数据库迁移 ───────────────────────────────────────────
echo "🗄️  数据库迁移..."

DB_PATH="$TRENDRADAR_PKG/data/fingerprints.db"
# PYTHONPATH 指向 TRENDRADAR_HOME（包父目录），让 import trendradar 可用
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$TRENDRADAR_HOME"
# ⚠️ Python 3.14t 不支持 PYTHON_GIL=0（子进程崩溃），必须 unset
unset PYTHON_GIL

if [ -f "$SCRIPT_DIR/migrations/runner.py" ]; then
    "$PYTHON_TARGET" -c "
import sys; sys.path.insert(0, '$TRENDRADAR_HOME')
from trendradar.migrations.runner import migrate
ver = migrate('$DB_PATH')
print(f'DB schema v{ver}')
" 2>/dev/null && echo "   ✅ 数据库迁移完成" || echo "   ⚠️  数据库迁移跳过（首次运行正常）"
fi

# ── 6. 环境变量持久化 ───────────────────────────────────────
SHELL_RC=""
for rc in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$rc" ]; then SHELL_RC="$rc"; break; fi
done

if [ -n "$SHELL_RC" ] && ! grep -q "TRENDRADAR_HOME" "$SHELL_RC" 2>/dev/null; then
    cat >> "$SHELL_RC" << 'EOF'

# ── TrendRadar ──────────────────────────────────────────
# TRENDRADAR_HOME 是 TrendRadar 的根目录，含 trendradar/ 包子目录
export TRENDRADAR_HOME="$HOME/.hermes/trendradar"
# PYTHONPATH 指向包父目录，使 import trendradar 可工作
export PYTHONPATH="$HOME/.hermes/trendradar${PYTHONPATH:+:$PYTHONPATH}"
export PYTHON="/usr/local/bin/python3.14t"
# ⚠️ PYTHON_GIL=0 会导致 Python 3.14t 子进程崩溃（config_read_gil: not supported）
# 不要设置 PYTHON_GIL，让脚本在需要时自行 unset
# 日文翻译模型（deepseek-chat 翻译日文必然返回原文）
export DEEPSEEK_MODEL=deepseek-v4-flash
EOF
    echo "   ✅ 环境变量已写入 $SHELL_RC"
fi

# ── 7. 验证 ─────────────────────────────────────────────────
echo ""
echo "✅ $APP_NAME 部署完成！"
echo ""
echo "验证命令（注意 PYTHONPATH 和 GIL）："
echo "  cd $TRENDRADAR_HOME"
echo "  PYTHONPATH=$TRENDRADAR_HOME PYTHON_GIL= $PYTHON_TARGET trendradar/scripts/push_slot_detect.py"
echo "  PYTHONPATH=$TRENDRADAR_HOME PYTHON_GIL= $PYTHON_TARGET trendradar/scripts/pipeline_orchestrator.py --list-steps"
echo ""
echo "手动运行一次推送:"
echo "  cd $TRENDRADAR_HOME"
echo "  DEEPSEEK_MODEL=deepseek-v4-flash TRENDRADAR_HOME=$TRENDRADAR_PKG \\"
echo "    PYTHONPATH=$TRENDRADAR_HOME PYTHON_GIL= \\"
echo "    $PYTHON_TARGET trendradar/scripts/pipeline_orchestrator.py --push-id noon"
echo ""
echo "补发存档:"
echo "  cd $TRENDRADAR_HOME"
echo "  TRENDRADAR_HOME=$TRENDRADAR_PKG PYTHONPATH=$TRENDRADAR_HOME PYTHON_GIL= \\"
echo "    $PYTHON_TARGET trendradar/scripts/archive_resend.py --date YYYY-MM-DD --slot noon"
