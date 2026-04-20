# ruff: noqa: E501
from __future__ import annotations

from sediment.web_ui_shared import (
    html_lang as _shared_html_lang,
    localized_path as _shared_localized_path,
    logo_mark_data_uri as _shared_logo_mark_data_uri,
    logo_mark_svg as _shared_logo_mark_svg,
    normalize_locale as _shared_normalize_locale,
    render_shell_template as _shared_render_shell_template,
    shell_data_defaults as _shared_shell_data_defaults,
)


def logo_mark_svg() -> str:
    return _shared_logo_mark_svg()


def logo_mark_data_uri() -> str:
    return _shared_logo_mark_data_uri()


def logo_inline(class_name: str = "brand-mark") -> str:
    return logo_mark_svg().replace("<svg ", f'<svg class="{class_name}" aria-hidden="true" ')


def normalize_locale(locale: str | None) -> str:
    return _shared_normalize_locale(locale)


def html_lang(locale: str) -> str:
    return _shared_html_lang(locale)


def localized_path(path: str, locale: str) -> str:
    return _shared_localized_path(path, locale)


def nav_link(label: str, href: str, *, primary: bool = False) -> str:
    classes = "button primary" if primary else "button"
    return f'<a class="{classes}" href="{href}">{label}</a>'


def shared_shell(title: str, body: str, script: str, *, locale: str) -> str:
    active_locale = normalize_locale(locale)
    toggle_label = "EN" if active_locale == "zh" else "中文"
    page_script_tag = f"<script>{script}</script>" if script.strip() else ""
    return _shared_render_shell_template(
        title,
        body,
        locale=active_locale,
        page_script_tag=page_script_tag,
        shell_data={
            **_shared_shell_data_defaults(active_locale),
            "toggleLabel": toggle_label,
        },
    )
