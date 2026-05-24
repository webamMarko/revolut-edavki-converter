# PRD: Custom Dashboard

**Epic:** SAA-88
**Status:** Ready for Spec
**Confidence:** 50%
**Last updated:** 2026-05-24

## Summary

Allow users to create one custom dashboard per user that includes any combination of widgets/sections already present on the report page. The builder uses a drag-and-drop grid where users place and resize widget tiles. The dashboard appears as a new "My Dashboard" tab in the report navigation. This requires refactoring existing sections into standalone, reusable widgets.

## Available Widgets

The following existing report sections become selectable widgets:
1. Quick Glance (portfolio snapshot card)
2. Health Score
3. Summary (portfolio overview with value, P&L, metrics)
4. Charts (performance, allocation, sector)
5. Positions (holdings table with P&L)
6. Dividends (income tracking)
7. Projections (Monte Carlo & FIRE)
8. Notes (investment notes)
9. Real Estate
10. Risk (risk analysis & metrics)
11. DCA Strategy
12. Tax Summary (timeline + preview + holding countdown + FIFO details)
13. Tax Calendar (year-end calendar)
14. Smart Sell (tax-loss harvesting)
15. Tax Wizard (eDavki filing)
16. Transaction History

## Requirements

1. Users can create one custom dashboard with a drag-and-drop grid builder
2. Widgets are resizable tiles that can be placed freely on a grid
3. The custom dashboard appears as a "My Dashboard" tab in the report navigation
4. Dashboard configuration is persisted per user in the database
5. Premium and admin roles have access; guests see the demo dashboard only
6. Widget data uses the same data pipeline as the existing report page (no new API endpoints needed for widget content)

## Acceptance Criteria

1. A new "My Dashboard" tab appears in the report nav for premium/admin users
2. Clicking the tab shows the custom dashboard (empty state with "Add Widgets" prompt if no widgets configured)
3. An edit mode allows adding/removing/resizing/repositioning widgets on a grid
4. Widget content renders identically to the corresponding section on the existing report page
5. Dashboard layout persists across sessions
6. Works on both desktop and mobile viewports

## Open Questions

1. Should custom dashboards be shareable via the existing share link feature?
2. Should widgets support per-widget scope filtering (e.g. stocks-only positions)?
3. What grid library to use for drag-and-drop (CSS Grid + vanilla JS vs lightweight library)?
4. Should there be a default widget layout for first-time users?

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Builder UX | Drag-and-drop grid builder | User chose visual grid with resizable tiles over simpler checklist | 2026-05-24 |
| Dashboard count | 1 per user | Keep it simple, expand later if needed | 2026-05-24 |
| Nav placement | New "My Dashboard" tab | Alongside existing tabs, doesn't replace Overview | 2026-05-24 |
