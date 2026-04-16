from __future__ import annotations

import re
from pathlib import Path


def test_skill_assets_do_not_embed_chinese_literals() -> None:
    skill_root = Path(__file__).resolve().parents[1] / "src" / "sediment" / "skills"
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]")

    offending: list[str] = []
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".md", ".py", ".yaml", ".yml", ".json"}:
            continue
        content = path.read_text(encoding="utf-8")
        if chinese_pattern.search(content):
            offending.append(str(path.relative_to(skill_root)))

    assert offending == []
