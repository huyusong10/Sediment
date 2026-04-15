import pytest
from pathlib import Path
from sediment.package_data import read_asset_text

def test_web_ui_tech_style_applied():
    """
    Test to ensure that the web-shell.html has the minimalist, 
    tech-style applied and no AI-flavored roundness or gradients.
    """
    content = read_asset_text("web-shell.html")

    # Ensure no generic blurry backdrop filters are applied that signify AI flavor
    assert "backdrop-filter: blur(12px);" not in content, "Found AI-flavored glassmorphism (blur) in UI"
    
    # Ensure all rounded corners are forced to 0px
    assert "--radius: 0px;" in content, "Global radius variable should be set to 0px"
    assert "border-radius: var(--radius) !important;" in content, "Border radius override is missing"

    # Ensure hero gradients look tech-oriented or plain
    assert "radial-gradient(circle " not in content, "Glowing radial gradients are too fleshy/AI-like"

    # Ensure monospace font is utilized for typical structured text
    assert "font-family: monospace;" in content, "Monospace font should be used for tech-feel elements"
    assert "search-suggestions-popover" in content, "Search suggestions should use a dedicated popover style"
    assert "position: absolute;" in content, "Popover-based suggestions should avoid reflowing the layout"
    assert "search-status-line" in content, "Search status should reserve vertical space beneath the search controls"
    assert "[data-shell-header-actions]" in content, "Primary navigation and utility controls should be visually separated"
    assert "--nav-button-width:" in content, "Primary navigation buttons should reserve equal width"
    assert ".hero-nav" in content, "Primary navigation should sit on its own row beneath the title area"
    assert ".nav-link" in content, "Primary navigation should use dedicated nav-link styling"
    assert "min-height: 52px;" in content, "Primary navigation should keep equal height even when English labels wrap"
    assert ".action-row" in content, "Non-navigation button rows should use a dedicated equal-size action layout"
    assert ".action-link" in content, "Content actions should not inherit primary navigation sizing"
    assert ".scroll-list" in content, "Long admin lists should cap height and scroll instead of stretching the page forever"
    assert ".overview-activity-list" in content, "Recent activity should use the same capped scroll treatment as long issue lists"
    assert ".grid.align-start" in content, "Admin panel grids should align cards to the top instead of stretching mismatched content"
    assert ".dropzone" in content, "Admin ingest should expose a dedicated drag-and-drop surface"
    assert ".doc-tree-group" in content, "File management should expose grouped document browsing"
    assert ".file-index-tree" in content, "File management should cap index browsing height and scroll inside the panel"
    assert ".file-editor-area" in content, "File management should give markdown editing a large dedicated editing area"
    assert ".settings-preview" in content, "Settings should show an effective-config preview alongside raw YAML editing"
    assert ".settings-editor-area" in content, "Settings should expose a large raw YAML editor instead of a cramped textarea"
    assert "utility-icons" in content, "Utility controls should use a dedicated icon group"
    assert "utility-action" in content, "Utility actions should use a style distinct from primary navigation"
    assert "utility-icon-button" in content, "Theme and locale toggles should use compact icon buttons"
    assert "download-action" in content, "Tutorial downloads should use a dedicated action style"
    assert ".page-title" in content, "Shell should define a dedicated visible page title style"
    assert ".sr-only" in content, "Redundant visual headings should fall back to an sr-only treatment instead of display:none"
    assert ".brand-lockup" in content, "Brand area should use the full lockup logo treatment"
    assert ".compact-note" in content, "Tutorial copy should default to a compact note treatment"
    assert ".tip-trigger" in content, "Compact tutorial notes should expose an explicit hover/focus trigger"
    assert ".tip-panel" in content, "Compact tutorial notes should reveal full details in a tooltip panel"
    assert ".tutorial-section-stack" in content, "MCP guidance should keep tool roles and agent steering inside the MCP section"
    assert ":focus:not(:focus-visible)" in content, "Keyboard focus outlines should survive mouse-only focus suppression"
