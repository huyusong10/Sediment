#!/usr/bin/env bash
# setup.sh — Sediment 服务端一键安装脚本
# 检测依赖 → 初始化知识库 → 安装 Python 依赖 → 启动 MCP 服务
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────
# Colours & helpers
# ──────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; }
step()    { echo -e "\n${BOLD}── $* ──${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ──────────────────────────────────────────────────────────────────────
# Banner
# ──────────────────────────────────────────────────────────────────────
step "Sediment — 隐性知识提取系统"
echo "  MCP Server 一键安装 & 启动"
echo ""

# ──────────────────────────────────────────────────────────────────────
# 1. OS detection
# ──────────────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == darwin* ]]; then
    OS="macos"
    info "检测到 macOS"
elif [[ "$OSTYPE" == linux-gnu* ]]; then
    OS="linux"
    info "检测到 Linux"
else
    warn "未识别的 OS: $OSTYPE — 继续尝试安装"
    OS="unknown"
fi

# ──────────────────────────────────────────────────────────────────────
# 2. Python 3.11+
# ──────────────────────────────────────────────────────────────────────
step "检查 Python 3.11+"
if command -v python3 &>/dev/null; then
    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    PY_MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
    PY_MINOR="$(echo "$PY_VER" | cut -d. -f2)"
    if (( PY_MAJOR >= 3 && PY_MINOR >= 11 )); then
        ok "Python $PY_VER 已安装"
    else
        error "需要 Python 3.11+，当前版本 $PY_VER"
        echo "  请先升级 Python：https://www.python.org/downloads/"
        echo "  macOS:  brew install python@3.11"
        echo "  Linux: sudo apt install python3.11"
        exit 1
    fi
else
    error "未找到 python3，请先安装 Python 3.11+"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# 3. uv package manager
# ──────────────────────────────────────────────────────────────────────
step "检查 uv 包管理器"
if command -v uv &>/dev/null; then
    ok "uv 已安装: $(uv --version)"
else
    warn "uv 未安装，正在自动安装..."
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        # Add uv to PATH for the current session
        UV_BIN="$HOME/.cargo/bin/uv"
        if [[ ! -x "$UV_BIN" ]]; then
            UV_BIN="$HOME/.local/bin/uv"
        fi
        if [[ -x "$UV_BIN" ]]; then
            export PATH="$(dirname "$UV_BIN"):$PATH"
        fi
        if command -v uv &>/dev/null; then
            ok "uv 安装成功: $(uv --version)"
        else
            error "uv 安装后不可用，请检查 PATH 或手动安装"
            exit 1
        fi
    else
        error "uv 安装失败"
        exit 1
    fi
fi

# ──────────────────────────────────────────────────────────────────────
# 4. Knowledge base initialization
# ──────────────────────────────────────────────────────────────────────
step "初始化知识库"

# Determine KB path
if [[ -n "${SEDIMENT_KB_PATH:-}" ]]; then
    KB_PATH="$SEDIMENT_KB_PATH"
    ok "使用环境变量 SEDIMENT_KB_PATH: $KB_PATH"
elif [[ -d "knowledge-base" ]]; then
    KB_PATH="$(pwd)/knowledge-base"
    ok "使用已有知识库: $KB_PATH"
else
    DEFAULT_KB="$HOME/.sediment/knowledge-base"
    echo -n "  知识库路径 [默认: $DEFAULT_KB]: "
    read -r KB_INPUT
    KB_PATH="${KB_INPUT:-$DEFAULT_KB}"
fi

# Create directory structure if missing
for subdir in entries placeholders; do
    mkdir -p "$KB_PATH/$subdir"
done

ok "知识库就绪: $KB_PATH"

# ──────────────────────────────────────────────────────────────────────
# 5. Install Python dependencies
# ──────────────────────────────────────────────────────────────────────
step "安装 Python 依赖"
if [[ -f "uv.lock" ]]; then
    info "使用锁定文件安装依赖 (uv sync --frozen)..."
    uv sync --frozen
else
    info "无锁定文件，使用 uv sync..."
    uv sync
fi
ok "依赖安装完成"

# ──────────────────────────────────────────────────────────────────────
# 6. Validate built-in skills
# ──────────────────────────────────────────────────────────────────────
step "检查内置 Skills"

REQUIRED_SKILLS=(
    "skills/ingest/SKILL.md"
    "skills/tidy/SKILL.md"
    "skills/explore/SKILL.md"
    "skills/health/SKILL.md"
)

for skill_file in "${REQUIRED_SKILLS[@]}"; do
    if [[ ! -f "$skill_file" ]]; then
        error "缺少内置 skill 文件: $skill_file"
        exit 1
    fi
done

ok "内置 skills 完整"

# ──────────────────────────────────────────────────────────────────────
# 7. .env configuration
# ──────────────────────────────────────────────────────────────────────
step "生成配置"

ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
    warn ".env 已存在，将保留已有值"
    echo "  修改配置请编辑 $ENV_FILE"
else
    cat > "$ENV_FILE" <<ENVEOF
# Sediment MCP Server 环境变量
SEDIMENT_KB_PATH=${KB_PATH}
SEDIMENT_HOST=0.0.0.0
SEDIMENT_PORT=8000
SEDIMENT_SSE_PATH=/sediment/
SEDIMENT_CLI=claude
ENVEOF
    ok "已创建 .env 文件"
fi

# Export for the current session
export SEDIMENT_KB_PATH="$KB_PATH"

# ──────────────────────────────────────────────────────────────────────
# 8. Start server
# ──────────────────────────────────────────────────────────────────────
step "启动服务"
echo "  选择启动方式："
echo "  1) 前台运行 (默认，Ctrl+C 停止)"
if [[ "$OS" == "linux" ]]; then
    echo "  2) 后台运行 (nohup)"
    echo "  3) 注册 systemd 服务"
elif [[ "$OS" == "macos" ]]; then
    echo "  2) 后台运行 (nohup)"
fi
echo ""
echo -n "  选择 [默认 1]: "
read -r MODE_INPUT
MODE_INPUT="${MODE_INPUT:-1}"

SERVER_PID=""

start_foreground() {
    info "启动 Sediment MCP Server (前台)..."
    echo ""
    info "服务地址: http://0.0.0.0:8000"
    info "SSE 端点: http://0.0.0.0:8000/sediment/"
    echo ""
    info "按 Ctrl+C 停止服务"
    echo "配置客户端请运行: ./install-client.sh"
    echo ""
    SEDIMENT_KB_PATH="$KB_PATH" uv run python mcp_server/server.py
}

start_background() {
    info "启动 Sediment MCP Server (后台)..."
    nohup uv run python mcp_server/server.py > sediment-server.log 2>&1 &
    SERVER_PID=$!
    ok "服务已在后台启动 (PID: $SERVER_PID)"
    info "日志文件: $(pwd)/sediment-server.log"

    # Wait a moment and verify
    sleep 2
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        ok "服务运行中"
    else
        error "服务启动失败，查看日志: cat sediment-server.log"
        exit 1
    fi
}

register_systemd() {
    if [[ "$OS" != "linux" ]]; then
        error "systemd 仅支持 Linux"
        exit 1
    fi

    ABS_KB_PATH="$(cd "$KB_PATH" && pwd)"
    SERVICE_NAME="sediment-mcp"
    SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

    if [[ -f "$SERVICE_FILE" ]]; then
        warn "systemd 服务 $SERVICE_NAME 已存在"
        echo -n "  是否重新注册？[y/N]: "
        read -r OVERWRITE
        if [[ "$OVERWRITE" =~ ^[Yy] ]]; then
            sudo rm -f "$SERVICE_FILE"
        else
            warn "跳过注册"
            return
        fi
    fi

    sudo tee "$SERVICE_FILE" > /dev/null <<SVCEOF
[Unit]
Description=Sediment MCP Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
Environment=SEDIMENT_KB_PATH=${ABS_KB_PATH}
ExecStart=$(command -v uv) run python mcp_server/server.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
SVCEOF

    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl start "$SERVICE_NAME"
    ok "systemd 服务已注册并启动: $SERVICE_NAME"
    info "查看状态: sudo systemctl status $SERVICE_NAME"
    info "查看日志: sudo journalctl -u $SERVICE_NAME -f"
}

case "$MODE_INPUT" in
    1) start_foreground ;;
    2) start_background ;;
    3) register_systemd ;;
    *) error "无效选择: $MODE_INPUT"; exit 1 ;;
esac

# ──────────────────────────────────────────────────────────────────────
# 9. Verify & summary (only for background/systemd)
# ──────────────────────────────────────────────────────────────────────
if [[ -n "$SERVER_PID" || "$MODE_INPUT" == "3" ]]; then
    step "验证服务"
    sleep 1
    HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/sediment/ 2>/dev/null || echo '000')"
    if [[ "$HTTP_CODE" == "200" ]]; then
        ok "服务响应正常 (HTTP $HTTP_CODE)"
    else
        warn "服务返回 HTTP $HTTP_CODE（SSE 端点可能需要长连接，这通常是正常的）"
    fi

    step "安装完成"
    echo ""
    echo "  ${BOLD}服务地址:${NC} http://localhost:8000/sediment/"
    echo "  ${BOLD}知识库:${NC}   $KB_PATH"
    echo ""
    echo "  下一步：运行客户端安装脚本"
    echo "    ./install-client.sh"
    echo ""
    echo "  或在 Claude Code / Claude Desktop 的 MCP 配置中添加："
    echo "    {"
    echo '      "mcpServers": {'
    echo '        "sediment": {'
    echo '          "url": "http://localhost:8000/sediment/"'
    echo "        }"
    echo "      }"
    echo "    }"
    echo ""
fi
