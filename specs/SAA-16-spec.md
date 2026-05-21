# Technical Specification: User Onboarding Flow

**Epic:** SAA-16
**PRD:** specs/SAA-16-prd.md
**Created:** 2026-05-21
**Status:** Ready for Review
**Confidence:** 92%

## Overview

Add a guided onboarding flow for new premium users in the WealthEagle portfolio analytics app. The implementation adds: (1) a multi-step modal wizard triggered on first login, (2) consistent empty states across all dashboard sections with inline import CTAs, (3) read-only demo data toggle for logged-in users, (4) background sync with toast notifications, and (5) a confetti celebration on first analytics load.

The app is a Python HTTP server (`src/web.py`) serving inline HTML/JS with SQLite databases. All new UI is client-side JS rendered in the existing SPA-style dashboard. No new backend framework or build tooling is introduced.

## Architecture

### System Context

```
User (browser)
  │
  ├─ GET /  → dashboard HTML (includes welcome_wizard.js, empty_states.js)
  ├─ POST /sync → _handle_sync (existing, now returns sync job status)
  ├─ GET /api/onboarding-status → new endpoint: returns {completed, hasData}
  ├─ POST /api/onboarding-complete → new endpoint: sets flag
  ├─ GET /api/demo-toggle → new endpoint: switches session to demo view
  └─ POST /upload, /import/* → existing import flow
```

### Key Components

**Backend (src/web.py):**
- `_handle_onboarding_status()` — returns `{completed: bool, hasData: bool, hasSync: bool}`
- `_handle_onboarding_complete()` — sets `onboarding_completed=1` in users.db
- `_handle_demo_toggle()` — toggles session between user DB and demo DB view
- Modified `_portfolio_conn()` — respects demo toggle for premium users

**Backend (src/users.py):**
- Add `onboarding_completed` column to users table schema
- Add `set_onboarding_completed(user_id)` function
- Add `get_onboarding_status(user_id)` function

**Frontend (src/templates/assets/):**
- `welcome_wizard.js` — new file: 4-step modal wizard (welcome → import → sync → celebration)
- `empty_states.js` — new file: reusable `renderEmptyState(containerId, section, message)` function
- `confetti.js` — new file: lightweight canvas confetti (~50 lines, no external dependency)
- `toast.js` — new file: non-blocking toast notification system
- Modified section JS files — each section calls `renderEmptyState()` when no data

**CSS (inline in dashboard HTML):**
- `.wizard-modal`, `.wizard-step`, `.wizard-overlay` — modal wizard styles
- `.empty-state-card` — unified empty state pattern
- `.toast-container`, `.toast` — toast notification styles
- `.confetti-canvas` — confetti overlay

### Data Model

**users table (src/users.py) — add column:**
```sql
ALTER TABLE users ADD COLUMN onboarding_completed INTEGER NOT NULL DEFAULT 0;
```

Migration: add column if not exists in `_init_db()`. Existing users get `0` (will see wizard on next visit unless they have data, in which case auto-complete).

**No new tables needed.** Demo toggle is session-level (stored in cookie/session, not persisted).

### API Contracts

**GET /api/onboarding-status**
- Auth: premium/admin required
- Response: `{"completed": false, "hasData": true, "hasSynced": true}`
- `hasData`: checks if user's portfolio.db has any transactions
- `hasSynced`: checks if prices exist for user's tickers

**POST /api/onboarding-complete**
- Auth: premium/admin required
- Response: `{"ok": true}`
- Side effect: sets `onboarding_completed=1` in users.db

**POST /api/demo-toggle**
- Auth: premium/admin required
- Body: `{"demo": true}` or `{"demo": false}`
- Response: `{"ok": true, "demo": true}`
- Side effect: sets `session["demo_view"]` flag; subsequent `_portfolio_conn()` calls return demo DB when true

**POST /sync (existing, modified)**
- No change to endpoint signature
- Returns `{"ok": true}` immediately (sync already runs synchronously — keep as-is, the wizard JS will call it and show a spinner/toast while waiting)

## Implementation Plan

### Phase 1: Backend — Onboarding State
1. Add `onboarding_completed` column to users table schema with migration
2. Add `get_onboarding_status()` and `set_onboarding_completed()` to users.py
3. Add `/api/onboarding-status` and `/api/onboarding-complete` endpoints to web.py
4. Add `/api/demo-toggle` endpoint and modify `_portfolio_conn()` to respect session demo flag

### Phase 2: Frontend — Toast & Confetti Utilities
5. Create `toast.js` — showToast(message, type, duration) function
6. Create `confetti.js` — launchConfetti() canvas animation
7. Add CSS for toast and confetti to dashboard HTML

### Phase 3: Frontend — Empty States
8. Create `empty_states.js` — renderEmptyState(containerId, sectionName, message) function
9. Integrate empty states into each dashboard section (summary, tax, analytics, charts, projections, dividends, report)
10. Each empty state shows icon + message + "Import CSV" button linking to /import

### Phase 4: Frontend — Welcome Wizard
11. Create `welcome_wizard.js` — 4-step modal wizard
12. Step 1 (Welcome): value prop message + "Import my data" / "Try demo data" buttons
13. Step 2 (Import): show brief message + "Go to Import" button → redirects to /import. After successful import, redirect back to dashboard where wizard auto-advances to step 3. Wizard state (current step) persisted in localStorage.
14. Step 3 (Sync): call POST /sync, show spinner with toast, auto-advance on completion
15. Step 4 (Celebration): confetti + portfolio highlights card + "View Dashboard" CTA
16. Wire wizard to check `/api/onboarding-status` on dashboard load; show if not completed
17. Add "Replay tour" option in help/settings menu

### Phase 5: Demo Data Toggle
18. Add "Try with demo data" button to wizard step 1 and empty states
19. Wire to POST /api/demo-toggle; reload dashboard with demo data
20. Show demo banner for premium users viewing demo data (extend existing guest banner logic)
21. Add "Switch to my portfolio" button in demo banner

### TDD Task List

Each task follows red-green-refactor:

**Backend:**
1. Test: `test_users_onboarding_column_exists` — verify schema has `onboarding_completed`
2. Implement: add column to schema + migration in `_init_db()`
3. Test: `test_get_onboarding_status` — returns correct status for new/existing users
4. Implement: `get_onboarding_status()` in users.py
5. Test: `test_set_onboarding_completed` — sets flag and persists
6. Implement: `set_onboarding_completed()` in users.py
7. Test: `test_api_onboarding_status_endpoint` — returns JSON with correct fields
8. Implement: `/api/onboarding-status` handler in web.py
9. Test: `test_api_onboarding_complete_endpoint` — sets flag via API
10. Implement: `/api/onboarding-complete` handler in web.py
11. Test: `test_api_demo_toggle` — toggles demo view in session
12. Implement: `/api/demo-toggle` handler + session demo flag
13. Test: `test_portfolio_conn_respects_demo_toggle` — returns demo DB when toggled
14. Implement: modify `_portfolio_conn()` to check session demo flag

**Frontend (E2E with Playwright):**
15. Test: `test_new_user_sees_wizard` — new user login triggers wizard modal
16. Implement: wizard modal launch logic in welcome_wizard.js
17. Test: `test_wizard_import_step` — file upload works in wizard context
18. Implement: wizard import step integration
19. Test: `test_wizard_completion_sets_flag` — completing wizard calls onboarding-complete API
20. Implement: wizard completion flow
21. Test: `test_empty_states_shown` — each section shows empty state when no data
22. Implement: empty state rendering across sections
23. Test: `test_demo_toggle_shows_demo_data` — demo button loads demo portfolio
24. Implement: demo toggle UI and integration
25. Test: `test_wizard_not_shown_after_completion` — wizard hidden for onboarded users
26. Implement: onboarding status check on dashboard load

## Requirement Coverage Matrix

| PRD Requirement | Spec Section | Test Coverage |
|---|---|---|
| R1 — Welcome Wizard | Phase 4, Tasks 15-20 | E2E: wizard flow, completion flag |
| R2 — Read-Only Demo Data | Phase 5, Tasks 23-24 | E2E: demo toggle, Unit: portfolio_conn |
| R3 — Consistent Empty States | Phase 3, Tasks 21-22 | E2E: empty states per section |
| R4 — Wizard Trigger & State | Phase 1, Tasks 1-10 | Unit: users.py, API endpoints |
| R5 — Background Sync with Notification | Phase 2+4, Tasks 5-6, 14 | E2E: sync during wizard |
| R6 — Confetti Celebration | Phase 2+4, Task 6, 20 | E2E: wizard final step |

## Acceptance Criteria Verification

| AC | Verification Method |
|---|---|
| 1. New user sees wizard on first visit | E2E: test_new_user_sees_wizard |
| 2. Wizard has 4 steps | E2E: test_wizard_steps_navigation |
| 3. Wizard dismissible, flag set | E2E: test_wizard_dismiss_sets_flag |
| 4. Demo data accessible via button | E2E: test_demo_toggle_shows_demo_data |
| 5. Demo banner shown | E2E: test_demo_banner_visible |
| 6. Empty states with import CTA | E2E: test_empty_states_shown |
| 7. Toast notifications for sync | E2E: test_sync_toast_notifications |
| 8. Confetti + highlights on completion | E2E: test_wizard_celebration_step |
| 9. Dashboard shows real data after onboarding | E2E: test_post_onboarding_dashboard |
| 10. Under 3 minutes signup to analytics | Manual timing test |
| 11. Wizard replayable from help menu | E2E: test_replay_wizard |
| 12. Flag in users.db | Unit: test_users_onboarding_column_exists |

## Dependencies

- Existing import wizard (`/import` routes) — reused, not modified
- Existing sync endpoint (`POST /sync`) — used as-is
- Existing demo DB (`data/_demo/portfolio.db`) — read by demo toggle
- Existing session/auth system — extended with demo_view flag

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Sync takes >30s, user abandons wizard | Medium | Medium | Toast shows progress; user can browse during sync |
| Demo DB missing on fresh deploy | Low | Low | Check file exists; show "Demo unavailable" gracefully |
| SQLite migration fails for existing users | High | Low | Use `ALTER TABLE IF NOT EXISTS` pattern; test migration |
| Confetti animation janky on mobile | Low | Medium | Keep animation simple; 2s max; test on mobile viewport |

## Architecture Decision Records

### ADR-1: Wizard as Client-Side Modal

**Context:** The wizard needs to guide users through import/sync. Could be server-rendered pages or client-side JS modal.

**Decision:** Client-side JS modal overlay on the dashboard.

**Rationale:** Consistent with existing tour (`onboarding.js`). No new routes needed. Lighter feel, user stays on dashboard. Import step can either embed the existing import page or redirect to it.

**Consequences:** All wizard logic is in JS. State management via fetch calls to `/api/onboarding-status`.

### ADR-2: Demo Toggle via Session Flag

**Context:** Premium users need to view demo data without copying the DB.

**Decision:** Session-level `demo_view` flag toggled via API. `_portfolio_conn()` returns demo DB when flag is set.

**Rationale:** No data copying, no cleanup. Leverages existing demo DB infrastructure. Flag is ephemeral (session-scoped), so it resets on logout.

**Consequences:** Any session-based code that calls `_portfolio_conn()` automatically gets demo data when toggled. Write operations should be blocked in demo mode.

### ADR-3: Server-Side Onboarding Flag

**Context:** Need to track whether user has completed onboarding.

**Decision:** `onboarding_completed` column in users table.

**Rationale:** Persists across browsers/devices. Simple boolean. Auto-set on wizard completion or dismissal.

**Consequences:** Requires schema migration. Existing users default to `0` but should auto-complete if they already have data.

### ADR-4: Import Step via Redirect

**Context:** The wizard's import step needs to let users upload CSVs. The existing /import page has full upload, preview, and validation UI.

**Decision:** Redirect to /import page, then return to dashboard where wizard auto-advances.

**Rationale:** Fully reuses existing import page with zero duplication. Wizard state stored in localStorage survives the redirect. Simplest implementation with lowest maintenance cost.

**Consequences:** Wizard must persist its state in localStorage. After import success, /import page redirects to `/?onboarding=3` (or similar) so the wizard JS knows to resume at step 3.

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
| Wizard format | Modal overlay | Consistent with existing tour, lighter feel | 2026-05-21 |
| Demo data approach | Read-only shared DB via session toggle | No copying, no cleanup, simple | 2026-05-21 |
| Empty state CTAs | Inline import button per section | Reduces clicks, prominent CTA | 2026-05-21 |
| Sync UX | Background with toast notification | Non-blocking, user can browse | 2026-05-21 |
| Celebration | Confetti + highlights card | Delightful, shows immediate value | 2026-05-21 |
| Wizard trigger | Server-side onboarding_completed flag | Persists across devices | 2026-05-21 |
| Import step integration | Redirect to /import, return to wizard | Reuses existing page, no duplication, localStorage for state | 2026-05-21 |
