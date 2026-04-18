from sediment import web_ui, web_ui_shell
from sediment.web_ui_shared import (
    html_lang,
    localized_path,
    logo_mark_data_uri,
    logo_mark_svg,
    normalize_locale,
)


def test_shared_web_ui_locale_helpers_stay_compatible() -> None:
    cases = [
        (None, "en", "en", "/search?lang=en"),
        ("en-US", "en", "en", "/search?lang=en"),
        ("zh-CN", "zh", "zh-CN", "/search?lang=zh"),
        ("ZH_hans", "zh", "zh-CN", "/search?lang=zh"),
    ]

    for locale, normalized, html, path in cases:
        assert normalize_locale(locale) == normalized
        assert html_lang(locale) == html
        assert localized_path("/search", locale) == path
        assert web_ui._normalize_locale(locale) == normalized
        assert web_ui._html_lang(locale) == html
        assert web_ui._localized_path("/search", locale) == path
        assert web_ui_shell.normalize_locale(locale) == normalized
        assert web_ui_shell.html_lang(locale) == html
        assert web_ui_shell.localized_path("/search", locale) == path


def test_shared_web_ui_logo_mark_helpers_stay_compatible() -> None:
    assert logo_mark_svg() == web_ui._logo_mark_svg()
    assert logo_mark_svg() == web_ui_shell.logo_mark_svg()
    assert logo_mark_data_uri() == web_ui._logo_mark_data_uri()
    assert logo_mark_data_uri() == web_ui_shell.logo_mark_data_uri()


def test_web_ui_shell_shared_shell_uses_shared_template_hooks() -> None:
    html = web_ui_shell.shared_shell(
        "Compat shell",
        '<section data-testid="compat-body">Hello</section>',
        "window.__compatLoaded = true;",
        locale="zh",
    )

    assert 'data-shell-variant="portal"' in html
    assert 'id="sediment-shell-data"' in html
    assert 'data-testid="compat-body"' in html
    assert "window.__compatLoaded = true;" in html
    assert ".page-title" in html
    assert ".utility-icon-button" in html
