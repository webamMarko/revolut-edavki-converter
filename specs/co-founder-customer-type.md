# PRD: Co-Founder Customer Type

**Epic:** co-founder-customer-type
**Status:** Ready for Review
**Confidence:** 92%
**Last updated:** 2026-05-23

## Summary

A new "co-founder" role for users who purchase a one-time lifetime licence via Stripe at an admin-configurable price. Co-founders get all premium features plus 100 weekly credits (non-rolling) to submit bug reports and feature ideas via a dedicated `/tickets` page. Each ticket costs 1 credit. Tickets have minimal fields (type, title, description) with statuses New/In Progress/Done and threaded comments. Co-founders see only their own tickets; admins see all. Admin configures per-type credit-to-token multipliers and the licence price. Tickets are executed by creating Paperclip issues assigned to an AI agent, with status synced back. Email notifications are sent on ticket status changes via Resend. Admin can revoke co-founder status if needed.

## Requirements

1. Add a new `cofounder` value to the user role CHECK constraint (`guest`, `premium`, `admin`, `cofounder`).
2. Co-founders have all premium features plus access to the ticket/credit system.
3. Each co-founder receives 100 credits per week; unused credits reset (do not roll over).
4. Bug tickets and idea tickets each cost 1 credit to create.
5. Ticket interface lives on a standalone `/tickets` page, accessible from the nav bar for co-founders and admins.
6. Co-founders see only their own tickets; admins see all tickets across all co-founders.
7. One-time lifetime licence purchased via Stripe Checkout (one-time payment mode); on success, user role upgrades to `cofounder`.
8. Admin settings page with per-type credit-to-token multiplier (e.g., 1 bug credit = 5000 tokens, 1 idea credit = 10000 tokens).
9. Ticket submission creates a Paperclip issue assigned to an AI agent; ticket status syncs with Paperclip issue status.
10. Ticket fields: type (bug/idea), title, description, status, created_at, updated_at. Comments are a separate related entity.
11. Email notification sent to co-founder via Resend when their ticket status changes (to In Progress or Done).
12. Co-founder licence price is admin-configurable in the admin settings page.
13. Admin can revoke co-founder role (downgrade to premium) for abuse or other reasons.

## Acceptance Criteria

1. A user with role `cofounder` can access all premium features.
2. Credit balance resets to 100 every Monday (or configurable weekly reset day).
3. Creating a bug or idea ticket deducts 1 credit from the co-founder's balance.
4. A co-founder with 0 credits cannot create new tickets until the next reset.
5. `/tickets` page shows the co-founder's own tickets with status, type, and creation date.
6. Admin `/tickets` view shows all tickets with author name and filtering by status/author.
7. Successful Stripe one-time payment upgrades the user's role from `premium` to `cofounder`.
8. A "Become Co-Founder" button/page is visible to premium users, linking to Stripe Checkout.
9. Admin can view and update credit-to-token multipliers on an admin settings page.
10. When a ticket is created, a corresponding Paperclip issue is created and the ticket status updates when the Paperclip issue status changes.
11. Ticket detail page shows title, description, status, and a comment thread where both the co-founder and admin can post.
12. Co-founder receives an email when their ticket moves to In Progress or Done.
13. Admin can set the co-founder licence price from the admin settings page; Stripe Checkout uses this price.
14. Admin can downgrade a co-founder to premium from the user management page.

## Open Questions

None — PRD is comprehensive and ready for technical specification.

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Role model | New `cofounder` role in DB | Clean separation, easy to query, no flag muddiness | 2026-05-23 |
| Credit rollover | Reset to 100 weekly | Simple, predictable, prevents hoarding | 2026-05-23 |
| Ticket costs | Same cost (1 credit each) | Simple UX; admin token-mapping handles AI cost differences | 2026-05-23 |
| Ticket interface | Standalone `/tickets` page | Clean separation from portfolio analytics, accessible from nav | 2026-05-23 |
| Ticket visibility | Own tickets only | Privacy-first; admin sees all | 2026-05-23 |
| Licence purchase | Stripe one-time payment | Consistent with existing Stripe integration, self-service | 2026-05-23 |
| Admin token settings | Simple multiplier per ticket type | Easy to understand and adjust; one key-value pair per type | 2026-05-23 |
| AI execution | Paperclip integration | Leverages existing infrastructure; ticket status syncs with issue status | 2026-05-23 |
| Ticket fields | Minimal (type + title + description) | Enough for v1; keeps the form simple | 2026-05-23 |
| Email notifications | Yes — email on status change | Uses existing Resend integration; keeps co-founders informed | 2026-05-23 |
| Pricing | Admin-configurable | Maximum flexibility for promotions and pricing adjustments | 2026-05-23 |
| Downgrade handling | Admin can revoke | Safety valve for abuse; admin controls role via user management | 2026-05-23 |
