from __future__ import annotations

import json
from functools import lru_cache
from urllib.parse import quote

from sediment.package_data import read_asset_text, render_asset_template


@lru_cache(maxsize=1)
def logo_mark_svg() -> str:
    return read_asset_text("logo-mark.svg").strip()


@lru_cache(maxsize=1)
def logo_svg() -> str:
    return read_asset_text("logo.svg").strip()


@lru_cache(maxsize=1)
def logo_mark_data_uri() -> str:
    return f"data:image/svg+xml;utf8,{quote(logo_mark_svg())}"


def normalize_locale(locale: str | None) -> str:
    return "zh" if str(locale or "").strip().lower().startswith("zh") else "en"


def html_lang(locale: str | None) -> str:
    return "zh-CN" if normalize_locale(locale) == "zh" else "en"


def localized_path(path: str, locale: str | None) -> str:
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}lang={normalize_locale(locale)}"


def json_script_payload(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


def render_shell_template(
    title: str,
    body: str,
    *,
    locale: str | None,
    shell_data: object,
    page_data: object | None = None,
    page_script_tag: str = "",
    shell_variant: str = "portal",
) -> str:
    active_locale = normalize_locale(locale)
    page_data_tag = ""
    if page_data is not None:
        page_data_tag = (
            '<script id="sediment-page-data" type="application/json">'
            f"{json_script_payload(page_data)}"
            "</script>"
        )
    return render_asset_template(
        "web-shell.html",
        {
            "HTML_LANG": html_lang(active_locale),
            "ACTIVE_LOCALE": active_locale,
            "TITLE": title,
            "LOGO_MARK_DATA_URI": logo_mark_data_uri(),
            "BODY": body,
            "SHELL_DATA": json_script_payload(shell_data),
            "PAGE_DATA_TAG": page_data_tag,
            "PAGE_SCRIPT_TAG": page_script_tag,
            "SHELL_VARIANT": shell_variant,
        },
    )
