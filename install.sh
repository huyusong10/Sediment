#!/usr/bin/env bash
# install.sh — Sediment one-command installer for macOS/Linux
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERR]${NC}  $*" >&2; }
step()  { echo -e "\n${BOLD}── $* ──${NC}"; }

REPO_SLUG="${SEDIMENT_REPO:-huyusong10/Sediment}"
REF="${SEDIMENT_REF:-master}"
FORCE_INSTALL=1
KEEP_SOURCE=0
DOWNLOAD_ROOT="${TMPDIR:-/tmp}"

usage() {
  cat <<'EOF'
Sediment installer

Usage:
  bash install.sh [--repo owner/name] [--ref git-ref] [--no-force] [--keep-source]

Options:
  --repo         GitHub repository slug to install from (default: huyusong10/Sediment)
  --ref          Git ref, branch, or tag to install from (default: master)
  --no-force     Fail instead of replacing and reinstalling an existing Sediment CLI installation
  --keep-source  Keep the downloaded source tree in /tmp for debugging
  -h, --help     Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO_SLUG="${2:?missing value for --repo}"
      shift 2
      ;;
    --ref)
      REF="${2:?missing value for --ref}"
      shift 2
      ;;
    --force)
      FORCE_INSTALL=1
      shift
      ;;
    --no-force)
      FORCE_INSTALL=0
      shift
      ;;
    --keep-source)
      KEEP_SOURCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      error "Unknown argument: $1"
      usage
      exit 2
      ;;
  esac
done

need_cmd() {
  local name="$1"
  command -v "$name" >/dev/null 2>&1 || {
    error "Required command not found: $name"
    exit 1
  }
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    ok "uv: $(uv --version)"
    return
  fi

  step "Install uv"
  info "uv was not found. Installing it with the official installer."
  need_cmd curl
  sh -c "$(curl -fsSL https://astral.sh/uv/install.sh)"
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  hash -r

  if ! command -v uv >/dev/null 2>&1; then
    error "uv installation finished, but uv is still not on PATH."
    error "Open a new shell or add ~/.local/bin to PATH, then rerun this installer."
    exit 1
  fi
  ok "uv: $(uv --version)"
}

resolve_local_source() {
  local script_path script_dir
  script_path="${BASH_SOURCE[0]:-}"
  [[ -n "$script_path" ]] || return 1
  script_dir="$(cd "$(dirname "$script_path")" && pwd)"
  [[ -f "$script_dir/pyproject.toml" ]] || return 1
  [[ -d "$script_dir/src/sediment" ]] || return 1
  printf '%s\n' "$script_dir"
}

download_source() {
  need_cmd curl
  need_cmd tar
  local temp_root archive_url
  temp_root="$(mktemp -d "$DOWNLOAD_ROOT/sediment-install.XXXXXX")"
  archive_url="https://github.com/${REPO_SLUG}/archive/${REF}.tar.gz"
  info "Downloading Sediment from ${archive_url}"
  curl -fsSL "$archive_url" | tar -xzf - -C "$temp_root"
  find "$temp_root" -mindepth 1 -maxdepth 1 -type d | head -n 1
}

step "Sediment installer"
echo "  Install the Sediment CLI so you can create and manage local instances."

step "Check dependencies"
need_cmd bash
need_cmd python3
ok "python3: $(python3 --version 2>/dev/null)"
ensure_uv

step "Resolve source"
SOURCE_DIR=""
TEMP_SOURCE_ROOT=""
if SOURCE_DIR="$(resolve_local_source 2>/dev/null)"; then
  ok "Using local source tree: $SOURCE_DIR"
else
  SOURCE_DIR="$(download_source)"
  TEMP_SOURCE_ROOT="$(dirname "$SOURCE_DIR")"
  ok "Downloaded source tree: $SOURCE_DIR"
fi

step "Install Sediment CLI"
INSTALL_ARGS=(tool install --from "$SOURCE_DIR" sediment --compile-bytecode)
if [[ $FORCE_INSTALL -eq 1 ]]; then
  INSTALL_ARGS+=(--force --reinstall)
fi
if uv "${INSTALL_ARGS[@]}"; then
  if [[ $FORCE_INSTALL -eq 1 ]]; then
    ok "Sediment CLI installed or fully refreshed."
  else
    ok "Sediment CLI installed."
  fi
else
  if [[ $FORCE_INSTALL -eq 0 ]]; then
    error "Sediment installation failed without overwrite. Rerun without --no-force to replace and reinstall the existing CLI."
    exit 1
  else
    error "Sediment installation failed."
    exit 1
  fi
fi

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
hash -r

step "Finish"
if command -v sediment >/dev/null 2>&1; then
  ok "sediment: $(command -v sediment)"
else
  warn "Sediment was installed, but the shell cannot find it yet."
  warn "You may need to reopen your shell or add ~/.local/bin to PATH."
fi

echo ""
echo "Next:"
echo "- Run: sediment --help"
echo "- Create a workspace: mkdir my-sediment-workspace && cd my-sediment-workspace"
echo "- Initialize an instance: sediment init --instance-name ops-prod --knowledge-name \"Ops Knowledge Base\""

if [[ -n "$TEMP_SOURCE_ROOT" && $KEEP_SOURCE -eq 0 ]]; then
  rm -rf "$TEMP_SOURCE_ROOT"
fi

if [[ -n "$TEMP_SOURCE_ROOT" && $KEEP_SOURCE -eq 1 ]]; then
  info "Kept downloaded source at: $TEMP_SOURCE_ROOT"
fi
