# Sediment Intranet / Offline Installation Guide (Windows / Linux)

> Use this guide when hosts cannot access public internet (for example, `pypi.org` / `github.com`) but can access internal PyPI, npm, and Git mirrors.

In restricted enterprise networks, `uv tool install --from . sediment ...` may still attempt the default index `https://pypi.org/simple` unless index settings are explicitly pinned.

---

## 0. Prerequisites

- Python 3.11+
- `uv` available from your internal package source
- Sediment source code available from your internal Git mirror / artifact system
- Internal PyPI repository containing all Sediment runtime dependencies

Current runtime dependencies (from `pyproject.toml`):

- `mcp`
- `pyyaml`
- `python-docx`
- `python-pptx`
- `starlette`
- `uvicorn`

---

## 1) Recommended: force uv to use internal PyPI only

Replace `https://<your-internal-pypi>/simple` with your real internal URL.

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

Validate installation:

```bash
uv tool list
uv tool dir --bin
sediment --help
```

You can also pin the index directly in one command (without env vars):

```bash
uv tool install --from . sediment --force --reinstall --compile-bytecode \
  --default-index "https://<your-internal-pypi>/simple" \
  --index-strategy first-index
```

---

## 2) More deterministic: build a wheelhouse, then install with `--no-index`

### 2.1 Download required packages to a local wheelhouse

Run in the Sediment repository root:

```bash
mkdir -p wheelhouse
uv pip download \
  --default-index "https://<your-internal-pypi>/simple" \
  --dest wheelhouse \
  mcp pyyaml python-docx python-pptx starlette uvicorn hatchling
```

> `hatchling` is included because local project builds require it as the build backend.

### 2.2 Install from local wheelhouse only

```bash
uv tool install \
  --from . \
  sediment \
  --force --reinstall --compile-bytecode \
  --no-index \
  --find-links wheelhouse
```

---

## 3) Persist settings in `uv.toml`

To avoid setting environment variables every time, configure `uv.toml` once.

> Important: `uv tool` commands are user-level operations. They read **user/system** config, and generally ignore project-local `./uv.toml`.

Recommended user-level paths:

- Linux/macOS: `~/.config/uv/uv.toml`
- Windows: `%APPDATA%\uv\uv.toml`

Example file content:

```toml
# uv.toml
default-index = "https://<your-internal-pypi>/simple"
```

Then install again:

```bash
uv tool install --from . sediment --force --reinstall --compile-bytecode
```

If you must keep config in a custom location, pin it explicitly with `--config-file`:

```bash
uv --config-file /path/to/uv.toml tool install --from . sediment --force --reinstall --compile-bytecode
```

---

## 3.5) Quartz (optional) in internal networks

Sediment CLI itself does **not** require Node/npm. Only the optional `/portal/graph-view` Quartz page needs npm packages.

If Quartz is needed, switch npm to the internal registry first:

```bash
npm config set registry https://<your-internal-npm>/
cd "<SEDIMENT_STATE_DIR>/quartz-runtime/quartz"
npm i
```

If graph view is not required, Quartz can be skipped without affecting core CLI workflows.

`<SEDIMENT_STATE_DIR>` means the Sediment user state directory (where the shared Quartz runtime is stored).

Typical defaults:

- Linux: `${XDG_STATE_HOME:-$HOME/.local/state}/sediment`
- macOS: `$HOME/Library/Application Support/Sediment`

If your environment uses a custom location, use that actual state directory path instead.

---

## 4) Fix: installed but `sediment` command not found

If `sediment` is installed but shell cannot find it, PATH likely misses uv's tool bin directory.

### Windows (PowerShell)

```powershell
uv tool dir --bin
```

Add that directory to user PATH, reopen terminal, and retry:

```powershell
sediment --help
```

### Linux / macOS

```bash
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
sediment --help
```

---

## 5) Troubleshooting checklist

1. **Still accessing `pypi.org`**
   - verify `UV_DEFAULT_INDEX` (or `--default-index`)
   - verify `UV_INDEX` / `UV_EXTRA_INDEX_URL` are not adding public indexes
   - run `uv tool install -v ...` for detailed logs

2. **Package exists in internal source but install still fails**
   - confirm wheel compatibility with target Python/OS
   - confirm your internal mirror exposes a valid `simple` API and trusted certificate chain

3. **`sediment` command not found**
   - confirm tool is installed via `uv tool list`
   - fix PATH and restart shell

4. **`sediment server start` hangs on health checks or times out**
   - inspect logs first: `<state-dir>/logs/platform.log` (Windows example: `.sediment_state\logs\platform.log`)
   - check port conflicts on the configured server port (default 8000)
   - verify local proxy env vars (`HTTP_PROXY` / `HTTPS_PROXY`) are not intercepting `127.0.0.1`
   - increase startup timeout if needed: `sediment server start --startup-timeout 30`

---

## 6) Admin recommendations for enterprise rollout

- pre-warm and regularly sync Sediment dependencies in internal PyPI
- provide a shared `uv.toml` template for all developer machines
- publish versioned wheelhouse artifacts per Python version and OS

This turns ad-hoc network failures into an auditable and repeatable installation process.
