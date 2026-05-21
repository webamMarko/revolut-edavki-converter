# PRD: Migrate Inline HTML to Jinja2 Templates (SAA-15)

**Epic:** SAA-15
**Status:** Draft
**Confidence:** 0%
**Last updated:** 2026-05-21

## Summary

Replace ~2,200 lines of inline Python f-string HTML generation in `src/web.py` with Jinja2 templates. The report page (`html_report.py`) already uses Jinja2 with `src/templates/report.html.j2`; this epic extends that pattern to all remaining pages: login, invite/signup, error, reset-password, account, admin, settings, pricing, upload/dashboard, and import wizard. Shared components (head, nav header, drag-drop overlay, toast, theme toggle) become Jinja2 partials. The ~275-line `_COMMON_CSS` string and `_COMMON_JS` block move to static files or template includes.

## Requirements

<numbered list of confirmed requirements — added as questions are answered>

## Acceptance Criteria

<numbered list — added as questions are answered>

## Open Questions

1. Template directory structure — should page templates live in the existing `src/templates/` alongside the report, or in a new top-level `templates/` directory?
2. How to handle the large `_COMMON_CSS` block — keep inline in a base template, extract to a static `.css` file, or split into per-component partials?
3. Should the migration happen all-at-once in one PR, or incrementally page-by-page?
4. How to wire the i18n `t()` function into Jinja2 templates — pass as a template global, or use a Jinja2 extension?

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
