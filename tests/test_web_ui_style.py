from sediment.package_data import read_asset_text


def _assert_tokens(content: str, *tokens: str) -> None:
    for token in tokens:
        assert token in content, f"Missing shared web-shell surface hook: {token}"


def _rule_body(content: str, selector: str) -> str:
    start = content.index(selector)
    body_start = content.index("{", start) + 1
    body_end = content.index("}", body_start)
    return content[body_start:body_end]


def test_web_shell_exposes_shared_surface_hooks() -> None:
    content = read_asset_text("web-shell.html")

    _assert_tokens(
        content,
        ".search-suggestions-popover",
        ".search-status-line",
        ".hero-nav",
        ".nav-link",
        ".action-row",
        ".panel-narrow",
        ".section-gap-sm",
        ".section-gap-md",
        ".section-gap-lg",
        ".section-gap-xl",
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
        ".admin-overview-grid",
        ".admin-overview-column",
        ".admin-overview-panel",
        ".admin-kb-layout",
        ".admin-kb-top-layout",
        ".master-detail",
        ".workspace-tabs",
        ".sticky-editor-header",
        ".admin-file-editor-console",
        ".admin-file-console-tabs",
        ".preview-modal-card",
        ".workbench-layout",
        ".workbench-column",
        ".panel-header-tip",
        ".file-picker",
        ".file-picker-input",
        ".file-picker-status",
        ".runtime-console",
        ".runtime-console-section",
        ".runtime-result-view",
        ".runtime-live-log",
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
        ".file-count-chip",
        ".editor-header-summary",
        ".file-console-section",
        ".file-console-scroll",
        ".file-meta-list",
        ".file-editor-area",
        ".settings-action-row",
        ".settings-preview",
        ".settings-editor-area",
    )


def test_portal_graph_templates_reuse_shared_action_row() -> None:
    available = read_asset_text("portal-graph-available.html")
    unavailable = read_asset_text("portal-graph-unavailable.html")

    assert 'class="action-row"' in available
    assert 'class="action-row"' in unavailable
    assert 'style="margin-top:12px;"' not in available
    assert 'style="margin-top:12px;"' not in unavailable


def test_templates_reuse_shared_spacing_classes_instead_of_inline_offsets() -> None:
    portal_search = read_asset_text("portal-search-body.html")
    portal_legacy = read_asset_text("portal-body.html")
    portal_universe = read_asset_text("portal-universe-body.html")
    admin_login = read_asset_text("admin-login-body.html")
    tutorial = read_asset_text("portal-tutorial-body.html")
    entry = read_asset_text("portal-entry-body.html")
    review = read_asset_text("admin-reviews-section.html")
    overview = read_asset_text("admin-overview-section.html")
    system = read_asset_text("admin-system-section.html")
    files = read_asset_text("admin-files-section.html")
    kb = read_asset_text("admin-kb-section.html")

    assert 'class="list section-gap-md"' in portal_search
    assert 'style="margin-top:18px;"' not in portal_search
    assert 'class="list section-gap-sm"' in portal_legacy
    assert 'style="margin-top:14px;"' not in portal_legacy
    assert 'class="universe-panel universe-panel-guide universe-overlay-panel universe-overlay-panel-center"' in portal_universe
    assert 'class="universe-panel universe-panel-system universe-overlay-panel universe-overlay-panel-center"' in portal_universe
    assert 'class="universe-guide-layout"' in portal_universe
    assert 'class="universe-reader-grid"' in portal_universe
    assert 'class="universe-control-button universe-control-button-primary"' in portal_universe
    assert 'class="universe-guide-stack"' in portal_universe
    assert 'class="universe-file-picker"' in portal_universe
    assert 'class="universe-utilities"' in portal_universe
    assert 'class="universe-panel universe-panel-survey universe-overlay-panel universe-overlay-panel-left"' in portal_universe
    assert 'class="universe-system-layout"' in portal_universe
    assert 'class="button "' not in portal_universe
    assert 'class="panel' not in portal_universe
    assert 'class="card' not in portal_universe
    assert 'style="margin-top:' not in portal_universe
    assert 'class="panel panel-narrow section-gap-lg"' in admin_login
    assert 'style="margin-top:20px; max-width:560px;"' not in admin_login
    assert 'class="detail-block section-gap-sm"' in tutorial
    assert 'class="list section-gap-sm"' in tutorial
    assert 'class="tutorial-layout section-gap-sm"' in tutorial
    assert 'class="tutorial-section-stack section-gap-md"' in tutorial
    assert "tutorial-detail-block" not in tutorial
    assert "tutorial-list-block" not in tutorial
    assert 'class="entry-detail-layout section-gap-sm"' in entry
    assert 'class="panel entry-markdown-panel section-gap-sm"' in entry
    assert 'class="split review-workspace section-gap-xl"' in review
    assert 'class="workbench-layout admin-overview-grid admin-overview-layout section-gap-sm"' in overview
    assert 'class="workbench-layout admin-system-layout section-gap-sm"' in system
    assert 'class="grid settings-editor-stack"' in system
    assert 'class="grid settings-editor-stack section-gap-sm"' not in system
    assert 'class="stack settings-preview-stack section-gap-sm"' in system
    assert 'class="master-detail admin-files-layout section-gap-sm"' in files
    assert 'class="stack files-workspace section-gap-sm"' in files
    assert 'class="stack file-editor-workspace section-gap-sm"' in files
    assert 'class="admin-kb-layout section-gap-sm"' in kb
    assert "admin-kb-workspace" not in kb


def test_templates_reuse_shared_action_rows_without_review_specific_overrides() -> None:
    review = read_asset_text("admin-reviews-section.html")
    shell = read_asset_text("web-shell.html")

    assert 'class="action-row"' in review
    assert "detail-actions" not in review
    assert ".detail-actions" not in shell


def test_shared_layout_classes_do_not_embed_outer_spacing_or_stale_kb_aliases() -> None:
    shell = read_asset_text("web-shell.html")

    assert "margin-top" not in _rule_body(shell, ".workbench-layout")
    assert "margin-top" not in _rule_body(shell, ".admin-overview-grid")
    assert "margin-top" not in _rule_body(shell, ".master-detail")
    assert "margin-top" not in _rule_body(shell, ".admin-kb-layout")
    assert "margin-top" not in _rule_body(shell, ".review-workspace")
    assert "margin-top" not in _rule_body(shell, ".tutorial-layout")
    assert "margin-top" not in _rule_body(shell, ".tutorial-section-stack")
    assert "margin-top" not in _rule_body(shell, ".entry-detail-layout")
    assert "margin-top" not in _rule_body(shell, ".entry-markdown-panel")
    assert ".kb-management-workspace" not in shell
    assert ".settings-editor-stack," not in shell
    assert ".files-workspace," not in shell
