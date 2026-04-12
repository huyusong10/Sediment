#!/usr/bin/env bash
# install-client.sh — Sediment 客户端一键安装脚本
# 检测 MCP 宿主程序 → 自动写入配置 → 可选注册 Skills
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
step "Sediment — 客户端配置"
echo "  自动配置 MCP 宿主程序连接 Sediment 服务"
echo ""

# ──────────────────────────────────────────────────────────────────────
# 1. Server URL
# ──────────────────────────────────────────────────────────────────────
step "服务端地址"
DEFAULT_URL="http://localhost:8000/sediment/"
echo -n "  Sediment 服务地址 [默认: $DEFAULT_URL]: "
read -r URL_INPUT
SERVER_URL="${URL_INPUT:-$DEFAULT_URL}"

# Validate URL format (basic check)
if [[ ! "$SERVER_URL" =~ ^https?:// ]]; then
    error "URL 必须以 http:// 或 https:// 开头"
    exit 1
fi
ok "服务端地址: $SERVER_URL"

# ──────────────────────────────────────────────────────────────────────
# 2. Detect MCP hosts
# ──────────────────────────────────────────────────────────────────────
step "检测 MCP 宿主程序"

HOSTS=()
HOST_LABELS=()

# Claude Code
CLAUDE_CODE_DIR="$HOME/.claude"
if [[ -d "$CLAUDE_CODE_DIR" ]]; then
    HOSTS+=("claude_code")
    HOST_LABELS+=("Claude Code")
    ok "检测到 Claude Code"
else
    info "未检测到 Claude Code"
fi

# Claude Desktop
CLAUDE_DESKTOP_CONFIG=""
if [[ "$OSTYPE" == darwin* ]]; then
    CLAUDE_DESKTOP_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
elif [[ "$OSTYPE" == linux-gnu* ]]; then
    CLAUDE_DESKTOP_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
fi

if [[ -n "$CLAUDE_DESKTOP_CONFIG" ]]; then
    # Check if Claude Desktop is installed
    CLAUDE_DESKTOP_INSTALLED=false
    if [[ "$OSTYPE" == darwin* ]] && [[ -d "/Applications/Claude.app" ]]; then
        CLAUDE_DESKTOP_INSTALLED=true
    elif [[ "$OSTYPE" == linux-gnu* ]] && command -v claude &>/dev/null; then
        CLAUDE_DESKTOP_INSTALLED=true
    fi

    if $CLAUDE_DESKTOP_INSTALLED || [[ -f "$CLAUDE_DESKTOP_CONFIG" ]]; then
        HOSTS+=("claude_desktop")
        HOST_LABELS+=("Claude Desktop")
        ok "检测到 Claude Desktop"
    else
        info "未检测到 Claude Desktop"
    fi
fi

if [[ ${#HOSTS[@]} -eq 0 ]]; then
    warn "未检测到任何 MCP 宿主程序"
    echo ""
    echo "  请先安装以下程序之一："
    echo "  - Claude Code: https://docs.anthropic.com/en/docs/claude-code/overview"
    echo "  - Claude Desktop: https://claude.ai/download"
    echo ""
    echo "  你也可以手动配置，在宿主程序的 MCP 配置中添加："
    echo "  {"
    echo '    "mcpServers": {'
    echo '      "sediment": {'
    echo "        \"url\": \"$SERVER_URL\""
    echo "      }"
    echo "    }"
    echo "  }"
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────
# 3. Host selection
# ──────────────────────────────────────────────────────────────────────
echo ""
echo "  选择要配置的宿主程序（输入编号，多个用逗号分隔）："
for i in "${!HOSTS[@]}"; do
    echo "  $((i+1))) ${HOST_LABELS[$i]}"
done
echo ""
echo -n "  选择 [默认全选]: "
read -r SELECTION
SELECTION="${SELECTION:-all}"

SELECTED_HOSTS=()
if [[ "$SELECTION" == "all" || -z "$SELECTION" ]]; then
    SELECTED_HOSTS=("${HOSTS[@]}")
else
    IFS=',' read -ra INDICES <<< "$SELECTION"
    for idx in "${INDICES[@]}"; do
        idx="$(echo "$idx" | tr -d ' ')"
        if (( idx >= 1 && idx <= ${#HOSTS[@]} )); then
            SELECTED_HOSTS+=("${HOSTS[$((idx-1))]}")
        else
            warn "无效编号: $idx"
        fi
    done
fi

if [[ ${#SELECTED_HOSTS[@]} -eq 0 ]]; then
    error "未选择任何宿主程序"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# 4. Configure hosts
# ──────────────────────────────────────────────────────────────────────
step "配置宿主程序"

# Helper: merge JSON using Python (avoids jq dependency)
merge_json_config() {
    local config_file="$1"
    local host_name="$2"
    local server_url="$3"

    python3 -c "
import json, os, sys

config_file = sys.argv[1]
host_name = sys.argv[2]
server_url = sys.argv[3]

# Read existing config or create empty
if os.path.exists(config_file):
    with open(config_file, 'r') as f:
        content = f.read().strip()
        if content:
            config = json.loads(content)
        else:
            config = {}
else:
    config = {}

# Ensure mcpServers key
if 'mcpServers' not in config:
    config['mcpServers'] = {}

# Check if sediment already configured
existing = config['mcpServers'].get(host_name)
if existing:
    print(f'EXISTING:{json.dumps(existing)}')
else:
    existing = None

# Add/update sediment config
config['mcpServers'][host_name] = {
    'url': server_url
}

# Write back
os.makedirs(os.path.dirname(config_file) if os.path.dirname(config_file) else '.', exist_ok=True)
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

if existing:
    print(f'UPDATED:{json.dumps(existing)}')
else:
    print('ADDED')
" "$config_file" "$host_name" "$server_url"
}

CONFIGURE_ERRORS=0

for host in "${SELECTED_HOSTS[@]}"; do
    echo ""
    case "$host" in
        claude_code)
            CONFIG_FILE="$HOME/.claude/settings.json"
            info "配置 Claude Code: $CONFIG_FILE"

            RESULT="$(merge_json_config "$CONFIG_FILE" "sediment" "$SERVER_URL")"

            case "$RESULT" in
                ADDED*)
                    ok "已添加 sediment MCP 配置"
                    ;;
                UPDATED*)
                    ok "已更新已有 sediment MCP 配置"
                    ;;
                EXISTING*)
                    warn "已有配置，已更新为新的地址"
                    ;;
            esac
            ;;

        claude_desktop)
            info "配置 Claude Desktop: $CLAUDE_DESKTOP_CONFIG"

            RESULT="$(merge_json_config "$CLAUDE_DESKTOP_CONFIG" "sediment" "$SERVER_URL")"

            case "$RESULT" in
                ADDED*)
                    ok "已添加 sediment MCP 配置"
                    ;;
                UPDATED*)
                    ok "已更新已有 sediment MCP 配置"
                    ;;
                EXISTING*)
                    warn "已有配置，已更新为新的地址"
                    ;;
            esac
            ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────
# 5. Skills registration (optional)
# ──────────────────────────────────────────────────────────────────────
step "注册 Skills（可选）"

SKILLS_DIR="$SCRIPT_DIR/skills"
CLAUDE_CODE_SKILLS_DIR="$HOME/.claude/skills"

list_skill_dirs() {
    local root="$1"
    find "$root" -mindepth 1 -maxdepth 1 -type d | while read -r skill_dir; do
        if [[ -f "$skill_dir/SKILL.md" ]]; then
            echo "$skill_dir"
        fi
    done | sort
}

if [[ -d "$SKILLS_DIR" ]]; then
    # Check if Claude Code is among selected hosts
    HAS_CLAUDE_CODE=false
    for host in "${SELECTED_HOSTS[@]}"; do
        if [[ "$host" == "claude_code" ]]; then
            HAS_CLAUDE_CODE=true
            break
        fi
    done

    if $HAS_CLAUDE_CODE; then
        mapfile -t SKILL_DIRS < <(list_skill_dirs "$SKILLS_DIR")

        if [[ ${#SKILL_DIRS[@]} -eq 0 ]]; then
            warn "skills/ 目录存在，但未找到任何标准 Skill 目录（缺少 SKILL.md）"
        else
            echo "  检测到以下 Skill 目录："
            for skill_dir in "${SKILL_DIRS[@]}"; do
                echo "    - $(basename "$skill_dir")/"
            done
            echo ""
            echo "  是否注册到 Claude Code？（symlink 目录到 ~/.claude/skills/）"
            echo -n "  注册 Skills？[Y/n]: "
            read -r SKILLS_INPUT
            SKILLS_INPUT="${SKILLS_INPUT:-y}"

            if [[ "$SKILLS_INPUT" =~ ^[Yy]$ ]] || [[ -z "$SKILLS_INPUT" ]]; then
                mkdir -p "$CLAUDE_CODE_SKILLS_DIR"

                SKILL_LINK_COUNT=0
                for skill_dir in "${SKILL_DIRS[@]}"; do
                    BASENAME="$(basename "$skill_dir")"
                    LINK_NAME="$CLAUDE_CODE_SKILLS_DIR/$BASENAME"

                    if [[ -L "$LINK_NAME" ]]; then
                        rm "$LINK_NAME"
                    elif [[ -e "$LINK_NAME" ]]; then
                        warn "$BASENAME 已存在（非 symlink），跳过"
                        continue
                    fi

                    ln -s "$skill_dir" "$LINK_NAME"
                    SKILL_LINK_COUNT=$((SKILL_LINK_COUNT + 1))
                    ok "已注册: $BASENAME"
                done
                ok "共注册 $SKILL_LINK_COUNT 个 Skills"
            else
                info "跳过 Skills 注册"
                echo "  如需手动注册，运行："
                echo "    ln -s $SKILLS_DIR/<skill-dir> $CLAUDE_CODE_SKILLS_DIR/"
            fi
        fi
    fi
else
    warn "未找到 skills/ 目录"
fi

# ──────────────────────────────────────────────────────────────────────
# 6. Summary
# ──────────────────────────────────────────────────────────────────────
step "配置完成"
echo ""
echo "  ${BOLD}已配置:${NC}"
for host in "${SELECTED_HOSTS[@]}"; do
    case "$host" in
        claude_code)    echo "  - Claude Code ($HOME/.claude/settings.json)" ;;
        claude_desktop) echo "  - Claude Desktop ($CLAUDE_DESKTOP_CONFIG)" ;;
    esac
done
echo ""
echo "  ${BOLD}服务地址:${NC} $SERVER_URL"
echo ""
echo "  下一步："
echo "  1. 重启宿主程序"
echo "  2. 验证 MCP 连接："
echo "     - Claude Code: 运行 /mcp 查看 sediment 状态"
echo "     - Claude Desktop: 查看 Developer 菜单中的 MCP 状态"
echo ""
echo "  如果服务未运行，请先执行服务端安装："
echo "    ./setup.sh"
echo ""
