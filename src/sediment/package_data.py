from __future__ import annotations

from importlib import resources


def read_asset_text(name: str) -> str:
    return resources.files("sediment.assets").joinpath(name).read_text(encoding="utf-8")


def read_skill_text(skill_name: str) -> str:
    return (
        resources.files(f"sediment.skills.{skill_name}")
        .joinpath("SKILL.md")
        .read_text(encoding="utf-8")
    )
