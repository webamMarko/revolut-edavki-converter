# PRD: Redesign Overview Page Layout

**Epic:** SAA-572
**Status:** Ready for Review
**Confidence:** 90%
**Last updated:** 2026-06-07

## Summary

Restructure the Overview page to establish a clear visual hierarchy: metrics cards at the top (collapsed secondary by default), followed by the Portfolio Value chart, then Portfolio Health. Milestones and achievements are unified into a single section with same-style cards, controlled by a toggle. Top Movers is relocated from Overview to below the positions table in the Positions tab.

## Requirements

1. Metrics cards (primary) render at the top of the Overview page
2. Secondary metrics panel defaults to collapsed; "Show more metrics" expands it
3. Portfolio Value chart renders immediately below the metrics section
4. Portfolio Health section renders below the Portfolio Value chart
5. Achievements section (including milestones as same-style cards) appears below Portfolio Health
6. Achievements toggle shows/hides the achievements section only (chart always visible)
7. Remove duplicate achievement displays — achievements render once as a unified card grid
8. Milestones are treated as achievements — same card style (icon, title, detail), no separate strip
9. Top Movers section is removed from Overview page
10. Top Movers is added to the Positions tab, below the positions table
11. Gains Breakdown and Benchmark Comparison remain below achievements on Overview

## Acceptance Criteria

1. Page order top-to-bottom: banners → primary metrics → (expandable secondary metrics) → portfolio value chart → portfolio health → achievements → gains/benchmark
2. Secondary metrics panel is collapsed on page load
3. Achievements toggle hides/shows the achievements card grid without affecting the chart
4. Milestones render as achievement cards (same layout) — no separate milestones strip exists
5. Top Movers section does not render on the Overview page
6. Top Movers renders in the Positions tab below the positions table
7. No duplicate achievement displays exist anywhere on the page

## Open Questions

None — all key decisions resolved.

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Achievements toggle scope | Toggle achievements display only | Chart should always be visible for portfolio context | 2026-06-07 |
| Section order below health | Remove Top Movers from Overview | Keep Overview minimal; movers belong with positions | 2026-06-07 |
| Milestones fate | Merge into achievements (same card style) | They are the same thing — reduces duplication | 2026-06-07 |
| Metrics default state | Collapsed by default | Show primary 4 metrics; user expands for more | 2026-06-07 |
| Milestones visual style | Same card style as achievements | Unified look, milestones ARE achievements | 2026-06-07 |
| Top Movers in Positions tab | Below the positions table | Positions table is primary content; movers supplemental | 2026-06-07 |
