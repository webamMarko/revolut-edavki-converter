# PRD: Unified Dashboard Components

**Epic:** SAA-167
**Status:** Draft
**Confidence:** 15%
**Last updated:** 2026-05-25

## Summary

After implementing the customizable GridStack dashboard (SAA-114), predefined navigation sections (Overview, Performance, Positions, etc.) render empty. The root cause is that section HTML templates are `{% include %}`-d twice — once in the predefined page containers (`page-overview`, `page-charts`, etc.) and again inside hidden `#widgetTemplates` div for the GridStack dashboard. Since sections use fixed DOM IDs, JavaScript finds the hidden widget-template copy first and renders into it instead of the visible page section. The goal is to make all components work correctly in both the predefined sidebar-navigation view and the customizable GridStack dashboard.

## Requirements

## Acceptance Criteria

## Open Questions

1. **Architecture approach**: Should we (a) extract shared renderers that both systems invoke, (b) make predefined sections just a locked preset of the customizable dashboard, or (c) eliminate duplicate includes and have dashboard clone/move DOM nodes on demand?
2. **Chart lifecycle**: How should charts handle init/destroy when moving between contexts or when GridStack widgets are added/removed?
3. **Scope of predefined sections**: Should predefined sections remain as-is (sidebar nav with full pages) or should they be replaced entirely by the customizable dashboard?

## Decisions Log

| Question | Decision | Rationale | Date |
|----------|----------|-----------|------|
