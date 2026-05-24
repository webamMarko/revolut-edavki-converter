# Technical Specification: Custom Dashboard

**Epic:** SAA-88
**PRD:** specs/custom-dashboard-prd.md
**Created:** 2026-05-24
**Status:** Ready for Review
**Confidence:** 90%

## Overview

Add a customizable "My Dashboard" tab to the report page where premium/admin users can drag, drop, resize, and arrange widget tiles sourced from existing report sections. The dashboard layout is persisted per-user in SQLite and rendered using Gridstack.js (CDN-loaded, no build system changes). First-time users see a sensible default layout. An edit-mode toggle in the dashboard header enables grid manipulation and a slide-out widget picker panel.

## Architecture

### System Context

The custom dashboard lives entirely within the existing report page (`/report`). No new routes are needed for the page itself. Two new API endpoints handle layout persistence. Widget content is rendered server-side via existing Jinja2 section templates — the same `{% include %}` mechanism already used in `report.html.j2`. The Gridstack.js library is loaded via CDN alongside Chart.js.

```
Browser                          Server (Flask)
  │                                │
  ├─ GET /report ──────────────────┤ serve_report() renders report.html.j2
  │   (includes My Dashboard tab)  │   with dashboard_layout in D global
  │                                │
  ├─ PUT /api/dashboard-layout ────┤ save_dashboard_layout() → users.db
  │   { widgets: [...] }           │
  │                                │
  └─ GET /api/dashboard-layout ────┤ get_dashboard_layout() → users.db
      → { widgets: [...] }         │
```

### Key Components

**Backend (Python):**

| Component | File | Responsibility |
|-----------|------|----------------|
| `save_dashboard_layout()` | `src/web/api.py` | PUT /api/dashboard-layout — validates and persists layout JSON |
| `get_dashboard_layout()` | `src/web/api.py` | GET /api/dashboard-layout — returns saved layout or default |
| DB migration | `src/users.py` | Add `dashboard_layout` column to `users` table |
| Template integration | `src/web/portfolio.py` | Inject `dashboard_layout` into template data |

**Frontend (Jinja2 + JS):**

| Component | File | Responsibility |
|-----------|------|----------------|
| Dashboard page | `src/templates/sections/dashboard.html.j2` | New section template with Gridstack grid container |
| Widget picker panel | (inline in dashboard.html.j2) | Slide-out panel listing available widgets with add buttons |
| Dashboard JS | `src/templates/assets/dashboard.js` | Gridstack init, edit mode toggle, save/load, widget lifecycle |
| Nav tab | `src/templates/sections/header.html.j2` | Add "My Dashboard" tab entry |

### Data Model

**Users table migration** — add column to existing `users` table in `_system/users.db`:

```sql
ALTER TABLE users ADD COLUMN dashboard_layout TEXT DEFAULT NULL;
```

The `dashboard_layout` column stores a JSON string:

```json
{
  "widgets": [
    { "id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2 },
    { "id": "health-score", "x": 4, "y": 0, "w": 4, "h": 2 },
    { "id": "summary",      "x": 8, "y": 0, "w": 4, "h": 4 },
    { "id": "charts",       "x": 0, "y": 2, "w": 8, "h": 4 },
    { "id": "positions",    "x": 0, "y": 6, "w": 12, "h": 4 }
  ]
}
```

Grid is 12 columns. Each widget has: `id` (maps to section template), `x`, `y` (grid position), `w`, `h` (grid size in columns/rows).

**Widget Registry** — hardcoded map of widget ID → metadata:

| Widget ID | Label | Template | Default Size (w×h) | Min Size |
|-----------|-------|----------|---------------------|----------|
| `quick-glance` | Quick Glance | sections/quick_glance.html.j2 | 4×2 | 3×2 |
| `health-score` | Health Score | sections/health_score.html.j2 | 4×2 | 3×2 |
| `summary` | Summary | sections/summary.html.j2 | 6×4 | 4×3 |
| `charts` | Charts | sections/charts.html.j2 | 8×5 | 6×4 |
| `positions` | Positions | sections/positions.html.j2 | 12×4 | 6×3 |
| `dividends` | Dividends | sections/dividends.html.j2 | 6×4 | 4×3 |
| `projections` | Projections | sections/projections.html.j2 | 6×4 | 4×3 |
| `notes` | Notes | sections/notes.html.j2 | 6×3 | 4×2 |
| `real-estate` | Real Estate | sections/real_estate.html.j2 | 6×4 | 4×3 |
| `risk` | Risk | sections/risk.html.j2 | 6×4 | 4×3 |
| `dca-strategy` | DCA Strategy | sections/dca_strategy.html.j2 | 6×4 | 4×3 |
| `tax-summary` | Tax Summary | sections/tax.html.j2 | 8×5 | 6×4 |
| `tax-calendar` | Tax Calendar | sections/year_end_calendar.html.j2 | 6×4 | 4×3 |
| `smart-sell` | Smart Sell | sections/smart_sell.html.j2 | 6×4 | 4×3 |
| `tax-wizard` | Tax Wizard | sections/tax_wizard.html.j2 | 6×4 | 4×3 |
| `transactions` | History | sections/transactions.html.j2 | 12×4 | 6×3 |

### API Contracts

**PUT /api/dashboard-layout**

Save the user's dashboard layout. Requires premium/admin role.

Request:
```json
{
  "widgets": [
    { "id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2 },
    { "id": "charts", "x": 0, "y": 2, "w": 8, "h": 5 }
  ]
}
```

Validation:
- `widgets` is an array of 0-16 items
- Each widget `id` must be in the widget registry
- `x`, `y`, `w`, `h` are non-negative integers
- `w` ≤ 12 (grid width), `h` ≤ 8 (reasonable max height)
- No duplicate widget IDs

Response: `200 OK` with `{ "status": "ok" }`

**GET /api/dashboard-layout**

Returns the user's saved layout, or the default layout if none saved.

Response:
```json
{
  "widgets": [...],
  "isDefault": true
}
```

## Implementation Plan

### Phase 1: Backend — DB Migration & API

1. Add `dashboard_layout` column to users table with migration
2. Implement GET/PUT `/api/dashboard-layout` endpoints
3. Define the widget registry as a Python dict
4. Inject dashboard layout into report template data

### Phase 2: Frontend — Dashboard Tab & Grid

1. Add "My Dashboard" nav tab in header.html.j2
2. Create dashboard.html.j2 section template with Gridstack container
3. Add Gridstack.js CDN script and CSS to report.html.j2
4. Implement grid initialization from saved layout
5. Render widget content inside grid items using existing section templates

### Phase 3: Edit Mode & Widget Picker

1. Add edit mode toggle button (pencil icon) in dashboard header
2. Implement slide-out widget picker panel (right side, bottom sheet on mobile)
3. Enable Gridstack drag/resize in edit mode only
4. Add remove button on each widget tile in edit mode
5. Auto-save layout on edit mode exit (PUT /api/dashboard-layout)

### Phase 4: Polish & Mobile

1. Responsive grid: collapse to 1-column on mobile viewports
2. Default layout for first-time users (Quick Glance + Summary + Charts + Positions)
3. Empty state banner: "This is your default layout — tap the pencil icon to customize"
4. Widget overflow handling (scrollable content within fixed grid tiles)

### TDD Task List

#### Phase 1: Backend

1. **Test:** Write test for `dashboard_layout` column migration — verify column exists after migration
2. **Implement:** Add migration logic in `src/users.py` to ALTER TABLE
3. **Test:** Write test for PUT /api/dashboard-layout — valid payload saves, invalid rejects (bad widget ID, too many widgets, negative coords)
4. **Implement:** Add `save_dashboard_layout()` in `src/web/api.py`
5. **Test:** Write test for GET /api/dashboard-layout — returns saved layout or default
6. **Implement:** Add `get_dashboard_layout()` in `src/web/api.py`
7. **Test:** Write test for role gating — guest gets 403, premium/admin get 200
8. **Implement:** Add `_require_role('premium', 'admin')` guards

#### Phase 2: Frontend

9. **Test:** E2E test — "My Dashboard" tab visible for premium user, hidden for guest
10. **Implement:** Add nav tab in header.html.j2
11. **Test:** E2E test — clicking "My Dashboard" tab shows dashboard page with grid
12. **Implement:** Create dashboard.html.j2 with Gridstack container, add CDN scripts
13. **Test:** E2E test — default layout renders 4 widgets (Quick Glance, Summary, Charts, Positions)
14. **Implement:** Grid initialization JS, default layout, widget rendering

#### Phase 3: Edit Mode

15. **Test:** E2E test — pencil icon toggles edit mode, grid items become draggable
16. **Implement:** Edit mode toggle button and Gridstack enable/disable
17. **Test:** E2E test — widget picker panel opens, lists all available widgets
18. **Implement:** Slide-out widget picker panel
19. **Test:** E2E test — adding a widget from picker places it on grid
20. **Implement:** Widget add flow (picker click → Gridstack addWidget)
21. **Test:** E2E test — removing a widget in edit mode removes it from grid
22. **Implement:** Remove button on widget tiles
23. **Test:** E2E test — exiting edit mode saves layout (verify via GET API)
24. **Implement:** Auto-save on edit mode exit

#### Phase 4: Mobile & Polish

25. **Test:** E2E test — dashboard renders in single column on mobile viewport
26. **Implement:** Gridstack column responsiveness config
27. **Test:** E2E test — first-time user sees default layout with banner
28. **Implement:** Default layout + banner logic

## Requirement Coverage Matrix

| PRD Requirement | Spec Section | Test Coverage |
|---|---|---|
| R1: One custom dashboard with drag-and-drop grid | Architecture, Phase 2-3 | E2E tests #11, #15-16 |
| R2: Resizable tiles placed freely on grid | Gridstack.js config, Phase 3 | E2E test #15 |
| R3: "My Dashboard" tab in report nav | Phase 2, header.html.j2 | E2E test #9 |
| R4: Config persisted per user in DB | Data Model, API Contracts | Unit tests #1-6 |
| R5: Premium/admin access only | API guards | Unit test #7, E2E test #9 |
| R6: Same data pipeline as report page | Architecture (server-side render) | E2E test #13 |

## Acceptance Criteria Verification

| AC | Verification Method |
|---|---|
| AC1: "My Dashboard" tab for premium/admin | E2E test #9: check tab presence per role |
| AC2: Empty/default dashboard state | E2E test #13, #27: verify default layout renders |
| AC3: Edit mode with add/remove/resize/reposition | E2E tests #15-22: full edit mode workflow |
| AC4: Widget content matches report sections | E2E test #13: visual comparison of widget vs section |
| AC5: Layout persists across sessions | E2E test #23: save, reload page, verify layout restored |
| AC6: Desktop and mobile | E2E test #25: mobile viewport single-column |

## Dependencies

| Dependency | Type | Status |
|---|---|---|
| Gridstack.js v10+ | CDN library | Available at cdn.jsdelivr.net |
| Existing section templates | Internal | Already exist in src/templates/sections/ |
| Users DB | Internal | Existing, needs migration |
| Chart.js (already loaded) | CDN library | Already in report.html.j2 |

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Section templates have page-level assumptions (e.g. global D variable, sibling selectors) | High | Medium | Wrap each widget in an isolated container; verify each section works standalone |
| Gridstack.js CDN unavailable | Low | Low | Pin specific version; could bundle as fallback |
| Layout JSON grows large | Low | Low | Max 16 widgets, JSON is small (~500 bytes) |
| Chart.js re-initialization when widgets are added/removed | Medium | Medium | Destroy and recreate chart instances on grid change events |
| Mobile drag-and-drop UX is poor | Medium | Medium | Disable drag on mobile; allow reorder via up/down buttons instead |

## Architecture Decision Records

### ADR-1: Grid Library Selection

**Context:** The custom dashboard needs a drag-and-drop grid with snap-to-grid, resize handles, and layout serialization. The app uses CDN-loaded libraries (no build system).

**Decision:** Gridstack.js (CDN)

**Rationale:** Purpose-built for widget dashboards with built-in save()/load(), resize handles, snap-to-grid, and collision detection. Follows the same CDN pattern as Chart.js. Avoids 500+ lines of custom drag/resize code that CSS Grid + vanilla JS would require. Muuri lacks built-in resize and layout serialization.

**Consequences:** ~45kb additional JS via CDN. Layout serialization maps directly to our JSON DB column.

### ADR-2: Widget Content Rendering Strategy

**Context:** Widgets must display the same content as existing report sections. Two approaches: server-side (include all sections in initial HTML, show/hide per layout) or client-side (lazy-load widget HTML via AJAX).

**Decision:** Server-side rendering — include all section templates in the initial page, wrap each in a hidden container, and move DOM nodes into Gridstack tiles based on the saved layout.

**Rationale:** All section data is already computed and injected as the `D` global by `serve_report()`. No new API endpoints needed. Avoids complexity of partial HTML rendering endpoints. The report page already includes all sections (just hides inactive tabs). Performance impact is negligible since the HTML is already generated.

**Consequences:** All 16 section templates are included in the page HTML regardless of which widgets are active. This is the same pattern as the current tab-based report page. Widgets that aren't placed simply remain hidden.

### ADR-3: Edit Mode UX

**Context:** Users need to enter a mode where they can add, remove, resize, and reposition widgets.

**Decision:** Pencil icon button in dashboard header toggles edit mode. Widget picker is a slide-out panel from the right (bottom sheet on mobile).

**Rationale:** Pencil icon is consistent with existing UI patterns (e.g. notes edit). Slide-out panel keeps the grid visible for spatial context while browsing widgets. FAB feels out of place in a desktop-first dark dashboard. Context menus are undiscoverable on mobile.

**Consequences:** Need edit mode state management in JS. Gridstack `enable()`/`disable()` controls drag/resize. Widget picker panel is a CSS slide-out with transform transition.

### ADR-4: Default Layout for New Users

**Context:** First-time users have no saved layout.

**Decision:** Pre-populated default layout with Quick Glance, Summary, Charts, and Positions widgets, plus a subtle banner explaining customization.

**Rationale:** Users see immediate value and learn the widget concept by example. A blank "Get Started" state creates friction and requires users to already understand available widgets.

**Consequences:** Default layout JSON defined as a constant in Python. Banner dismissed on first edit mode entry. `isDefault` flag in API response lets frontend show/hide the banner.

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
| Grid library | Gridstack.js (CDN) | Purpose-built for dashboards, save/load built-in, CDN pattern matches Chart.js | 2026-05-24 |
| Widget rendering | Server-side (DOM node move) | All data already in page via D global, no new endpoints needed | 2026-05-24 |
| Edit mode UX | Pencil icon toggle + slide-out picker | Consistent with existing UI, keeps grid visible | 2026-05-24 |
| Default layout | Pre-populated with 4 core widgets | Immediate value, learn by example | 2026-05-24 |
| Shareability | Out of scope for v1 | Keep scope small, can add later | 2026-05-24 |
| Per-widget scope filtering | Out of scope for v1 | Complexity vs value tradeoff | 2026-05-24 |
