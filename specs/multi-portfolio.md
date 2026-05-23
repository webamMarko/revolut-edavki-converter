# PRD: Multi-portfolio support

**Epic:** SAA-20
**Status:** Ready for Review
**Confidence:** 90%
**Last updated:** 2026-05-23

## Summary

Power users with multiple investment accounts or strategies need to manage separate portfolios. This feature adds named portfolios per user (max 5), a switcher in the nav header, and scoped analytics/tax/report views. Existing users auto-migrate to a default "Main" portfolio. Each user's single portfolio.db gains a portfolio_id column on all relevant tables.

## Requirements

1. Each user can have up to 5 named portfolios stored as rows in a `portfolios` table within their existing `portfolio.db`
2. All transaction/analytics tables gain a `portfolio_id` column; all queries must filter by active portfolio
3. A default "Main" portfolio is auto-created on first access; existing data is backfilled with this portfolio's ID
4. Users can create, rename, and delete portfolios from the Settings page
5. A dropdown in the nav header (header-right zone, next to username) lets users switch the active portfolio
6. All analytics, tax, report, and import views are scoped to the active portfolio
7. The cron sync job syncs prices for all portfolios per user
8. Consolidated "All Portfolios" view is deferred to v2
9. CSV imports always target the active portfolio (no portfolio picker in import wizard)
10. Portfolio deletion is hard delete with confirmation dialog; default portfolio cannot be deleted

## Acceptance Criteria

1. User can create a second portfolio, import data into it, and see separate analytics
2. Switching portfolios updates all views instantly
3. Existing single-portfolio users see their data under a "Main" portfolio without manual action
4. Portfolio limit of 5 is enforced with a clear error message
5. Deleting a portfolio removes all its transaction data after confirmation
6. Shared portfolio links continue to work (scoped to the portfolio they were created from)
7. Default portfolio cannot be deleted
8. Import wizard imports into the currently active portfolio

## Open Questions

(none remaining)

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Data isolation approach | Single DB with portfolio_id column | User chose single-DB approach — keeps one DB per user, shared market data tables | 2026-05-23 |
| Consolidated view scope | Defer to v2 | Reduces v1 scope; aggregation across portfolios is complex | 2026-05-23 |
| Max portfolios per user | 5 | Covers typical use cases without unbounded resource usage | 2026-05-23 |
| Portfolio switcher placement | Header-right, next to username | Groups all user controls in one zone, preserves nav layout, scales on mobile | 2026-05-23 |
| Portfolio deletion | Hard delete with confirmation | Simple, no orphaned data, user warned via dialog. Default portfolio protected | 2026-05-23 |
| Import target | Always use active portfolio | Simple UX — user switches portfolio first, then imports. No extra wizard step | 2026-05-23 |
