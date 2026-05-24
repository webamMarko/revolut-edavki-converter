# PRD: Custom Dashboard

**Epic:** SAA-88
**Status:** Draft
**Confidence:** 0%
**Last updated:** 2026-05-24

## Summary

Allow users to create a custom dashboard that includes any combination of widgets/sections already present on the report page (Quick Glance, Health Score, Summary, Charts, Positions, Dividends, Projections, Notes, Real Estate, Risk, DCA Strategy, Tax sub-sections, Transactions). This requires refactoring existing sections into standalone, reusable widgets.

## Requirements

## Acceptance Criteria

## Open Questions

1. How many custom dashboards can a user create?
2. What is the widget selection UX (drag-and-drop builder vs checklist)?
3. Should widgets be resizable/reorderable or fixed layout?
4. Where does the custom dashboard live in the nav (new tab, replaces overview)?
5. Should custom dashboards be shareable?
6. Which user roles have access to custom dashboards?
7. How is dashboard config persisted (DB schema)?
8. Should widgets support per-widget scope filtering (e.g. stocks-only positions)?

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
