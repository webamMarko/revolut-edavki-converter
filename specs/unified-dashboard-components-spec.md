# Unified Dashboard Components — Technical Specification

**Epic:** SAA-167 / SAA-168
**Source:** SAA-167 Paperclip spec document

## Problem

Every section template is `{% include %}`d twice in `report.html.j2`:
1. Inside a predefined page (`<div class="page" id="page-positions">`)
2. Inside `#widgetTemplates` (hidden div for GridStack cloning)

This creates **duplicate DOM IDs**. `document.getElementById()` finds the first occurrence — which is in the hidden `#widgetTemplates` div (it appears first in the DOM) — so predefined pages get no chart initialization.

## Solution: data-role + scopedFind

1. Replace inner `id=` with `data-role=` in all 16 duplicated section templates
2. Add `scopedFind(container, role)` utility to `app.js`
3. Refactor each section JS init function to accept `container` param
4. Update `dashboard.js` with `WIDGET_INIT_MAP` — call init after `addWidget`
5. Update `nav.js` — call section init on page switch

## Files to Modify

- `src/templates/assets/app.js` — add scopedFind
- `src/templates/sections/*.html.j2` (16 files) — replace id → data-role
- `src/templates/assets/sections/*.js` (16 files) — accept container param
- `src/templates/assets/dashboard.js` — WIDGET_INIT_MAP + init lifecycle
- `src/templates/assets/nav.js` — call section init on page switch

## Acceptance Criteria

1. Each predefined section (Overview, Charts, Positions, etc.) renders charts/tables correctly
2. Opening the customizable dashboard shows widgets with correct data
3. Adding/removing widgets initializes/destroys sections properly
4. Switching between predefined sections and dashboard causes no duplicate charts or missing data
