# Technical Specification: Redesign Overview Page Layout

**Epic:** SAA-572
**PRD:** specs/SAA-572-prd.md
**Created:** 2026-06-07
**Status:** Ready for Review
**Confidence:** 92%

## Overview

Restructure the Overview page (`summary.html.j2` + `summary.js`) to reorder sections into a clear visual hierarchy: metrics → portfolio value chart → portfolio health → achievements (with milestones merged in). Remove Top Movers from Overview and relocate it to the Positions tab. Unify milestones and achievements into a single card grid with a show/hide toggle.

This is a pure frontend change — no backend/API modifications needed. All data already exists; only the rendering order and toggle logic change.

## Architecture

### System Context

```
summary.html.j2          — Template: section order (HTML structure)
summary.js               — Metrics rendering, achievements, milestones
achievements.js          — Achievement card rendering
health_score.html.j2     — Portfolio Health section (already exists as widget)
positions.html.j2        — Positions section (receives Top Movers)
```

### Key Components

**Template changes (`src/templates/sections/summary.html.j2`):**
- Reorder `.page-stack` children: metrics → chart → health → achievements → gains/benchmark
- Remove `data-role="topMoversSection"` from Overview
- Remove separate `data-role="milestonesSection"` — milestones render inside achievements grid
- Add achievements toggle button above the achievements grid

**JS changes (`src/templates/assets/sections/summary.js`):**
- `updateMilestones()` → render milestone items as achievement cards within `achievementsGrid`
- Remove Top Movers rendering from Overview context
- Achievements toggle: show/hide `achievementsSection` via localStorage-persisted state

**Positions tab (`src/templates/sections/positions.html.j2` + `positions.js`):**
- Add Top Movers section below the positions table
- Move `topMoversSection` HTML and its JS rendering here

**Achievements unification (`src/templates/assets/achievements.js`):**
- Accept milestone events as input alongside achievement data
- Render both with identical card markup (icon, title, detail)

### Data Model

No database changes. All data sources remain the same.

### API Contracts

No API changes. The existing `/` endpoint returns the same analytics data; only client-side rendering order changes.

## Implementation Plan

### Phase 1: Reorder Overview sections in template

1. Write E2E test: verify page order is metrics → chart → health → achievements → gains
2. Reorder `summary.html.j2` `.page-stack` children to new order
3. Move Portfolio Health (`health_score` include or inline) between chart and achievements

### Phase 2: Unify milestones into achievements

4. Write test: milestones render as cards inside achievements grid (no separate strip)
5. Remove `milestonesSection` / `milestonesStrip` / `milestonesList` from template
6. Modify `updateMilestones()` in `summary.js` to produce achievement-style card HTML
7. Inject milestone cards into `achievementsGrid` alongside achievement cards

### Phase 3: Achievements toggle

8. Write test: toggle button hides/shows achievements section, persists in localStorage
9. Add toggle button markup above achievements section in template
10. Implement toggle JS: click handler, localStorage read/write, initial state = visible
11. Ensure toggle does NOT affect Portfolio Value chart visibility

### Phase 4: Relocate Top Movers to Positions tab

12. Write test: Top Movers does not appear on Overview; appears on Positions below table
13. Remove `topMoversSection` from `summary.html.j2`
14. Add Top Movers HTML to `positions.html.j2` below the positions table
15. Move Top Movers rendering logic from `summary.js` to `positions.js`

### Phase 5: Secondary metrics default collapsed

16. Write test: secondary metrics panel is collapsed on page load
17. Ensure `overviewMetricsToggle` aria-expanded defaults to `false` and panel is hidden
18. Verify "Show more metrics" toggle still works to expand/collapse

## Requirement Coverage Matrix

| PRD Requirement | Spec Section | Test Coverage |
|---|---|---|
| 1. Metrics at top | Phase 1, task 1-2 | E2E: first section is metrics |
| 2. Secondary metrics collapsed | Phase 5, task 16-18 | E2E: panel hidden on load |
| 3. Chart below metrics | Phase 1, task 2 | E2E: chart follows metrics |
| 4. Health below chart | Phase 1, task 3 | E2E: health follows chart |
| 5. Achievements below health | Phase 1, task 2 | E2E: achievements follow health |
| 6. Toggle controls achievements only | Phase 3, task 8-11 | E2E: toggle hides achievements, chart stays |
| 7. No duplicate achievements | Phase 2, task 5-7 | E2E: single achievements grid, no strip |
| 8. Milestones as achievement cards | Phase 2, task 6-7 | E2E: milestone items in achievements grid |
| 9. Top Movers removed from Overview | Phase 4, task 12-13 | E2E: no movers section on Overview |
| 10. Top Movers in Positions below table | Phase 4, task 14-15 | E2E: movers section in Positions tab |
| 11. Gains/Benchmark below achievements | Phase 1, task 2 | E2E: gains section after achievements |

## Acceptance Criteria Verification

| Criterion | Verification |
|---|---|
| Page order: banners → metrics → chart → health → achievements → gains | E2E test checks DOM order of `data-role` elements |
| Secondary metrics collapsed on load | E2E test checks `aria-expanded="false"` and panel `display:none` |
| Achievements toggle hides grid, chart unaffected | E2E test: click toggle → achievements hidden, canvas still visible |
| Milestones render as achievement cards | E2E test: `.ach-grid` contains milestone items, no `.milestones-strip` exists |
| No Top Movers on Overview | E2E test: `[data-role="topMoversSection"]` absent from `#summary-widget` |
| Top Movers in Positions below table | E2E test: movers section exists after positions table |
| No duplicate achievements | E2E test: only one `[data-role="achievementsSection"]` in DOM |

## Dependencies

- No external dependencies
- Existing achievement/milestone data pipeline unchanged
- Health score widget already exists (just needs repositioning)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Dashboard widget system conflicts with hardcoded order | Med | Low | Widget templates are just containers; order is controlled by page-stack in summary.html.j2 |
| Top Movers JS has implicit coupling to summary.js scope | Low | Med | Audit data dependencies before moving; may need to expose helper functions |
| localStorage toggle state conflicts with dashboard customize mode | Low | Low | Use distinct key prefix; customize mode already has its own storage |

## Architecture Decision Records

### ADR-1: Pure Template Reorder vs JS-driven Layout

**Context:** The overview layout could be restructured either by reordering HTML in the Jinja template or by using JS to dynamically reposition DOM elements.

**Decision:** Pure template reorder (modify `summary.html.j2` directly).

**Rationale:** The page-stack is static HTML rendered server-side. JS repositioning would add complexity, flash of unstyled content, and fragility. Template reorder is simpler, faster, and matches existing patterns.

**Consequences:** Straightforward implementation; no runtime layout shifts.

### ADR-2: Milestones Rendering Approach

**Context:** Milestones currently render via `updateMilestones()` as a separate strip. They need to become achievement cards.

**Decision:** Modify `updateMilestones()` to generate achievement card HTML and append to `achievementsGrid`.

**Rationale:** Reuses existing `_renderAchievementCard` or similar markup. Single rendering location. No new component needed.

**Consequences:** `updateMilestones()` becomes a data transformer that feeds into the achievements renderer.

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
| Template reorder vs JS layout | Template reorder | Simpler, no FOUC, matches patterns | 2026-06-07 |
| Milestones rendering | Append to achievements grid | Single location, reuse card markup | 2026-06-07 |
