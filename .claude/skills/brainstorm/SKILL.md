---
name: brainstorm
description: "This skill should be used when the user wants to brainstorm, refine, or develop a PRD (Product Requirements Document) for an epic. It iteratively asks questions with recommended options, reconciles answers into requirements, and continues until confidence reaches 90%. Usage: /brainstorm <epic-name>"
---

# Brainstorm — Epic PRD Builder

This skill iteratively builds a PRD for an epic by asking targeted questions, presenting options with recommendations, and reconciling answers into concrete requirements.

## Input

The skill takes one argument: the **epic name** (e.g. `/brainstorm MERCH-3200 Voucher Redesign`).

## PRD File Location

PRDs are stored in: `specs/<epic-name-slug>.md` (relative to the repo root).

If the file already exists, resume from its current state. If it doesn't exist, create it with the initial template.

## Workflow

### Step 1: Initialize or Load PRD

If `specs/<slug>.md` does not exist, create it with this template:

```markdown
# PRD: <Epic Name>

**Epic:** <epic-name>
**Status:** Draft
**Confidence:** 0%
**Last updated:** <date>

## Summary

<one-paragraph summary — fill in as answers accumulate>

## Requirements

<numbered list of confirmed requirements — added as questions are answered>

## Acceptance Criteria

<numbered list — added as questions are answered>

## Open Questions

<numbered list of unresolved questions with options>

## Decisions Log

<table: Question | Decision | Rationale | Date>
```

If the file exists, read it and identify:
- Current confidence level
- Remaining open questions
- Areas lacking coverage

### Step 2: Generate Questions

Analyze the PRD's current state and generate 1-3 open questions that would most increase confidence. Each question must:

1. Have 2-4 concrete options
2. Mark one option as **(Recommended)** by appending "(Recommended)" to its label — but NEVER pre-select it. Only the user decides which option to pick.
3. Be presented using the `AskUserQuestion` tool

Focus questions on these dimensions (in priority order):
- **Scope**: What's in/out? Edge cases?
- **User impact**: Who benefits, how?
- **Technical approach**: Key architectural decisions
- **Dependencies**: What must exist first?
- **Success criteria**: How do we know it works?
- **Risks**: What could go wrong?

For any question that touches **technical approach, module design, integration strategy, or data model**, invoke the `architect-advisor` agent before presenting the question. Use its recommendation to:
- Select which option to mark as **(Recommended)**
- Write the option descriptions (pros/cons, alignment)
- Ensure the options reflect real project patterns rather than generic choices

For any question that touches **user-facing behaviour, UI components, interaction patterns, layout, or visual design**, invoke the `ux-advisor` agent before presenting the question. Use its recommendation to:
- Select which option to mark as **(Recommended)**
- Write the option descriptions grounded in the project's brand and component palette
- Ensure options reference real tokens and components rather than generic choices

### Step 3: Reconcile Answers

For each answered question:
1. Move it from "Open Questions" to the "Decisions Log" with the chosen option and rationale
2. Derive 1-2 concrete **Requirements** or **Acceptance Criteria** from the answer
3. Add them to the appropriate PRD section
4. Update the **Confidence** percentage (estimate based on coverage of the dimensions above)

### Step 4: Loop or Complete

- If confidence < 90%: go back to Step 2 and generate the next batch of questions
- If confidence >= 90%: update Status to "Ready for Review", write a short completion summary

## Confidence Scoring Guide

- 0-20%: Only epic name known, no scope defined
- 20-40%: Scope roughly defined, major decisions unmade
- 40-60%: Core requirements clear, some edges undefined
- 60-80%: Most requirements and acceptance criteria written, few open questions remain
- 80-90%: Nearly complete, only minor clarifications needed
- 90-100%: PRD is comprehensive and actionable

## Rules

- Never pre-select an answer — mark the recommended option but always let the user choose
- Never invent requirements without user confirmation — always ask first
- Keep the PRD concise: requirements should be one sentence each
- Use the Decisions Log to maintain an audit trail
- Each interaction should make visible progress (new requirements added or questions resolved)
- If the user provides context about the epic (Jira link, description), incorporate it before asking questions
