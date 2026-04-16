from __future__ import annotations

import subprocess
from pathlib import Path

from sediment.quartz_runtime import build_quartz_site


def test_build_quartz_site_normalizes_graph_runtime_for_browser_compatibility(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_dir = tmp_path / "runtime"
    graph_script = runtime_dir / "quartz" / "components" / "scripts" / "graph.inline.ts"
    graph_script.parent.mkdir(parents=True, exist_ok=True)
    graph_script.write_text(
        "\n".join(
            [
                'import type { ContentDetails } from "../../plugins/emitters/contentIndex"',
                "",
                "type TweenNode = {",
                "  update: (time: number) => void",
                "  stop: () => void",
                "}",
                "",
                "async function renderGraph(graph: HTMLElement, fullSlug: FullSlug) {",
                "  const slug = simplifySlug(fullSlug)",
                "  const data: Map<SimpleSlug, ContentDetails> = new Map(",
                "    Object.entries<ContentDetails>(await fetchData).map(([k, v]) => [",
                "      simplifySlug(k as FullSlug),",
                "      v,",
                "    ]),",
                "  )",
                "  const neighbourhood = new Set<SimpleSlug>()",
                '  const wl: (SimpleSlug | "__SENTINEL")[] = [slug, "__SENTINEL"]',
                "  const app = new Application()",
                "  await app.init({",
                '    preference: "webgpu",',
                "  })",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (runtime_dir / "quartz.layout.ts").write_text(
        "\n".join(
            [
                "export const defaultContentPageLayout = {",
                "  right: [",
                "    Component.Graph(),",
                "  ],",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (runtime_dir / "package.json").write_text("{}", encoding="utf-8")
    (runtime_dir / "node_modules").mkdir(parents=True, exist_ok=True)

    kb_path = tmp_path / "knowledge-base"
    kb_path.mkdir(parents=True, exist_ok=True)
    (kb_path / "index.root.md").write_text("# Index\n", encoding="utf-8")

    def _fake_run(command, cwd, capture_output, text, timeout, check):
        workspace_root = Path(cwd)
        normalized = (
            workspace_root / "quartz" / "components" / "scripts" / "graph.inline.ts"
        ).read_text(encoding="utf-8")
        layout = (workspace_root / "quartz.layout.ts").read_text(encoding="utf-8")
        assert 'preference: "webgl"' in normalized
        assert 'preference: "webgpu"' not in normalized
        assert 'filePath !== "index.md"' in normalized
        assert '!filePath.startsWith("indexes/")' in normalized
        assert 'data.has(slug) ? [slug, "__SENTINEL"] : []' in normalized
        assert 'condition: (page) => page.fileData.frontmatter?.kind !== "index"' in layout
        public_root = workspace_root / "public"
        public_root.mkdir(parents=True, exist_ok=True)
        (public_root / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    result = build_quartz_site(
        kb_path=kb_path,
        runtime_dir=runtime_dir,
        site_dir=tmp_path / "site",
        knowledge_name="Test KB",
        locale="en",
        timeout_seconds=30,
    )

    assert result["built"] is True
    assert result["site_available"] is True
