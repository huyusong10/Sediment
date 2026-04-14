# Sediment 内网离线安装指南（Windows / Linux）

> 适用场景：机器不能访问公网（例如无法访问 `pypi.org` / `github.com`），但可以访问企业内部的 PyPI / npm / Git 仓库。

在内网环境中，若未显式指定索引，`uv tool install --from . sediment ...` 可能仍会尝试访问默认索引 `https://pypi.org/simple`，从而导致安装失败。

---

## 0. 先决条件

- Python 3.11+
- 已能从企业内网源安装 `uv`
- 已拿到 Sediment 源码（例如通过内网 Git 镜像下载 zip 或 clone）
- 可访问企业内部 PyPI 源（必须包含 Sediment 的依赖包）

Sediment 当前 Python 依赖见 `pyproject.toml`：

- `mcp`
- `pyyaml`
- `python-docx`
- `python-pptx`
- `starlette`
- `uvicorn`

如果你的内网源里缺任何一个，安装都会失败。

---

## 1) 推荐方案：强制 uv 只走内网 PyPI

> 这是最直接、改动最小的方案。

以下示例把内网源写成：`https://<your-internal-pypi>/simple`，请替换成你的实际地址。

### Windows PowerShell

```powershell
$env:UV_DEFAULT_INDEX = "https://<your-internal-pypi>/simple"
Remove-Item Env:UV_INDEX -ErrorAction SilentlyContinue
Remove-Item Env:UV_EXTRA_INDEX_URL -ErrorAction SilentlyContinue

cd C:\path\to\Sediment
uv tool install --from . sediment --force --reinstall --compile-bytecode --index-strategy first-index
```

### Linux / macOS Bash

```bash
export UV_DEFAULT_INDEX="https://<your-internal-pypi>/simple"
unset UV_INDEX
unset UV_EXTRA_INDEX_URL

cd /path/to/Sediment
uv tool install --from . sediment --force --reinstall --compile-bytecode --index-strategy first-index
```

安装后验证：

```bash
uv tool list
uv tool dir --bin
sediment --help
```

如果你不希望依赖环境变量，也可以一次性在命令里指定索引：

```bash
uv tool install --from . sediment --force --reinstall --compile-bytecode \
  --default-index "https://<your-internal-pypi>/simple" \
  --index-strategy first-index
```

---

## 2) 更稳方案：先在内网预下载 wheelhouse，再离线安装

> 适用于“内网源偶发不稳定”或“希望构建可重复安装包”的场景。

### 2.1 先下载依赖到本地目录

在 Sediment 仓库根目录执行：

```bash
mkdir -p wheelhouse
uv pip download \
  --default-index "https://<your-internal-pypi>/simple" \
  --dest wheelhouse \
  mcp pyyaml python-docx python-pptx starlette uvicorn hatchling
```

> `hatchling` 是构建本地项目时需要的构建后端，也建议一起准备。

### 2.2 从 wheelhouse 离线安装 CLI

```bash
uv tool install \
  --from . \
  sediment \
  --force --reinstall --compile-bytecode \
  --no-index \
  --find-links wheelhouse
```

---

## 3) 固化到 uv 配置（避免每次手动 export）

为了避免每次手动设置环境变量，建议一次性配置 `uv.toml`。

> 重要：`uv tool` 是用户级命令，主要读取**用户级/系统级**配置，通常不会读取项目内的 `./uv.toml`。

推荐用户级路径：

- Linux/macOS：`~/.config/uv/uv.toml`
- Windows：`%APPDATA%\uv\uv.toml`

示例内容：

```toml
# uv.toml
default-index = "https://<your-internal-pypi>/simple"
```

然后重新执行安装：

```bash
uv tool install --from . sediment --force --reinstall --compile-bytecode
```

如果你必须把配置放在自定义位置，可用 `--config-file` 显式指定：

```bash
uv --config-file /path/to/uv.toml tool install --from . sediment --force --reinstall --compile-bytecode
```

---

## 3.5) Quartz（可选）在内网的处理

Sediment 核心 CLI 不依赖 Node/npm；只有 `/portal/graph-view` 的 Quartz 页面需要 npm 依赖。

如果你需要 Quartz，请把 npm 源切到企业内部 registry 后再安装：

```bash
# 示例
npm config set registry https://<your-internal-npm>/
cd "<SEDIMENT_STATE_DIR>/quartz-runtime/quartz"
npm i
```

如果你不需要图谱页，可以先跳过 Quartz，不影响 CLI 与主流程。

`<SEDIMENT_STATE_DIR>` 表示 Sediment 的用户状态目录（共享 Quartz runtime 的存放位置）。

常见默认值：

- Linux：`${XDG_STATE_HOME:-$HOME/.local/state}/sediment`
- macOS：`$HOME/Library/Application Support/Sediment`

如果你的环境做了自定义，请替换为实际状态目录路径。

---

## 4) 解决“安装成功但命令 sediment 不存在”

如果出现：

- `sediment: The term 'sediment' is not recognized ...`

通常是 PATH 没包含 uv 的工具安装目录。

### Windows（PowerShell）

查看工具目录：

```powershell
uv tool dir --bin
```

把该目录加入用户 PATH 后，重开终端再试：

```powershell
sediment --help
```

### Linux / macOS

常见目录是 `~/.local/bin` 或 `~/.cargo/bin`，加入 PATH：

```bash
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
sediment --help
```

---

## 5) 常见排查

1. **仍然访问 `pypi.org`**
   - 检查是否真的设置了 `UV_DEFAULT_INDEX`（或命令里 `--default-index`）。
   - 检查是否存在 `UV_INDEX` / `UV_EXTRA_INDEX_URL` 把公网源加回去了。
   - 执行 `uv tool install -v ...` 看详细日志。

2. **内网源有包名但仍失败**
   - 确认该包支持你当前 Python 版本与平台（win_amd64 / manylinux 等）。
   - 确认内网源同步的是 `simple` API，且证书链被系统信任。

3. **`sediment` 命令找不到**
   - 先 `uv tool list` 确认确实安装了 `sediment`。
   - 再修复 PATH，重开终端。

4. **`sediment server start` 卡在 health 检查或超时**
   - 先查看日志：`<state-dir>/logs/platform.log`（Windows 示例：`.sediment_state\logs\platform.log`）。
   - 检查端口是否被占用：实例配置端口（默认 8000）若冲突会导致服务起不来。
   - 检查本机代理变量（`HTTP_PROXY`/`HTTPS_PROXY`）是否误拦截了 `127.0.0.1`。
   - 必要时加长启动超时：`sediment server start --startup-timeout 30`。

---

## 6) 给企业管理员的建议（一次治理，长期省事）

- 在内网 PyPI 镜像里预热并定期同步 Sediment 所需依赖。
- 提供统一的 `uv.toml` 模板，所有开发机复用。
- 对生产环境提供 wheelhouse 制品（按 Python 版本、操作系统分发）。

这样可以把“开发机偶发联网问题”变成“可审计、可复现的标准安装流程”。
