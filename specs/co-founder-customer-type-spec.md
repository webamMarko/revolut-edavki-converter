# Technical Specification: Co-Founder Customer Type

**Epic:** co-founder-customer-type
**PRD:** specs/co-founder-customer-type-prd.md
**Created:** 2026-05-23
**Status:** Ready for Review
**Confidence:** 92%

## Overview

This feature adds a new `cofounder` user role with a ticket/credit system for submitting bug reports and feature ideas. The implementation touches the user model (new role + credit columns), adds new database tables (tickets, ticket_comments, system_settings) in users.db, creates a new `web/tickets.py` route module, extends the admin settings page, integrates with Stripe for one-time purchase, Paperclip for AI ticket execution, and Resend for email notifications.

## Architecture

### System Context

```
Premium User ──Stripe Checkout──> Webhook ──> role upgrade to cofounder
                                                      │
Cofounder ──/tickets──> Create Ticket ──> Deduct Credit
                              │                    │
                              │              Paperclip API
                              │              (create issue)
                              │                    │
                              ▼                    ▼
                         tickets table      AI agent executes
                              │                    │
                              │              Status sync
                              ▼              (on-demand fetch)
                     Ticket Detail Page ◄──────────┘
                     + Comment Thread
                              │
                     Status Change ──> Resend email notification
```

### Key Components

| Component | File | Responsibility |
|-----------|------|----------------|
| User model changes | `src/users.py` | New `cofounder` role, credit columns, credit reset logic |
| Ticket routes | `src/web/tickets.py` | `/tickets` page, ticket CRUD, comment CRUD |
| Ticket DB functions | `src/tickets.py` | Ticket/comment data access, credit management |
| Admin settings | `src/web/admin.py` | Credit-to-token config, licence price config |
| Stripe upgrade | `src/web/admin.py` | Webhook handler for cofounder one-time payment |
| Paperclip integration | `src/tickets.py` | Create Paperclip issue on ticket submit, sync status |
| Email notifications | `src/tickets.py` | Send status-change emails via `email_service.py` |
| Templates | `src/templates/pages/tickets.html.j2`, `ticket_detail.html.j2` | Ticket list + detail UI |

### Data Model

All tables in `_system/users.db`:

```sql
-- Extend users table
ALTER TABLE users ADD COLUMN credits_remaining INTEGER NOT NULL DEFAULT 0;
ALTER TABLE users ADD COLUMN credits_last_reset TEXT;

-- Update role CHECK constraint
-- (SQLite requires table recreation for CHECK changes)
-- New CHECK: role IN ('guest', 'premium', 'admin', 'cofounder')

-- Tickets
CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    type            TEXT NOT NULL CHECK(type IN ('bug', 'idea')),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'in_progress', 'done')),
    paperclip_issue_id TEXT,
    status_synced_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ticket comments
CREATE TABLE IF NOT EXISTS ticket_comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id   INTEGER NOT NULL REFERENCES tickets(id),
    user_id     INTEGER NOT NULL REFERENCES users(id),
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- System settings (key-value)
CREATE TABLE IF NOT EXISTS system_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Default settings inserted on schema init:
-- ('cofounder_price_eur', '249')
-- ('bug_token_multiplier', '5000')
-- ('idea_token_multiplier', '10000')
-- ('credits_per_week', '100')
```

### API Contracts

#### Pages (GET)

| Route | Auth | Description |
|-------|------|-------------|
| `GET /tickets` | cofounder, admin | Ticket list (own for cofounder, all for admin) |
| `GET /tickets/{id}` | cofounder (own), admin | Ticket detail + comments |
| `GET /cofounder` | premium | "Become Co-Founder" landing page with Stripe button |

#### Actions (POST)

| Route | Auth | Description |
|-------|------|-------------|
| `POST /tickets` | cofounder | Create ticket (deducts 1 credit) |
| `POST /tickets/{id}/comments` | cofounder (own), admin | Add comment |
| `POST /tickets/{id}/status` | admin | Update ticket status (triggers email) |
| `POST /admin/settings` | admin | Update system settings (token multipliers, price) |
| `POST /cofounder/checkout` | premium | Create Stripe Checkout session |

#### Stripe Webhook

Existing `POST /webhook/stripe` extended to handle `checkout.session.completed` events where `metadata.purpose == 'cofounder_licence'`. On success: set user role to `cofounder`, set `credits_remaining = 100`, set `credits_last_reset` to now.

#### Paperclip Integration

On ticket creation, `POST /api/companies/{companyId}/issues` with:
```json
{
  "title": "[Bug|Idea] {ticket.title}",
  "description": "{ticket.description}",
  "assigneeAgentId": "{configured_agent_id}",
  "status": "todo"
}
```

Store returned `id` as `paperclip_issue_id`. On ticket detail view, if `status_synced_at` is older than 60 seconds, `GET /api/issues/{paperclip_issue_id}` and update local ticket status from Paperclip issue status mapping: `todo|in_progress` → `in_progress`, `done` → `done`.

## Implementation Plan

### Phase 1: Data Model & Role (Backend Foundation)

1. Write test: `cofounder` role accepted in user creation
2. Recreate users table with updated CHECK constraint adding `cofounder`
3. Write test: credits_remaining and credits_last_reset columns exist
4. Add migration logic in `users.py` schema init for new columns
5. Write test: `system_settings` table CRUD
6. Add system_settings table and default values in schema init
7. Write test: tickets table CRUD (create, read by user, read all)
8. Add tickets and ticket_comments tables in schema init

### Phase 2: Credit System

9. Write test: `ensure_credits()` resets to 100 if last_reset > 7 days ago
10. Implement `ensure_credits(user_id)` in `tickets.py`
11. Write test: `deduct_credit()` reduces balance, fails at 0
12. Implement `deduct_credit(user_id)` in `tickets.py`

### Phase 3: Ticket CRUD

13. Write test: `create_ticket()` creates row and deducts credit
14. Implement `create_ticket(user_id, type, title, description)`
15. Write test: `get_tickets(user_id)` returns own; `get_all_tickets()` returns all
16. Implement ticket query functions
17. Write test: `add_comment()` and `get_comments(ticket_id)`
18. Implement comment functions

### Phase 4: Web Routes & Templates

19. Create `src/web/tickets.py` with route handlers
20. Create `tickets.html.j2` — ticket list with create form, credit balance display
21. Create `ticket_detail.html.j2` — ticket detail with comment thread
22. Register routes in `server.py` (GET/POST /tickets, /tickets/{id}, /tickets/{id}/comments, /tickets/{id}/status)
23. Add "Tickets" nav link for cofounder/admin roles in base template

### Phase 5: Stripe Co-Founder Purchase

24. Write test: Stripe checkout session creation with cofounder metadata
25. Create `GET /cofounder` page with pricing and Stripe button
26. Implement `POST /cofounder/checkout` — create Stripe Checkout session
27. Write test: webhook upgrades role to cofounder on successful payment
28. Extend Stripe webhook handler for `cofounder_licence` purpose

### Phase 6: Admin Settings

29. Write test: admin can read/write system_settings
30. Add settings section to admin page (token multipliers, licence price, credits per week)
31. Implement `POST /admin/settings` handler
32. Write test: admin can update ticket status
33. Add status update button on admin ticket detail view

### Phase 7: Paperclip Integration

34. Write test: ticket creation calls Paperclip API (mock)
35. Implement Paperclip issue creation in `create_ticket()`
36. Write test: status sync fetches from Paperclip and updates local
37. Implement on-demand status sync in ticket detail handler

### Phase 8: Email Notifications

38. Write test: status change triggers email via Resend
39. Implement email notification in status update handler
40. Add email template for ticket status change

### Phase 9: Admin Role Management

41. Write test: admin can downgrade cofounder to premium
42. Extend existing `handle_admin_set_role` to support cofounder role transitions

## Requirement Coverage Matrix

| PRD Req# | Requirement | Spec Section | Test Coverage |
|----------|-------------|--------------|---------------|
| 1 | New `cofounder` role | Data Model, Phase 1 | Test: role CHECK accepts cofounder |
| 2 | All premium features | Web Routes (role check) | Test: cofounder accesses premium routes |
| 3 | 100 credits/week, no rollover | Credit System, Phase 2 | Test: ensure_credits resets weekly |
| 4 | 1 credit per ticket | Credit System, Phase 2 | Test: deduct_credit on create |
| 5 | Standalone /tickets page | Web Routes, Phase 4 | Test: GET /tickets serves page |
| 6 | Own tickets only; admin sees all | Ticket CRUD, Phase 3 | Test: get_tickets vs get_all_tickets |
| 7 | Stripe one-time payment | Stripe, Phase 5 | Test: webhook upgrades role |
| 8 | Admin token multiplier settings | Admin Settings, Phase 6 | Test: settings CRUD |
| 9 | Paperclip issue creation | Paperclip, Phase 7 | Test: create_ticket calls API |
| 10 | Minimal ticket fields | Data Model | Test: table schema |
| 11 | Email on status change | Email, Phase 8 | Test: status change sends email |
| 12 | Admin-configurable price | Admin Settings, Phase 6 | Test: price setting updates Stripe |
| 13 | Admin can revoke role | Phase 9 | Test: role downgrade works |

## Acceptance Criteria Verification

| AC# | Criterion | Verification Method |
|-----|-----------|-------------------|
| 1 | Cofounder accesses premium features | Integration test: cofounder role passes premium route guards |
| 2 | Credits reset weekly | Unit test: ensure_credits() with stale last_reset |
| 3 | Ticket creation deducts credit | Unit test: deduct_credit returns new balance |
| 4 | 0 credits blocks creation | Unit test: deduct_credit raises at 0 |
| 5 | /tickets shows own tickets | E2E test: cofounder sees own, not others' |
| 6 | Admin sees all with filters | E2E test: admin /tickets with filter params |
| 7 | Stripe payment upgrades role | Integration test: mock webhook → role check |
| 8 | "Become Co-Founder" visible to premium | E2E test: premium user sees button, cofounder does not |
| 9 | Admin updates token multipliers | E2E test: admin settings form submit |
| 10 | Paperclip issue created + status sync | Integration test: mock Paperclip API |
| 11 | Ticket detail with comments | E2E test: post comment, verify display |
| 12 | Email on status change | Unit test: mock Resend, verify call |
| 13 | Admin sets licence price | E2E test: settings form, verify Stripe session |
| 14 | Admin downgrades cofounder | Integration test: set_role to premium |

## Dependencies

- **Stripe API**: One-time payment Checkout session creation (existing integration)
- **Resend API**: Email delivery (existing integration via `src/email_service.py`)
- **Paperclip API**: Issue creation and status reads (new integration; requires `PAPERCLIP_API_URL` and `PAPERCLIP_API_KEY` env vars)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| SQLite table recreation for CHECK constraint | Med | Med | Run migration in a transaction; test with backup |
| Paperclip API unavailable | Low | Low | Ticket created locally; Paperclip issue creation retried on next view |
| Credit race condition (concurrent requests) | Low | Low | SQLite write lock serializes; use UPDATE WHERE credits > 0 |
| Stripe webhook replay | Low | Low | Idempotent: skip if role already cofounder |

## Architecture Decision Records

### ADR-1: Ticket Storage Location

**Context:** Tickets are cross-user data (admin sees all). The app has per-user portfolio.db files and a shared _system/users.db.

**Decision:** Store tickets in `_system/users.db` alongside user accounts.

**Rationale:** Tickets are system-wide data, not portfolio data. A separate tickets.db adds connection management overhead for no benefit. users.db already handles shared state.

**Consequences:** Single connection pool for user + ticket queries. Schema migration applies to one database.

### ADR-2: Credit Tracking

**Context:** Need to track weekly credit allowance per co-founder with weekly reset.

**Decision:** Two columns on users table: `credits_remaining INTEGER` and `credits_last_reset TEXT`.

**Rationale:** Simple allowance model doesn't need transaction history. Check-and-reset on access is sufficient. Can migrate to a ledger table later if audit trail is needed.

**Consequences:** `ensure_credits()` called before any credit operation to handle lazy reset.

### ADR-3: Paperclip Status Sync

**Context:** Tickets create Paperclip issues. Need to reflect Paperclip issue status on the ticket.

**Decision:** Store `paperclip_issue_id` on ticket row. Fetch status on-demand with 60-second cache (`status_synced_at`).

**Rationale:** No webhook infrastructure exists. Polling cron adds unnecessary load. On-demand fetch is simplest and only costs an API call when someone views the ticket.

**Consequences:** Ticket detail view may show stale status (up to 60s). Acceptable for this use case.

### ADR-4: System Settings

**Context:** Admin needs to configure token multipliers, licence price, and credits per week.

**Decision:** New `system_settings` key-value table in users.db with defaults inserted on schema init.

**Rationale:** Simple key-value is sufficient for ~4 settings. No need for a full config framework.

**Consequences:** Settings read from DB on each request that needs them. Could cache in-memory if performance is a concern.

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Ticket storage | users.db | Cross-user data belongs in shared DB | 2026-05-23 |
| Credit tracking | Columns on users table | Simple model, no audit trail needed | 2026-05-23 |
| Paperclip sync | On-demand with 60s cache | No webhook infra, simplest approach | 2026-05-23 |
| System settings | Key-value table in users.db | Simple, sufficient for ~4 settings | 2026-05-23 |
| Route module | New web/tickets.py | Follows existing modular pattern | 2026-05-23 |
