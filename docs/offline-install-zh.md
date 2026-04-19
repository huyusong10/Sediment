# Sediment 内网离线安装指南（Windows / Linux）

> 适用场景：机器不能访问公网（例如无法访问 `pypi.org` / `github.com`），但可以访问企业内部的 PyPI / npm / Git 仓库。

你遇到的报错本质上是：`uv tool install --from . sediment ...` 在解析依赖时仍然走了默认索引 `https://pypi.org/simple`，所以在内网被阻断。

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

可以把内网索引写进 uv 配置文件，避免每次设置环境变量。

示例（请按你环境修改）：

```toml
# uv.toml
default-index = "https://<your-internal-pypi>/simple"
```

可放在：

- 用户级配置目录（推荐）
- 或项目根目录（仅对当前项目生效）

然后重新执行：

```bash
uv tool install --from . sediment --force --reinstall --compile-bytecode
```

---

## 3.5) Graph / Quartz 前端构建链（可选）

Sediment 运行时本身不依赖 Node/npm；终端用户仍然只需要 `pip install sediment`。

只有在你要修改或重建浏览器图形资产时，才需要 Node/npm，例如：

- `/portal/graph-view` 的 Insights Graph
- 可选的 Quartz 运行时资源

如果你需要重建这些前端资产，请先把 npm 源切到企业内部 registry：

```bash
npm config set registry https://<your-internal-npm>/
cd /path/to/Sediment/frontend/graph
npm ci
python ../../scripts/build_graph_assets.py
```

如果你不改图前端，这一步可以跳过，不影响 CLI、主流程和 wheel 安装。

如果你还需要单独安装 Quartz 运行时，请继续在共享 Sediment state 目录下执行：

```bash
cd <sediment-state>/quartz-runtime/quartz
npm i
```

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

---

## 6) 给企业管理员的建议（一次治理，长期省事）

- 在内网 PyPI 镜像里预热并定期同步 Sediment 所需依赖。
- 提供统一的 `uv.toml` 模板，所有开发机复用。
- 对生产环境提供 wheelhouse 制品（按 Python 版本、操作系统分发）。

这样可以把“开发机偶发联网问题”变成“可审计、可复现的标准安装流程”。
