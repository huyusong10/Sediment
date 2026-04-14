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
    assert "[data-shell-header-actions]" in content, "Primary navigation and utility controls should be visually separated"
    assert "utility-icons" in content, "Utility controls should use a dedicated icon group"
    assert "utility-icon-button" in content, "Theme and locale toggles should use compact icon buttons"
