# Technical Specification: Multi-portfolio Support

**Epic:** SAA-20
**PRD:** specs/multi-portfolio.md
**Created:** 2026-05-23
**Status:** Draft
**Confidence:** 90%

## Overview

Add multi-portfolio support so each user can manage up to 5 named portfolios within their existing `portfolio.db`. A `portfolios` table stores portfolio metadata, and all per-portfolio tables gain a `portfolio_id` foreign key. The active portfolio is tracked in the user's session (users.db). A dropdown in the nav header lets users switch portfolios, and all analytics/tax/report/import views are scoped to the active portfolio. Existing users are auto-migrated to a default "Main" portfolio via a schema v10 migration.

## Architecture

### System Context

```
Browser
  │
  ├── Nav header: portfolio switcher dropdown (GET /api/portfolios, POST /api/switch-portfolio)
  ├── Settings page: CRUD portfolios (POST/PATCH/DELETE /api/portfolios)
  └── All existing views: scoped by active portfolio_id from session
        │
        ▼
  Web layer (src/web/)
  ├── auth.py: get_session() now returns active_portfolio_id
  ├── portfolio.py: portfolio_conn() unchanged, but queries filter by portfolio_id
  └── All route handlers: pass portfolio_id to analytics/tax/import
        │
        ▼
  DB layer (src/db.py)
  ├── portfolio.db: schema v10 adds portfolios table + portfolio_id columns
  └── users.db: sessions table gains active_portfolio_id column
```

### Key Components

**1. Database migration (src/db.py)**
- New `portfolios` table in portfolio.db
- Add `portfolio_id` column to 8 tables
- Backfill existing data to default portfolio (id=1)
- Schema version 9 → 10

**2. Session extension (src/users.py)**
- Add `active_portfolio_id` column to `sessions` table
- Update `get_session()` to return `active_portfolio_id`
- Add `set_active_portfolio()` function
- Default to portfolio id=1 when session has no active portfolio

**3. Portfolio CRUD API (src/web/portfolio.py or new src/web/portfolios.py)**
- `GET /api/portfolios` — list user's portfolios
- `POST /api/portfolios` — create portfolio (enforce max 5)
- `PATCH /api/portfolios/{id}` — rename
- `DELETE /api/portfolios/{id}` — hard delete (block default)
- `POST /api/switch-portfolio` — set active portfolio in session

**4. Nav header portfolio switcher (src/templates/partials/nav.html.j2)**
- Dropdown in header-right zone, before username
- Shows active portfolio name with chevron
- Lists all portfolios, highlights active one
- JavaScript to handle switching via POST /api/switch-portfolio

**5. Query scoping (src/analytics.py, src/tax.py, src/importer.py, etc.)**
- All SELECT/INSERT queries on portfolio-scoped tables must include `portfolio_id`
- 14 files touch transactions table — all must be audited

### Data Model

**New table in portfolio.db:**
```sql
CREATE TABLE IF NOT EXISTS portfolios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    slug       TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(slug)
);
```

**New column on sessions table (users.db):**
```sql
ALTER TABLE sessions ADD COLUMN active_portfolio_id INTEGER NOT NULL DEFAULT 1;
```

**Tables receiving portfolio_id (portfolio.db):**
```sql
-- All get: portfolio_id INTEGER NOT NULL DEFAULT 1 REFERENCES portfolios(id)
-- Tables: transactions, import_log, real_estate_properties, investment_notes,
--         cached_analytics, cached_tax_reports, dividend_schedule, goals
```

**Tables NOT modified (shared data):**
- `daily_prices` — market data shared across portfolios
- `fx_rates` — FX data shared across portfolios
- `metadata` — DB-level config

### API Contracts

**GET /api/portfolios**
```json
Response 200: {
  "portfolios": [
    {"id": 1, "name": "Main", "slug": "main", "is_default": true, "created_at": "..."},
    {"id": 2, "name": "Trading", "slug": "trading", "is_default": false, "created_at": "..."}
  ],
  "active_portfolio_id": 1,
  "max_portfolios": 5
}
```

**POST /api/portfolios**
```json
Request: {"name": "Trading"}
Response 201: {"id": 2, "name": "Trading", "slug": "trading", "is_default": false}
Response 409: {"error": "Maximum of 5 portfolios reached"}
```

**PATCH /api/portfolios/{id}**
```json
Request: {"name": "New Name"}
Response 200: {"id": 2, "name": "New Name", "slug": "new-name"}
```

**DELETE /api/portfolios/{id}**
```json
Response 200: {"deleted": true}
Response 400: {"error": "Cannot delete default portfolio"}
```

**POST /api/switch-portfolio**
```json
Request: {"portfolio_id": 2}
Response 200: {"active_portfolio_id": 2}
```

## Implementation Plan

### Phase 1: Database & Session Layer
1. Schema v10 migration — portfolios table, portfolio_id columns, backfill
2. Session extension — active_portfolio_id in sessions table
3. Portfolio CRUD functions in db.py or new portfolios.py module

### Phase 2: API & Web Routes
4. Portfolio CRUD API endpoints
5. Switch-portfolio endpoint
6. Update get_session() to include active_portfolio_id

### Phase 3: Query Scoping
7. Audit and update all queries in analytics.py
8. Audit and update all queries in tax.py
9. Audit and update all queries in importer.py
10. Audit and update all queries in remaining modules (price_fetcher.py, health_score.py, harvest.py, html_report.py, email_reports.py, dividend_forecast.py, analytics_cache.py, cli.py)
11. Update import wizard to use active portfolio_id

### Phase 4: UI
12. Portfolio switcher dropdown in nav header
13. Portfolio CRUD UI in Settings page
14. Confirmation dialog for portfolio deletion

### Phase 5: Edge Cases & Polish
15. Portfolio-scoped shared links (portfolio_shares)
16. Cron sync across all portfolios
17. Demo DB handling (single default portfolio, no switcher for guests)

### TDD Task List

**Phase 1: Database & Session**

1. Write test: schema v10 migration creates portfolios table with correct columns
2. Write test: migration inserts default "Main" portfolio with id=1, is_default=1
3. Write test: migration adds portfolio_id column to transactions, import_log, real_estate_properties, investment_notes, cached_analytics, cached_tax_reports, dividend_schedule, goals
4. Write test: existing transaction rows get portfolio_id=1 after migration
5. Write test: daily_prices, fx_rates, metadata tables do NOT have portfolio_id
6. Implement schema v10 migration in `_init_schema()`
7. Refactor: verify migration is idempotent

8. Write test: create_portfolio() inserts row and returns portfolio dict
9. Write test: create_portfolio() rejects when user already has 5 portfolios
10. Write test: create_portfolio() generates unique slug from name
11. Write test: rename_portfolio() updates name and slug
12. Write test: delete_portfolio() removes portfolio and all scoped data (transactions, goals, etc.)
13. Write test: delete_portfolio() rejects deletion of default portfolio
14. Write test: list_portfolios() returns all portfolios for the DB
15. Implement portfolio CRUD functions

16. Write test: sessions table gains active_portfolio_id column
17. Write test: get_session() returns active_portfolio_id in session dict
18. Write test: set_active_portfolio() updates session's active_portfolio_id
19. Write test: new session defaults active_portfolio_id to user's default portfolio
20. Implement session extension in users.py

**Phase 2: API Routes**

21. Write test: GET /api/portfolios returns portfolio list with active_portfolio_id
22. Write test: POST /api/portfolios creates portfolio and returns 201
23. Write test: POST /api/portfolios returns 409 when limit reached
24. Write test: PATCH /api/portfolios/{id} renames portfolio
25. Write test: DELETE /api/portfolios/{id} deletes non-default portfolio
26. Write test: DELETE /api/portfolios/{id} returns 400 for default portfolio
27. Write test: POST /api/switch-portfolio updates session and returns new active_id
28. Implement portfolio API routes

**Phase 3: Query Scoping**

29. Write test: importer.py INSERT includes portfolio_id
30. Write test: analytics.py queries filter by portfolio_id
31. Write test: tax.py queries filter by portfolio_id
32. Write test: cached_analytics includes portfolio_id in cache key
33. Audit and update all 14 files that query transactions table
34. Refactor: verify no query on scoped tables lacks portfolio_id filter

**Phase 4: UI**

35. Write test: nav.html.j2 renders portfolio switcher for premium/admin users
36. Write test: nav.html.j2 does NOT render switcher for guests
37. Write test: settings page renders portfolio CRUD section
38. Implement portfolio switcher dropdown in nav template
39. Implement portfolio CRUD UI in settings page
40. Implement delete confirmation dialog

**Phase 5: Edge Cases**

41. Write test: portfolio_shares records are scoped to portfolio_id
42. Write test: shared link resolves to correct portfolio regardless of active portfolio
43. Write test: cron sync iterates all portfolios per user
44. Implement portfolio-scoped shared links
45. Update cron sync to handle multiple portfolios

## Requirement Coverage Matrix

| PRD Requirement | Spec Section | Test Coverage |
|---|---|---|
| R1: Up to 5 named portfolios in portfolios table | Data Model, Phase 1 | Tests 1, 8-10 |
| R2: portfolio_id column on all scoped tables | Data Model, Phase 1 | Tests 3-5 |
| R3: Default "Main" portfolio auto-created, existing data backfilled | Phase 1 migration | Tests 2, 4 |
| R4: Create/rename/delete from Settings | Phase 2 API, Phase 4 UI | Tests 21-26, 37-40 |
| R5: Dropdown in nav header-right | Phase 4 UI | Tests 35-36, 38 |
| R6: All views scoped to active portfolio | Phase 3 query scoping | Tests 29-34 |
| R7: Cron sync all portfolios | Phase 5 | Tests 43, 45 |
| R8: Consolidated view deferred | N/A (not implemented) | N/A |
| R9: Imports target active portfolio | Phase 3 | Test 29 |
| R10: Hard delete with confirmation | Phase 1, Phase 4 | Tests 12-13, 40 |

## Acceptance Criteria Verification

| AC | Verification |
|---|---|
| AC1: Create second portfolio, import, see separate analytics | E2E test: create portfolio, switch, import CSV, verify analytics show only that portfolio's data |
| AC2: Switching updates all views instantly | E2E test: switch portfolio via dropdown, verify report/analytics/status endpoints return scoped data |
| AC3: Existing users auto-migrated to "Main" | Integration test: open DB with pre-v10 data, verify migration creates "Main" portfolio and backfills |
| AC4: Limit of 5 enforced | Unit test: attempt 6th portfolio creation, verify 409 error |
| AC5: Delete removes all transaction data | Integration test: delete portfolio, verify transactions/goals/etc. with that portfolio_id are gone |
| AC6: Shared links scoped to source portfolio | Integration test: create share from portfolio 2, access share, verify data comes from portfolio 2 |
| AC7: Default portfolio cannot be deleted | Unit test: attempt delete of is_default=1 portfolio, verify 400 error |
| AC8: Import uses active portfolio | Integration test: switch to portfolio 2, import CSV, verify transactions.portfolio_id = 2 |

## Dependencies

- No external dependencies — all changes are internal to the existing codebase
- Requires SQLite schema migration (v9 → v10)
- portfolio_shares table in users.db needs portfolio_id column added

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Missed portfolio_id filter in a query causes cross-portfolio data leakage | High | Medium | Systematic audit of all 14 files that query transactions; grep-based CI check for unfiltered queries |
| Migration fails on large existing DBs | Medium | Low | Test migration on copy of production data; use single transaction for atomicity |
| Session loses active_portfolio_id (stale session) | Low | Low | Default to user's default portfolio (is_default=1) when active_portfolio_id is missing |
| Cached analytics/tax reports serve wrong portfolio | Medium | Medium | Include portfolio_id in cache key; invalidate cache on portfolio switch |
| Slug collision on portfolio names | Low | Low | Generate slug with uniqueness suffix; UNIQUE constraint on slug column |

## Architecture Decision Records

### ADR-1: Single DB with portfolio_id Column

**Context:** Multi-portfolio data isolation requires either separate SQLite files per portfolio or a portfolio_id column added to tables within the existing single DB per user.

**Decision:** Single DB with portfolio_id column.

**Rationale:** User chose this approach. Keeps one DB file per user, avoids file management complexity, and shares market data tables (daily_prices, fx_rates) naturally without duplication. Trade-off: every query on scoped tables must include portfolio_id filter — requires systematic audit.

**Consequences:** All 14 files querying transactions must be audited. Cache keys must include portfolio_id. Migration must backfill existing rows atomically.

### ADR-2: Active Portfolio in Session

**Context:** Need to track which portfolio the user is currently viewing across requests.

**Decision:** Store `active_portfolio_id` in the sessions table (users.db).

**Rationale:** Co-located with existing session state (user_id, role, expires_at). Survives browser restarts. Works across tabs. Not editable by user (unlike cookies).

**Consequences:** `get_session()` must return active_portfolio_id. New `set_active_portfolio()` function needed. Default to is_default portfolio when session has no active_portfolio_id.

### ADR-3: Portfolio Switcher in Header-Right

**Context:** Need UI element for switching between portfolios.

**Decision:** Dropdown in header-right zone, next to username.

**Rationale:** Groups all user/account controls in one logical zone. Preserves the clean three-zone nav layout (brand | nav links | controls). Scales well on mobile.

**Consequences:** nav.html.j2 needs a portfolio-switcher div with dropdown menu. JavaScript for toggle + AJAX switch. Only shown for premium/admin users (guests see demo, no switching).

### ADR-4: Hard Delete for Portfolios

**Context:** When a user deletes a portfolio, should data be permanently removed or soft-deleted?

**Decision:** Hard delete with confirmation dialog.

**Rationale:** Simpler implementation, no orphaned data, no cleanup jobs. User is warned via confirmation dialog. Default portfolio is protected from deletion.

**Consequences:** DELETE cascades through all scoped tables (transactions, goals, etc.). UI must show clear warning. API must reject deletion of is_default=1 portfolio.

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
| Data isolation | Single DB with portfolio_id | User preference; shared market data | 2026-05-23 |
| Consolidated view | Defer to v2 | Reduces scope | 2026-05-23 |
| Max portfolios | 5 | Practical limit | 2026-05-23 |
| UI placement | Header-right dropdown | Groups controls, clean layout | 2026-05-23 |
| Deletion strategy | Hard delete + confirmation | Simple, no orphans | 2026-05-23 |
| Import target | Active portfolio | Simple UX | 2026-05-23 |
| Tables with portfolio_id | 8 tables (not daily_prices, fx_rates, metadata) | Shared vs scoped data | 2026-05-23 |
| Migration approach | Single-phase v10 | Atomic, no nullable gap | 2026-05-23 |
| Session tracking | active_portfolio_id in sessions table | Co-located with session state | 2026-05-23 |
