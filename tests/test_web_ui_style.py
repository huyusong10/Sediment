from sediment.package_data import read_asset_text


def _assert_tokens(content: str, *tokens: str) -> None:
    for token in tokens:
        assert token in content, f"Missing shared web-shell surface hook: {token}"


def test_web_shell_exposes_shared_surface_hooks() -> None:
    content = read_asset_text("web-shell.html")

    _assert_tokens(
        content,
        ".search-suggestions-popover",
        ".search-status-line",
        ".hero-nav",
        ".nav-link",
        ".action-row",
        ".utility-icons",
        ".utility-action",
        ".utility-icon-button",
        ".page-title",
        ".sr-only",
        ":focus-visible",
    )


def test_web_shell_exposes_compact_tips_and_workbench_hooks() -> None:
    content = read_asset_text("web-shell.html")

    _assert_tokens(
        content,
        ".compact-note",
        ".tip-trigger",
        ".tip-panel",
        ".tutorial-layout",
        ".tutorial-side-stack",
        ".tutorial-section-stack",
        ".admin-kb-layout",
        ".panel-header-tip",
        ".live-log-area",
    )


def test_web_shell_exposes_admin_workspace_hooks() -> None:
    content = read_asset_text("web-shell.html")

    _assert_tokens(
        content,
        ".scroll-list",
        ".overview-activity-list",
        ".grid.align-start",
        ".dropzone",
        ".doc-tree-group",
        ".file-index-tree",
        ".file-editor-area",
        ".settings-preview",
        ".settings-editor-area",
    )
