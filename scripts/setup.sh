#!/usr/bin/env bash
# setup.sh — Sediment quick bootstrap for a local workspace instance
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; }
step()    { echo -e "\n${BOLD}── $* ──${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

run_sediment_in_target() {
    (
        cd "$TARGET_DIR"
        uv run --project "$REPO_ROOT" sediment "$@"
    )
}

step "Sediment Workspace Setup"
echo "  Create a local Sediment instance and optionally start the platform."

step "Check dependencies"
command -v python3 >/dev/null 2>&1 || {
    error "python3 is required."
    exit 1
}
command -v uv >/dev/null 2>&1 || {
    error "uv is required. Install it from https://docs.astral.sh/uv/."
    exit 1
}
ok "python3: $(python3 --version 2>/dev/null)"
ok "uv: $(uv --version)"

step "Choose workspace"
DEFAULT_TARGET="$PWD"
echo -n "  Workspace directory [default: $DEFAULT_TARGET]: "
read -r TARGET_INPUT
TARGET_DIR="${TARGET_INPUT:-$DEFAULT_TARGET}"
mkdir -p "$TARGET_DIR"
TARGET_DIR="$(cd "$TARGET_DIR" && pwd)"
ok "Workspace: $TARGET_DIR"

if [[ "$TARGET_DIR" == "$REPO_ROOT" ]]; then
    warn "You are initializing Sediment inside the source repository itself."
fi

CONFIG_PATH="$TARGET_DIR/config/sediment/config.yaml"

if [[ ! -f "$CONFIG_PATH" ]]; then
    step "Initialize instance"
    DEFAULT_INSTANCE="$(basename "$TARGET_DIR" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '-')"
    DEFAULT_INSTANCE="${DEFAULT_INSTANCE:-sediment-local}"
    DEFAULT_KNOWLEDGE="Sediment Knowledge Base"

    echo -n "  Instance name [default: $DEFAULT_INSTANCE]: "
    read -r INSTANCE_INPUT
    INSTANCE_NAME="${INSTANCE_INPUT:-$DEFAULT_INSTANCE}"

    echo -n "  Knowledge base title [default: $DEFAULT_KNOWLEDGE]: "
    read -r KNOWLEDGE_INPUT
    KNOWLEDGE_NAME="${KNOWLEDGE_INPUT:-$DEFAULT_KNOWLEDGE}"

    echo -n "  Agent backend [claude-code/codex/opencode, default: claude-code]: "
    read -r BACKEND_INPUT
    BACKEND="${BACKEND_INPUT:-claude-code}"

    run_sediment_in_target init \
        --instance-name "$INSTANCE_NAME" \
        --knowledge-name "$KNOWLEDGE_NAME" \
        --backend "$BACKEND"
    ok "Instance created."
else
    ok "Existing instance found: $CONFIG_PATH"
fi

step "Doctor"
run_sediment_in_target doctor

step "Start platform"
echo "  1) Foreground"
echo "  2) Background daemon"
echo -n "  Mode [default: 1]: "
read -r MODE_INPUT
MODE_INPUT="${MODE_INPUT:-1}"

case "$MODE_INPUT" in
    1)
        info "Starting in foreground..."
        echo "  Stop with Ctrl+C"
        run_sediment_in_target server run
        ;;
    2)
        info "Starting background daemon..."
        run_sediment_in_target server start
        run_sediment_in_target server status
        ;;
    *)
        error "Unknown mode: $MODE_INPUT"
        exit 1
        ;;
esac

echo ""
echo "Client helper: bash \"$REPO_ROOT/scripts/install-client.sh\""
