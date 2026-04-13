from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from sediment.kb import index_config

_RUNTIME_IGNORE = shutil.ignore_patterns(".git", "node_modules", "content", "public", "docs")


def quartz_runtime_available(runtime_dir: str | Path) -> bool:
    runtime_root = Path(runtime_dir)
    return (runtime_root / "package.json").exists() and (
        runtime_root / "node_modules"
    ).exists()


def quartz_site_available(site_dir: str | Path) -> bool:
    return (Path(site_dir) / "index.html").exists()


def quartz_status(
    *,
    runtime_dir: str | Path,
    site_dir: str | Path,
) -> dict[str, Any]:
    runtime_root = Path(runtime_dir)
    site_root = Path(site_dir)
    site_index = site_root / "index.html"
    return {
        "runtime_available": quartz_runtime_available(runtime_root),
        "runtime_path": str(runtime_root),
        "site_available": site_index.exists(),
        "site_path": str(site_root),
        "site_index_path": str(site_index),
        "site_last_built_at": (
            site_index.stat().st_mtime if site_index.exists() else None
        ),
    }


def build_quartz_site(
    *,
    kb_path: str | Path,
    runtime_dir: str | Path,
    site_dir: str | Path,
    knowledge_name: str,
    locale: str,
    timeout_seconds: int = 240,
) -> dict[str, Any]:
    runtime_root = Path(runtime_dir).expanduser().resolve()
    site_root = Path(site_dir).expanduser().resolve()
    if not quartz_runtime_available(runtime_root):
        raise RuntimeError("Quartz runtime is not installed or is incomplete.")

    workspace_root = site_root.parent / "workspace"
    content_root = workspace_root / "content"
    public_root = workspace_root / "public"
    _prepare_workspace(
        runtime_root=runtime_root,
        workspace_root=workspace_root,
        knowledge_name=knowledge_name,
        locale=locale,
    )
    _stage_kb_content(
        kb_path=Path(kb_path).expanduser().resolve(),
        content_root=content_root,
        knowledge_name=knowledge_name,
    )
    if public_root.exists():
        shutil.rmtree(public_root)

    command = [
        "node",
        "./quartz/bootstrap-cli.mjs",
        "build",
        "-d",
        "content",
        "-o",
        "public",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Quartz build could not start because `{exc.filename or 'node'}` is unavailable."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Quartz build timed out after {timeout_seconds} seconds."
        ) from exc
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"Quartz build failed: {detail}")
    if not (public_root / "index.html").exists():
        raise RuntimeError("Quartz build finished without producing index.html.")

    _replace_tree(public_root, site_root)
    status = quartz_status(runtime_dir=runtime_root, site_dir=site_root)
    status.update(
        {
            "built": True,
            "command": command,
            "stdout": stdout,
            "stderr": stderr,
        }
    )
    return status


def _prepare_workspace(
    *,
    runtime_root: Path,
    workspace_root: Path,
    knowledge_name: str,
    locale: str,
) -> None:
    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    shutil.copytree(runtime_root, workspace_root, ignore=_RUNTIME_IGNORE)
    _link_node_modules(runtime_root=runtime_root, workspace_root=workspace_root)
    _write_workspace_config(
        workspace_root=workspace_root,
        knowledge_name=knowledge_name,
        locale=locale,
    )


def _link_node_modules(*, runtime_root: Path, workspace_root: Path) -> None:
    target = runtime_root / "node_modules"
    destination = workspace_root / "node_modules"
    if destination.exists() or destination.is_symlink():
        destination.unlink() if destination.is_symlink() else shutil.rmtree(destination)
    try:
        destination.symlink_to(target, target_is_directory=True)
    except OSError:
        shutil.copytree(target, destination)


def _write_workspace_config(
    *,
    workspace_root: Path,
    knowledge_name: str,
    locale: str,
) -> None:
    quartz_locale = "zh-CN" if locale == "zh" else "en-US"
    page_title = knowledge_name.replace("\\", "\\\\").replace('"', '\\"')
    config_text = f"""import {{ QuartzConfig }} from "./quartz/cfg"
import * as Plugin from "./quartz/plugins"

const config: QuartzConfig = {{
  configuration: {{
    pageTitle: "{page_title}",
    pageTitleSuffix: "",
    enableSPA: true,
    enablePopovers: true,
    analytics: null,
    locale: "{quartz_locale}",
    baseUrl: "localhost",
    ignorePatterns: ["private", "templates", ".obsidian"],
    defaultDateType: "modified",
    theme: {{
      fontOrigin: "googleFonts",
      cdnCaching: true,
      typography: {{
        header: "Schibsted Grotesk",
        body: "Source Sans Pro",
        code: "IBM Plex Mono",
      }},
      colors: {{
        lightMode: {{
          light: "#faf8f8",
          lightgray: "#e5e5e5",
          gray: "#b8b8b8",
          darkgray: "#4e4e4e",
          dark: "#2b2b2b",
          secondary: "#284b63",
          tertiary: "#84a59d",
          highlight: "rgba(143, 159, 169, 0.15)",
          textHighlight: "#fff23688",
        }},
        darkMode: {{
          light: "#161618",
          lightgray: "#393639",
          gray: "#646464",
          darkgray: "#d4d4d4",
          dark: "#ebebec",
          secondary: "#7b97aa",
          tertiary: "#84a59d",
          highlight: "rgba(143, 159, 169, 0.15)",
          textHighlight: "#b3aa0288",
        }},
      }},
    }},
  }},
  plugins: {{
    transformers: [
      Plugin.FrontMatter(),
      Plugin.CreatedModifiedDate({{
        priority: ["frontmatter", "git", "filesystem"],
      }}),
      Plugin.SyntaxHighlighting({{
        theme: {{
          light: "github-light",
          dark: "github-dark",
        }},
        keepBackground: false,
      }}),
      Plugin.ObsidianFlavoredMarkdown({{ enableInHtmlEmbed: false }}),
      Plugin.GitHubFlavoredMarkdown(),
      Plugin.TableOfContents(),
      Plugin.CrawlLinks({{ markdownLinkResolution: "shortest" }}),
      Plugin.Description(),
      Plugin.Latex({{ renderEngine: "katex" }}),
    ],
    filters: [Plugin.RemoveDrafts()],
    emitters: [
      Plugin.AliasRedirects(),
      Plugin.ComponentResources(),
      Plugin.ContentPage(),
      Plugin.FolderPage(),
      Plugin.TagPage(),
      Plugin.ContentIndex({{
        enableSiteMap: false,
        enableRSS: false,
      }}),
      Plugin.Assets(),
      Plugin.Static(),
      Plugin.Favicon(),
      Plugin.NotFoundPage(),
    ],
  }},
}}

export default config
"""
    (workspace_root / "quartz.config.ts").write_text(config_text, encoding="utf-8")


def _stage_kb_content(
    *,
    kb_path: Path,
    content_root: Path,
    knowledge_name: str,
) -> None:
    if content_root.exists():
        shutil.rmtree(content_root)
    content_root.mkdir(parents=True, exist_ok=True)

    root_file = index_config()["root_file"]
    copied_any = False
    for source_path in sorted(kb_path.rglob("*.md")):
        relative = source_path.relative_to(kb_path)
        if source_path.name == root_file:
            destination = content_root / "index.md"
        else:
            destination = content_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        copied_any = True

    if not copied_any:
        (content_root / "index.md").write_text(
            (
                f"# {knowledge_name}\n\n"
                "This Quartz site is empty because the knowledge base does not contain "
                "Markdown yet.\n"
            ),
            encoding="utf-8",
        )


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
