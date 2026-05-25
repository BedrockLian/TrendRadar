#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# TrendRadar 一键安装与迁移脚本 v1.0
# 用法: curl -sSL <raw-url> | bash  或  bash one-key-setup.sh
# ═══════════════════════════════════════════════════════════════
set -e

APP_NAME="TrendRadar"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TRENDRADAR_HOME="${TRENDRADAR_HOME:-$HERMES_HOME/trendradar}"
PYTHON_TARGET="${PYTHON:-/usr/local/bin/python3.14t}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 $APP_NAME 一键部署开始..."
echo "   Hermes 目录: $HERMES_HOME"
echo "   TrendRadar:  $TRENDRADAR_HOME"
echo "   Python:      $PYTHON_TARGET"

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
mkdir -p "$TRENDRADAR_HOME"/{data,cache,config,output}
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

# sources.json
if [ ! -f "$TRENDRADAR_HOME/data/sources.json" ]; then
    if [ -f "$SCRIPT_DIR/config/sources.json" ]; then
        cp "$SCRIPT_DIR/config/sources.json" "$TRENDRADAR_HOME/data/sources.json"
        echo "   ✅ sources.json 已从仓库复制"
    else
        echo "   ⚠️  请手动配置 $TRENDRADAR_HOME/data/sources.json"
    fi
fi

# timeline.yaml
if [ ! -f "$TRENDRADAR_HOME/config/timeline.yaml" ]; then
    if [ -f "$SCRIPT_DIR/config/timeline.yaml" ]; then
        cp "$SCRIPT_DIR/config/timeline.yaml" "$TRENDRADAR_HOME/config/timeline.yaml"
    else
        cat > "$TRENDRADAR_HOME/config/timeline.yaml" << 'YAML'
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
if [ ! -f "$TRENDRADAR_HOME/config/ai_interests.yaml" ]; then
    cat > "$TRENDRADAR_HOME/config/ai_interests.yaml" << 'YAML'
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
if [ ! -f "$TRENDRADAR_HOME/data/source_health.json" ]; then
    echo '{"version": 1, "updated_at": "", "sources": {}}' > "$TRENDRADAR_HOME/data/source_health.json"
    echo "   ✅ source_health.json 已初始化"
fi

# ── 5. 数据库迁移 ───────────────────────────────────────────
echo "🗄️  数据库迁移..."

DB_PATH="$TRENDRADAR_HOME/data/fingerprints.db"
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$HERMES_HOME"
export PYTHON_GIL=0

if [ -f "$SCRIPT_DIR/migrations/runner.py" ]; then
    "$PYTHON_TARGET" -c "
import sys; sys.path.insert(0, '$HERMES_HOME')
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
export TRENDRADAR_HOME="$HOME/.hermes/trendradar"
export PYTHONPATH="$HOME/.hermes${PYTHONPATH:+:$PYTHONPATH}"
export PYTHON="/usr/local/bin/python3.14t"
export PYTHON_GIL=0
EOF
    echo "   ✅ 环境变量已写入 $SHELL_RC"
fi

# ── 7. 验证 ─────────────────────────────────────────────────
echo ""
echo "✅ $APP_NAME 部署完成！"
echo ""
echo "验证命令:"
echo "  cd $SCRIPT_DIR"
echo "  PYTHONPATH=$HERMES_HOME $PYTHON_TARGET scripts/push_slot_detect.py"
echo "  PYTHONPATH=$HERMES_HOME $PYTHON_TARGET scripts/pipeline_orchestrator.py --list-steps"
echo "  PYTHONPATH=$HERMES_HOME $PYTHON_TARGET scripts/pipeline_orchestrator.py --check-version"
echo ""
echo "手动运行一次推送:"
echo "  PYTHONPATH=$HERMES_HOME PYTHON_GIL=0 $PYTHON_TARGET scripts/pipeline_orchestrator.py"
