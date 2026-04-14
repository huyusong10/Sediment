from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from importlib import resources
from pathlib import PurePosixPath


def _resource_text(package: str, path: str) -> str:
    resource = resources.files(package)
    for part in PurePosixPath(path).parts:
        resource = resource.joinpath(part)
    return resource.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def read_asset_text(name: str) -> str:
    return _resource_text("sediment.assets", name)


def render_asset_template(name: str, replacements: Mapping[str, str]) -> str:
    rendered = read_asset_text(name)
    for key, value in replacements.items():
        rendered = rendered.replace(f"__{key}__", value)
    return rendered


@lru_cache(maxsize=None)
def read_skill_text(skill_name: str) -> str:
    return _resource_text(f"sediment.skills.{skill_name}", "SKILL.md")
