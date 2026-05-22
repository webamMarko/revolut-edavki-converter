# PRD: Multi-portfolio support

**Epic:** SAA-20
**Status:** Draft
**Confidence:** 0%
**Last updated:** 2026-05-22

## Summary

Power users with multiple investment accounts or strategies need to manage separate portfolios. This feature adds named portfolios per user, a switcher in the nav, and scoped analytics/tax/report views. Existing users auto-migrate to a default "Main" portfolio.

## Requirements

## Acceptance Criteria

## Open Questions

1. How should portfolio data be isolated — separate SQLite DB files per portfolio (extending current pattern) or tables within a single DB?
2. What is the maximum number of portfolios per user?
3. Should the consolidated "All Portfolios" view be in scope for v1 or deferred?
4. How should portfolio switching work in the UI — nav dropdown, sidebar, or settings page?
5. What happens to shared portfolio links when multi-portfolio is introduced?
6. Should CSV imports auto-detect which portfolio to target, or always use the active one?
7. Should the cron sync job sync all portfolios for all users?
8. How should portfolio deletion work — soft delete, hard delete, or archive?

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
