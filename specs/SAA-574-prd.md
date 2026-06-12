# PRD: SAA-574 — Enhance Positions Page with Full-View Modal and Interactive Charts

**Epic:** SAA-574
**Status:** Ready for Review
**Confidence:** 92%
**Last updated:** 2026-06-11

## Summary

Redesign the Positions page to focus on three sections (Current Positions → Performance Attribution → Closed Positions) and add a full-view modal for each position with interactive, zoomable charts for detailed analysis. Remove Top Movers and What-If Simulator sections to keep the page focused. Price data comes from the existing synced DB; CFD/crypto/savings positions show a P&L timeline instead. The modal uses a side-by-side layout (chart left, metrics right) in a large centered dialog with prev/next navigation between positions.

## Requirements

1. Reorder Positions page sections: Current Positions (top), Performance Attribution, Closed Positions (bottom)
2. Remove Top Movers section from Positions page (gain/loss data already visible in sortable table columns)
3. Remove What-If Simulator section from Positions page (Simulate button on position rows still accessible)
4. Add full-view modal triggered by clicking an open position row, containing: interactive price chart, cost basis lots table, bracket progress, and key metrics
5. Modal price chart must support zoom (scroll/pinch), pan (drag), crosshair with date/price tooltip, and time range presets (1M, 3M, 6M, 1Y, All)
6. Use Chart.js zoom plugin for chart interactivity
7. Price chart data sourced from existing `daily_prices` DB table (no on-demand yfinance fetch)
8. For CFD/crypto/savings positions (no yfinance data), show a P&L timeline chart instead of price chart
9. Clicking a closed position row opens a minimal modal: lots consumed, realized P&L, holding period (no price chart)
10. Modal key metrics section shows: current value, total cost, unrealized P&L (€ and %), today's change, weight in portfolio
11. Modal layout: side-by-side — chart (~60% width) on left, metrics + lots + bracket progress (~40%) on right; stacks vertically on mobile
12. Modal size: large centered dialog (90% viewport width, 85% height) with backdrop dimming
13. Prev/next arrows in modal to navigate between positions in table order; keyboard arrow keys also supported
14. Modal closable via X button, Escape key, or clicking backdrop

## Acceptance Criteria

1. Positions page shows exactly 3 sections in order: Current Positions, Performance Attribution, Closed Positions
2. No Top Movers or Simulator sections visible on the page
3. Clicking any open position row opens a full-view modal with price chart, lots, bracket progress, and metrics
4. Chart in modal supports scroll zoom, drag pan, and crosshair hover
5. Time range buttons (1M, 3M, 6M, 1Y, All) filter the chart date range
6. Modal can be closed with X button, Escape key, or clicking backdrop
7. CFD/crypto/savings positions show P&L timeline instead of price chart in modal
8. Clicking a closed position row opens a minimal modal with lots, realized P&L, and holding period
9. Modal key metrics display: current value, total cost, unrealized P&L (€/%), today's change, portfolio weight
10. Price chart loads from DB data without additional API calls
11. Modal uses side-by-side layout on desktop (chart left ~60%, details right ~40%) and stacks vertically on mobile
12. Modal is 90% viewport width × 85% height, centered with dimmed backdrop
13. Prev/next arrows navigate between positions without closing the modal
14. Left/right keyboard arrows also navigate between positions when modal is open

## Open Questions

_None — all major decisions resolved._

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Modal content scope | Rich analytics: price chart + lots + bracket progress + key metrics + allocation | Comprehensive single-position deep dive | 2026-06-11 |
| Top Movers & Simulator | Remove both from Positions page | Keep page focused; gain/loss visible in sortable columns; Simulate button remains on rows | 2026-06-11 |
| Chart interactivity level | Zoom + pan + crosshair + time range presets | Good balance of functionality vs complexity; Chart.js zoom plugin handles it | 2026-06-11 |
| Price data source | Existing DB daily_prices table | Instant load, no API dependency; CFD/crypto/savings get P&L timeline instead | 2026-06-11 |
| Closed position modal | Minimal: lots consumed, realized P&L, holding period | Closed positions don't need full analytics; keep it lightweight | 2026-06-11 |
| Modal metrics | Core P&L only: value, cost, unrealized P&L, today's change, weight | Focused on most actionable info; income/tax/risk metrics excluded | 2026-06-11 |
| Modal layout | Side-by-side: chart left (~60%), metrics/lots right (~40%); vertical stack on mobile | Shows everything at once without scrolling on desktop | 2026-06-11 |
| Modal size | Large centered dialog: 90% width, 85% height, backdrop dimming | Consistent with existing modal patterns; maintains app context | 2026-06-11 |
| Position navigation | Prev/next arrows + keyboard arrow keys | Quick comparison between positions without close/reopen cycle | 2026-06-11 |
