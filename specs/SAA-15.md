# PRD: Migrate Inline HTML to Jinja2 Templates (SAA-15)

**Epic:** SAA-15
**Status:** Ready for Review
**Confidence:** 90%
**Last updated:** 2026-05-22

## Summary

Replace ~2,200 lines of inline Python f-string HTML generation in `src/web.py` with Jinja2 templates. The report page (`html_report.py`) already uses Jinja2 with `src/templates/report.html.j2`; this epic extends that pattern to all remaining pages: login, invite/signup, error, reset-password, account, admin, settings, pricing, upload/dashboard, and import wizard. Shared components (head, nav header, drag-drop overlay, toast, theme toggle) become Jinja2 partials. The ~275-line `_COMMON_CSS` string moves to a static CSS file.

## Requirements

1. Create a `src/templates/pages/` directory for page-level templates, reusing the existing `jinja2.Environment(loader=FileSystemLoader('src/templates'))` from `html_report.py`
2. Create a `base.html.j2` template with shared `<head>`, nav header, theme toggle, and footer blocks
3. Extract `_COMMON_CSS` (~275 lines) to `src/templates/assets/common.css` as a static file served by the web handler
4. Migrate all 16 `_*_html()` functions in `src/web.py` to individual Jinja2 page templates extending `base.html.j2`
5. Extract shared partials: `_head_html()` → base template head block, `_header_html()` → `partials/nav.html.j2`, `_global_drop_import_html()` → `partials/drop_import.html.j2`
6. Register a `t()` global function on the Jinja2 Environment that calls the existing JSON-backed i18n lookup from `src/i18n.py`
7. Remove all inline HTML f-string functions from `src/web.py` after migration
8. Roll out incrementally in 4 subtasks by page group: (a) base template + auth pages, (b) admin/settings/account, (c) dashboard/upload/import wizard, (d) pricing/error/misc
9. Serve `common.css` as a static file with appropriate caching headers

## Acceptance Criteria

1. Zero inline HTML generation functions remain in `src/web.py` (except report which uses its own Jinja2 template)
2. All pages render identically — no visual regressions
3. All existing E2E tests pass without modification
4. Mobile responsiveness preserved on all pages
5. Translation system works: `t()` function available in templates, JS translations still loaded client-side
6. Theme toggle (dark/light) continues to work
7. Drag-and-drop CSV import overlay works on premium/admin pages
8. Each incremental subtask is independently deployable without breaking other pages

## Open Questions

None remaining.

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
| Template directory | `src/templates/pages/` subdirectory | Reuses existing Jinja2 Environment and FileSystemLoader; keeps page templates separate from report section partials | 2026-05-21 |
| CSS handling | Extract to static `common.css` file | Browser caching, cleaner base template, existing `styles.css` already in `assets/` | 2026-05-21 |
| Rollout strategy | Incremental by page group (4 subtasks) | Each subtask independently deployable and testable; lower review/revert risk | 2026-05-21 |
| i18n in templates | `t()` Jinja2 global function | Same JSON-backed lookup as JS; eliminates flash-of-untranslated-content for server-rendered strings | 2026-05-21 |

## Pages to Migrate (16 functions)

| Function | Template | Subtask |
|----------|----------|---------|
| `_head_html()` | `base.html.j2` (head block) | A |
| `_header_html()` | `partials/nav.html.j2` | A |
| `_global_drop_import_html()` | `partials/drop_import.html.j2` | A |
| `_login_html()` | `pages/login.html.j2` | A |
| `_invite_html()` | `pages/invite.html.j2` | A |
| `_reset_password_request_html()` | `pages/reset_password_request.html.j2` | A |
| `_reset_password_confirm_html()` | `pages/reset_password_confirm.html.j2` | A |
| `_error_html()` | `pages/error.html.j2` | D |
| `_shared_expired_html()` | `pages/shared_expired.html.j2` | D |
| `_account_html()` | `pages/account.html.j2` | B |
| `_admin_html()` | `pages/admin.html.j2` | B |
| `_settings_html()` | `pages/settings.html.j2` | B |
| `_pricing_html()` | `pages/pricing.html.j2` | D |
| `_upload_html()` | `pages/upload.html.j2` | C |
| `_import_wizard_html()` | `pages/import_wizard.html.j2` | C |
| `_import_wizard_html_with_user()` | `pages/import_wizard.html.j2` (reuse) | C |
