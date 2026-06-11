---
name: write-spec
description: "Creates a detailed technical specification from an epic's PRD. Covers all requirements and acceptance criteria, plans TDD implementation tasks, highlights architecture decisions, and lists high-impact decisions with selectable options. Usage: /write-spec <epic-name>"
---

# Write Spec — Technical Specification Generator

This skill generates a detailed technical specification from an existing PRD by iteratively asking questions until 90% confidence is reached and all high-impact tech decisions are resolved.

## Input

The skill takes one argument: the **epic name** (e.g. `/write-spec epic-1-user-and-organisation`).

## File Conventions

- PRDs are stored in: `specs/<epic-name>-prd.md`
- Tech specs are written to: `specs/<epic-name>-spec.md`

## Workflow

### Step 1: Locate and Read PRD

Look for the PRD file at `specs/<epic-name>-prd.md`.

If the file does **not** exist, stop immediately and inform the user:

> "No PRD found at `specs/<epic-name>-prd.md`. Please create a PRD first (e.g. using `/brainstorm <epic-name>`) before generating a tech spec."

If the file exists, read it in full.

### Step 2: Initialize Spec File

If `specs/<epic-name>-spec.md` does not exist, create it with the initial template:

```markdown
# Technical Specification: <Epic Title>

**Epic:** <epic-name>
**PRD:** specs/<epic-name>-prd.md
**Created:** <date>
**Status:** Draft
**Confidence:** 0%

## Overview

<1-2 paragraph technical summary of what will be built and why>

## Architecture

### System Context

<How the new components fit into the existing system — services, modules, data flows>

### Key Components

<List of new/modified modules, services, classes with their responsibilities>

### Data Model

<Database tables, entities, relationships — include schema definitions where applicable>

### API Contracts

<New or modified APIs — endpoints, request/response shapes, events>

## Implementation Plan

### Phase Breakdown

<Group work into logical phases/milestones>

### TDD Task List

<For each component, list tasks in TDD order:>
1. Write failing test for <behavior>
2. Implement <component> to pass test
3. Refactor

<Each task should map back to a specific requirement or acceptance criterion from the PRD>

## Requirement Coverage Matrix

| PRD Requirement | Spec Section | Test Coverage |
|---|---|---|
| <requirement> | <section ref> | <test description> |

## Acceptance Criteria Verification

<For each acceptance criterion from the PRD, describe how it will be verified — unit test, integration test, manual test, or automated E2E>

## Dependencies

<External systems, libraries, infrastructure, or other epics this depends on>

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| <risk> | High/Med/Low | High/Med/Low | <mitigation strategy> |

## Architecture Decision Records

<Resolved decisions are recorded here as they are answered>

## Decisions Log

| Question | Decision | Rationale | Date |
|---|---|---|---|
```

If the file already exists, read it and resume from its current state (identify confidence level, open questions, unresolved ADRs).

### Step 3: Identify Open Decisions

Analyze the PRD requirements and the spec's current state. Identify gaps where technical decisions are needed. Classify each gap into one of two categories:

**Category A — Architecture decisions** (require `architect-advisor` — see Step 3a):
- High-impact architecture decisions: choices that affect multiple components, are hard to change later, or have significant trade-offs (e.g. sync vs async, separate module vs extend existing, storage strategy)
- Magento extension point selection: plugin vs observer vs preference vs event
- Data model decisions: table structure, relationships, indexing strategy
- Integration points: how components communicate, API design, event-driven vs direct calls
- Performance/scalability: caching, queue usage, batch processing

**Category B — Coding/implementation decisions** (require `coding-advisor` — see Step 3b):
- Class pattern selection: which pattern to use (Service, ViewModel, Repository, Plugin, Observer, Controller, etc.)
- Code organisation within a module: how to split responsibilities, method structure, where logic lives
- Naming: class names, interface names, constant names, method names
- Constructor and DI style: promoted readonly vs other approaches
- Exception handling strategy: what to catch, wrap, re-throw
- Test structure: Mockery vs createMock, data providers, setUp layout

**Category C — UX/UI decisions** (require `ux-advisor` — see Step 3c):
- Component selection: which button variant, form element, card, alert, slider, etc.
- Layout and spacing: page structure, column layout, spacing tokens, breakpoint behaviour
- Color and visual style: which brand token applies, status color usage, contrast
- Interaction patterns: hover/focus/disabled states, transitions, touch targets
- Template structure: how to mark up a new UI section, `data-ui-id` naming

**Category D — Scope/requirements questions** (no agent needed):
- What's in/out of scope
- Priority or phasing decisions
- Non-UI behaviour clarifications

Select the 1-3 highest-priority open decisions across all categories and proceed to Steps 3a, 3b, 3c, and 3d.

### Step 3a: Consult architect-advisor for Category A decisions

For every Category A decision, invoke the `architect-advisor` agent **before** constructing the `AskUserQuestion` call. Provide:
- The decision context (what requirement drives it, what's already decided)
- The candidate options you are considering (2-4)

Extract from its response:
- Which option to mark as **(Recommended)**
- The pros/cons description for each option label
- Pre-drafted ADR "Context" and "Rationale" text to use once the user answers

Do not present the question to the user until the agent has responded.

### Step 3b: Consult coding-advisor for Category B decisions

For every Category B decision, invoke the `coding-advisor` agent **before** constructing the `AskUserQuestion` call. Provide:
- The implementation context (which class/layer is being designed, what the requirement is)
- The candidate options you are considering (2-4)

Extract from its response:
- Which option to mark as **(Recommended)**
- The pros/cons and guideline-alignment description for each option label
- The concrete code example to attach to the recommended option's description

Do not present the question to the user until the agent has responded.

### Step 3c: Consult ux-advisor for Category C decisions

For every Category C decision, invoke the `ux-advisor` agent **before** constructing the `AskUserQuestion` call. Provide:
- The UI context (which screen/component is being designed, what the requirement is)
- The candidate options you are considering (2-4)

Extract from its response:
- Which option to mark as **(Recommended)**
- The pros/cons and brand-alignment description for each option label
- The concrete HTML/Tailwind snippet to attach to the recommended option's description

Do not present the question to the user until the agent has responded.

### Step 3d: Present questions to the user

Present the 1-3 prepared questions using the `AskUserQuestion` tool. Each question must:
- Have 2-4 concrete options whose descriptions reflect the relevant agent's analysis (A → architect-advisor, B → coding-advisor, C → ux-advisor) or your own analysis (D)
- Have exactly one option labelled with **(Recommended)** appended — as determined by the agent or your own analysis
- **Never pre-select**: the recommendation is advisory only — only the user decides

### Step 4: Reconcile Answers into Spec

For each answered question:

1. **If it's a Category A (architecture) decision**: Add a resolved ADR entry to the "Architecture Decision Records" section using the pre-drafted Context and Rationale from the `architect-advisor` agent, updated to reflect the user's actual choice:

```markdown
### ADR-N: <Decision Title>

**Context:** <from agent — why this decision was needed>

**Decision:** <the chosen option>

**Rationale:** <from agent — adapted to the chosen option>

**Consequences:** <from agent — what this means for implementation>
```

2. **If it's a Category B (coding/implementation) decision**: Use the concrete code example from the `coding-advisor` response to populate the relevant spec section (Key Components, TDD Task List, Implementation Plan). Record the chosen class pattern, naming convention, or code organisation rule as a concrete statement — not a general note.

3. **If it's a Category C (UX/UI) decision**: Use the HTML/Tailwind snippet from the `ux-advisor` response to populate the relevant spec section (Key Components, API Contracts for frontend, Implementation Plan). Record the chosen component, token, or interaction pattern as a concrete statement with the example markup.

4. **If it's a Category D (scope/requirements) question**: Convert the answer into a concrete statement and add it to the appropriate spec section (Architecture, Data Model, API Contracts, Implementation Plan, etc.)

5. **Add to Decisions Log**: Record the question, decision, rationale, and date.

6. **Update dependent sections**: If the decision affects the TDD task list, data model, or other sections, update them immediately.

7. **Update Confidence**: Re-estimate based on how many requirements and acceptance criteria now have clear technical coverage.

### Step 5: Loop or Complete

After reconciling answers:

- If confidence < 90% OR there are unresolved high-impact tech decisions: go back to Step 3
- If confidence >= 90% AND all high-impact decisions are resolved:
  1. Update Status to "Ready for Review"
  2. Ensure the Requirement Coverage Matrix is complete (every PRD requirement mapped)
  3. Ensure Acceptance Criteria Verification is complete
  4. Ensure TDD Task List covers all implementation work
  5. Inform the user the spec is complete
  6. Proceed to Step 6 (Create Implementation Issue)

### Step 6: Create Implementation Issue

After the spec is complete (confidence >= 90%), create a Paperclip issue for the Full Stack Dev to implement it. Use the `paperclip` skill to create the issue with:

- **Title:** `Implement <epic-name> spec`
- **Assignee:** FullStackDev agent (`ce166768-111c-48ba-828c-008a9227ceaf`)
- **Parent:** the current spec-writing issue (if running inside a Paperclip heartbeat)
- **Project/Goal:** inherited from the parent issue
- **Status:** `todo`
- **Priority:** same as the spec issue
- **Description** should include:
  - Pointers to the PRD (`specs/<epic-name>-prd.md` or `specs/<epic-name>.md`) and spec (`specs/<epic-name>-spec.md`)
  - A brief summary of what needs to be implemented
  - The TDD task list from the spec
  - The acceptance criteria from the spec

If not running inside a Paperclip heartbeat (no `PAPERCLIP_API_URL` env var), skip this step and inform the user that they should create the implementation issue manually.

## Confidence Scoring Guide

- 0-20%: PRD read, no technical decisions made
- 20-40%: Core architecture direction chosen, most details undefined
- 40-60%: Key components identified, data model sketched, some ADRs resolved
- 60-80%: Most technical decisions made, implementation plan taking shape, TDD tasks partially defined
- 80-90%: Nearly complete — minor decisions remain, all major ADRs resolved
- 90-100%: Spec is comprehensive — all requirements covered, all ADRs resolved, TDD tasks actionable

## Output Style — Caveman Mode

All skill output MUST follow caveman mode: terse, token-reduced, no filler.

- **Questions**: Short, direct. No "Could you please help us decide..." — write "Data model: SQL or NoSQL?" or "Auth strategy?"
- **Descriptions**: Fragments OK. Drop articles (a/an/the), filler (just/really/basically), pleasantries, hedging.
- **Comments**: Pattern: `[thing] [action] [reason]. [next step].` e.g. "Spec decisions posted — round 2. Awaiting answers." not "I've posted some decisions for your review."
- **Spec body**: Technical sections (data model, API contracts, ADRs, TDD tasks) stay precise and complete — caveman applies to prose sections (Overview, rationale, consequences), not to structured specs.
- **Interaction titles/descriptions**: Terse. "Spec decisions — round 2. Confidence: 45%." not "Here are some follow-up questions to help refine the technical specification."
- **Options**: Label + short description. No padding words.

Exceptions: security warnings and irreversible action confirmations use normal prose.

## Writing Guidelines

- **Cover every requirement** from the PRD — use the coverage matrix to ensure nothing is missed
- **Cover every acceptance criterion** — each must have a clear verification strategy
- **Assume TDD** — all implementation tasks should follow red-green-refactor cycle
- **Be specific** — name actual classes, tables, interfaces (following Magento conventions from CLAUDE.md)
- **Keep it actionable** — a developer should be able to pick up a task from this spec and start coding
- **Resolved ADRs are final** — once a decision is made, integrate its consequences into all affected sections

## Rules

- Never generate a spec without a PRD — always check first
- Never pre-select an answer — mark one option as "(Recommended)" in the `AskUserQuestion` label, but NEVER check a `[x]` box in the spec file. All checkboxes must remain `[ ]` — only the user selects
- Never invent technical decisions without user confirmation — always ask first
- **Always invoke `architect-advisor` before presenting any Category A (architecture) question** — its recommendation determines which option is marked "(Recommended)" and provides the ADR pre-draft
- **Always invoke `coding-advisor` before presenting any Category B (coding/implementation) question** — its recommendation determines which option is marked "(Recommended)" and provides the concrete code example
- **Always invoke `ux-advisor` before presenting any Category C (UX/UI) question** — its recommendation determines which option is marked "(Recommended)" and provides the concrete HTML/Tailwind snippet
- Never determine the recommended option for Category A, B, or C questions from your own judgment alone — delegate to the relevant agent
- Every PRD requirement must appear in the coverage matrix by completion
- Every acceptance criterion must have a verification strategy by completion
- Implementation tasks must be in TDD order (test first, then implementation)
- High-impact architecture decisions MUST be resolved via questions before the spec is marked complete
- Answered questions become direct statements/records in the spec — not left as open options
- Follow the coding standards and conventions from CLAUDE.md (PHP 8.3+, typed everything, interfaces over concretes, etc.)
- If the PRD references Magento modules, use the actual namespace conventions (Atlantis/, Dhimahi/, etc.)
- Each iteration should make visible progress (sections filled in, ADRs resolved, tasks added)
