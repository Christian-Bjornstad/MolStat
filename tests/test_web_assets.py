from pathlib import Path


WEB = Path(__file__).parents[1] / "src" / "molstat" / "web_assets"


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def test_board_has_required_landmarks_and_live_status():
    html = read("board.html")
    assert '<main id="dashboard">' in html
    assert 'aria-live="polite"' in html
    assert 'id="stale-banner"' in html
    assert 'id="offline-status"' in html
    assert 'id="analysis-grid"' in html
    assert '<script src="/assets/board.js" defer></script>' in html
    assert '<link rel="stylesheet" href="/assets/board.css">' in html
    assert "<style" not in html
    assert "<script>" not in html


def test_board_js_uses_only_safe_dom_text_apis():
    script = read("board.js")
    for forbidden in (
        "innerHTML",
        "insertAdjacentHTML",
        "document.write",
        "eval(",
        "Function(",
    ):
        assert forbidden not in script
    assert "document.createElement" in script
    assert "textContent" in script
    assert 'fetch("/api/v1/snapshot"' in script


def test_board_supports_polling_and_tv_pagination():
    script = read("board.js")
    assert "30000" in script
    assert "20000" in script
    assert "CARDS_PER_PAGE = 12" in script
    assert 'params.get("mode") === "tv"' in script
    assert "prefers-reduced-motion" in script
    assert "lastSnapshot" in script


def test_board_css_is_responsive_and_prevents_horizontal_scroll():
    css = read("board.css")
    assert "overflow-x: hidden" in css
    assert "repeat(auto-fit, minmax(280px, 1fr))" in css
    assert "@media (min-width: 1366px)" in css
    assert "@media (min-width: 1920px)" in css
    assert "@media (min-width: 3000px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_package_data_includes_web_assets():
    pyproject = (WEB.parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.package-data]" in pyproject
    assert 'molstat = ["web_assets/*.html", "web_assets/*.css", "web_assets/*.js"]' in pyproject

