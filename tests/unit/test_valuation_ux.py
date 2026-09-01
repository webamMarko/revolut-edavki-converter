"""Valuation workbench UX regressions."""

from src.web.templates import COMMON_JS, FOUC_SCRIPT, page_env


def render(has_fmp_key=True):
    return page_env.get_template("pages/valuation.html.j2").render(
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=True,
        show_drop_import=False,
        username=None,
        role="guest",
        active_page="valuation",
        active_portfolio_name=None,
        has_fmp_key=has_fmp_key,
    )


def test_missing_api_key_explains_unavailable_state_and_disables_search():
    html = render(False)
    assert "Market data is not configured" in html
    assert 'id="vwTicker"' in html and 'aria-controls="vwSuggest" disabled' in html
    assert 'id="vwLoadBtn" class="vw-btn vw-btn-primary" disabled' in html


def test_configured_state_has_quick_starts_and_enabled_search():
    html = render(True)
    assert "Choose a company to value" in html
    assert 'data-ticker="AAPL"' in html
    ticker_tag = html.split('id="vwTicker"', 1)[1].split(">", 1)[0]
    assert "disabled" not in ticker_tag


def test_controls_expose_accessible_state():
    html = render(True)
    assert 'role="listbox"' in html
    assert 'role="tablist"' in html
    assert 'aria-selected="true"' in html
    assert 'aria-pressed="true"' in html
    assert 'aria-live="polite"' in html


def test_mobile_results_precede_collapsible_assumptions():
    html = render(True)
    assert ".vw-results { order: 1; }" in html
    assert ".vw-assumptions { order: 2;" in html
    assert ".vw-assumptions.collapsed .vw-assumptions-body { display: none; }" in html


def test_page_uses_shared_dark_and_light_theme_tokens():
    html = render(True)
    assert "var(--surface, #fff)" in html
    assert "var(--raised, #f3f4f6)" in html
    assert "var(--card-bg, #fff)" not in html
    assert "var(--bg2, #f3f4f6)" not in html


def test_refresh_preserves_current_results_and_ignores_stale_requests():
    html = render(True)
    assert "if (on && !VW.market)" in html
    assert "requestId !== VW._requestId" in html
    assert "requestId === VW._requestId" in html


def test_ticker_can_be_loaded_from_and_written_to_url():
    html = render(True)
    assert "new URLSearchParams(window.location.search).get('ticker')" in html
    assert "url.searchParams.set('ticker', ticker)" in html
    assert "history.replaceState(null, '', url)" in html
