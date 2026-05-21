# PRD: User Onboarding Flow — Guided First-Time Experience

**Epic:** User onboarding flow
**Issue:** SAA-16
**Status:** Ready
**Confidence:** 90%
**Last updated:** 2026-05-21

## Summary

New paying users (premium/admin) land on an empty dashboard after signup. Build a guided onboarding flow that gets them from signup to seeing portfolio analytics in under 3 minutes. Includes a multi-step modal welcome wizard, consistent empty states with inline import CTAs, and read-only demo data access for exploration.

## Existing Implementation (Audit)

1. **Guided tour** (`onboarding.js`) — 5-step spotlight tour for demo visitors, auto-starts on first visit.
2. **Import wizard** (`web.py: _serve_import_wizard`) — file upload flow with CSV validation and staging.
3. **Demo portfolio** (`_demo/portfolio.db`) — read-only demo DB shown to unauthenticated guests.
4. **Partial empty states** — some sections show empty messages; dashboard shows basic "No data imported yet" text.
5. **Landing page** — "Explore a live demo" CTA on the public landing page.

## Requirements

### R1 — Welcome Wizard (Modal Overlay)
After first login, show a multi-step modal overlay on the dashboard:
- **Step 1 — Welcome**: Brief message explaining WealthEagle's value proposition. Options: "Import my data" or "Try with demo data".
- **Step 2 — Import CSV**: Simplified import wizard focused on Revolut format. Drag-and-drop or file picker. Validates CSV and shows preview.
- **Step 3 — Price Sync**: Trigger sync in the background. User can browse/explore while it runs. Toast notification when sync completes.
- **Step 4 — Celebration**: Confetti animation + portfolio highlights card showing key metrics (total value, gain/loss, top holding).

### R2 — Read-Only Demo Data
- Logged-in premium users can view the shared demo portfolio (`_demo/portfolio.db`) in read-only mode.
- "Try with demo data" button available in the wizard and in empty states.
- When viewing demo data, a clear "Demo Data" banner is shown (extend existing guest demo banner to premium users).
- User can switch back to their own (empty) portfolio at any time.

### R3 — Consistent Empty States
- Every dashboard section (summary, tax, analytics, charts, projections, dividends, report) shows an empty state when no user data exists.
- Each empty state follows a unified pattern: contextual icon + descriptive message + prominent "Import CSV" button.
- The "Import CSV" button opens the import wizard directly (modal or navigates to import page).

### R4 — Wizard Trigger & State
- Server-side `onboarding_completed` flag in `users.db`. Wizard shows only when flag is false.
- Flag set to true when user completes the wizard OR dismisses it.
- Wizard can be replayed from a help menu (resets flag temporarily for the session).

### R5 — Background Sync with Notification
- Price sync runs asynchronously after CSV import.
- Show a non-blocking toast/notification when sync starts ("Syncing prices...").
- Show completion toast with link to analytics when done ("Prices synced! View your analytics →").
- If sync fails, show error toast with retry option.

### R6 — Confetti Celebration
- Brief confetti animation (canvas-based, ~2 seconds) on the final wizard step.
- Below confetti, show a portfolio highlights card: total value, total gain/loss %, top holding, number of positions.
- "View Full Dashboard" CTA button dismisses wizard and loads the dashboard with real data.

## Acceptance Criteria

1. A new premium user sees the welcome wizard modal on their first dashboard visit after signup.
2. The wizard guides through 4 steps: welcome → import → sync → celebration.
3. Wizard can be dismissed at any step; `onboarding_completed` flag is set.
4. "Try with demo data" shows the shared demo portfolio in read-only mode with a demo banner.
5. Users can switch between demo view and their own portfolio.
6. Every dashboard section shows a consistent empty state with an inline "Import CSV" button when no user data exists.
7. Price sync runs in the background; toast notifications show progress and completion.
8. Final wizard step shows confetti animation + portfolio highlights card.
9. After completing onboarding, the dashboard shows the user's real analytics.
10. A new user can go from signup → seeing portfolio analytics in under 3 minutes.
11. The wizard can be replayed from a help menu.
12. The `onboarding_completed` flag persists server-side in `users.db`.

## Technical Notes

- Extend existing `onboarding.js` tour infrastructure or create a new `welcome_wizard.js` component.
- Reuse existing `_serve_import_wizard` backend; add modal variant for the wizard step.
- Add `onboarding_completed BOOLEAN DEFAULT 0` column to users table.
- Confetti: lightweight canvas-based library (e.g., canvas-confetti) or inline implementation (~50 lines).
- Background sync: existing `/api/sync` endpoint + polling or SSE for completion notification.
- Empty states: create a reusable `renderEmptyState(section, message)` JS function.

## Out of Scope

- Email-based onboarding drip campaign.
- Multi-format CSV support in the wizard (Revolut only for now).
- Onboarding analytics/tracking.
- A/B testing of wizard variants.

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
| Wizard format | Modal overlay on dashboard | Keeps context visible, feels lighter, consistent with existing tour overlays | 2026-05-21 |
| Demo data for premium users | Read-only view of shared demo DB | Simpler than copying, no cleanup needed, similar to existing guest experience | 2026-05-21 |
| Empty state CTAs | Inline Import CSV button per section | Reduces clicks, each section gets a prominent CTA opening the import wizard | 2026-05-21 |
| Sync UX | Background sync with notification | Fastest perceived time, user can browse while sync runs, toast on completion | 2026-05-21 |
| Celebration UI | Confetti animation + highlights card | More delightful than plain success message, shows immediate value with key metrics | 2026-05-21 |
| Wizard trigger | Server-side onboarding_completed flag | Persists across browsers/devices, reliable, only shows once unless replayed | 2026-05-21 |

