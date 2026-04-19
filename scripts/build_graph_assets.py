from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    frontend_root = project_root / "frontend" / "graph"
    asset_root = project_root / "src" / "sediment" / "assets"
    package_json = frontend_root / "package.json"
    if not package_json.exists():
        raise SystemExit(f"Missing frontend workspace: {package_json}")
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm:
        raise SystemExit("Node.js and npm are required to build graph assets.")

    install_command = [npm, "ci"] if (frontend_root / "package-lock.json").exists() else [npm, "install"]
    _run(install_command, cwd=frontend_root)
    _run([npm, "run", "build"], cwd=frontend_root)

    expected = [
        asset_root / "graph.bundle.js",
        asset_root / "graph.bundle.css",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise SystemExit(f"Missing expected graph asset bundle(s): {', '.join(missing)}")
    print("Built graph assets:")
    for path in expected:
        print(f" - {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
