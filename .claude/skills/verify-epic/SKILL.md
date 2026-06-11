---
name: verify-epic
description: "Verifies a complete epic by running all relevant tests (unit → integration → acceptance/e2e) and a Playwright feature click-through. Pass --screenshots to capture screenshots into e2e/screenshots/. Usage: /verify-epic <epic-name> [--screenshots]"
---

# Verify Epic

Runs the full QA suite for a named epic in order: unit tests → integration tests → Codeception acceptance tests → Playwright click-through. Produces a final report mapping every acceptance criterion to its test result.

Can be invoked directly by the user or called automatically at the end of `/implement-epic`.

## Input

```
/verify-epic <epic-name> [--screenshots]
```

- `<epic-name>` — the epic slug used throughout: matches `specs/<epic-name>-prd.md`, `specs/<epic-name>-spec.md`, and scopes all test runs. Every path and filter in this skill is derived from this value.
- `--screenshots` — if present, Playwright captures full-page screenshots after each major step into `src/tests/visual/e2e/screenshots/<epic-name>/`

---

## Workflow

### Step 1: Load Epic Context

Derive all paths from `<epic-name>`:

1. Read `specs/<epic-name>-prd.md` — extract every acceptance criterion (AC-N) and its description.
2. Read `specs/<epic-name>-spec.md` — extract:
   - Module namespaces and class names under test
   - The AC → test mapping from the Requirement Coverage Matrix
   - Any Playwright / acceptance test files referenced in the spec
3. If neither file exists, stop:
   > "No spec found for `<epic-name>`. Run `/write-spec <epic-name>` first."
4. Build an internal tracking table — every AC starts as ⏳:

| AC | Description | Unit | Integration | Acceptance | Playwright |
|----|-------------|------|-------------|------------|------------|
| AC-1 | … | ⏳ | ⏳ | ⏳ | ⏳ |

---

### Step 2: Unit Tests

Run PHPUnit scoped to the modules identified in the spec for `<epic-name>`:

```bash
cd /Users/marko/Projects/dev-environment/src && vendor/bin/phpunit --filter "<Namespace>" 2>/dev/null | tail -30
```

- Multiple modules: `--filter "Namespace\\\\Module1|Namespace\\\\Module2"`
- Capture: passed / failed / errors / skipped.
- Map failures to AC items via `// AC-N` comments in test files.
- Update tracking table: ✅ pass / ❌ fail / ⚠️ no test / — n/a

---

### Step 3: Integration Tests

Run integration tests for the epic's modules if they exist under `src/app/code/<Namespace>/<Module>/Test/Integration/`:

```bash
cd /Users/marko/Projects/dev-environment/src && vendor/bin/phpunit --filter "<Namespace>\\\\<Module>\\\\Test\\\\Integration" 2>/dev/null | tail -30
```

If no integration tests exist for this epic, note "no integration tests" and continue.

- Capture: passed / failed / errors.
- Update tracking table.

---

### Step 4: Codeception Acceptance Tests

Find acceptance feature files related to `<epic-name>` in `src/tests/acceptance/`. Match by:
- Feature files whose `@tags` or folder name match the epic's domain (e.g. `checkout`, `voucher`, `payment`)
- Any test files explicitly referenced in the spec

Run each matched file:

```bash
bin/cli bash -c "cd /var/www/html && php vendor/bin/codecept run acceptance <path/to/feature.feature> --no-ansi 2>&1" | tail -40
```

If no relevant acceptance tests are found, note it and continue.

- Capture: scenarios passed / failed / skipped.
- Map scenarios to AC items by matching scenario descriptions against AC text.
- Update tracking table.

---

### Step 5: Playwright Click-Through

#### 5a: Determine which test to run

Check `src/tests/visual/tests/` for any spec file related to `<epic-name>`. If one exists, run it directly (Step 5c). If none exists, generate an inline click-through (Step 5b).

#### 5b: Generate inline click-through (if no existing test)

Create a temporary Playwright test at:
```
src/tests/visual/tests/<epic-name>-clickthrough.spec.ts
```

The script must:
- Use `data-ui-id` selectors exclusively — never CSS classes or visible text
- Cover the happy path of the epic's primary user journey from the PRD
- Dismiss the cookie banner if present: `[data-action="accept-cookies"], #btn-cookie-allow`
- Call `await page.waitForLoadState('load')` after each navigation

If `--screenshots` is active, capture a full-page screenshot after each major step:

```typescript
import * as fs from 'fs';
import * as path from 'path';

const SCREENSHOT_DIR = path.join(__dirname, '..', 'e2e', 'screenshots', '<epic-name>');
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}
// After each step:
await page.screenshot({ path: path.join(SCREENSHOT_DIR, '<step-name>.png'), fullPage: true });
```

#### 5c: Run Playwright

```bash
cd /Users/marko/Projects/dev-environment/src/tests/visual && npx playwright test tests/<test-file>.spec.ts --project=desktop-chrome 2>&1 | tail -40
```

With `--screenshots`:
```bash
cd /Users/marko/Projects/dev-environment/src/tests/visual && PLAYWRIGHT_SCREENSHOTS=all npx playwright test tests/<test-file>.spec.ts --project=desktop-chrome 2>&1 | tail -40
```

Capture: tests passed / failed / errors. Note any JS console errors.
Update tracking table.

#### 5d: Screenshot report

If `--screenshots` was passed, list all files saved:
```
Screenshots saved to src/tests/visual/e2e/screenshots/<epic-name>/
  - 01-cart-page.png
  - 02-voucher-applied.png
  ...
```

---

### Step 6: Final Verification Report

```
## Verification Report: <Epic Name>

### Test Summary

| Suite | Passed | Failed | Skipped / N/A |
|-------|--------|--------|---------------|
| Unit | X | X | X |
| Integration | X | X | X |
| Acceptance (Codeception) | X | X | X |
| Playwright click-through | X | X | X |

### Acceptance Criteria Coverage

| AC | Description | Unit | Integration | Acceptance | Playwright | Overall |
|----|-------------|------|-------------|------------|------------|---------|
| AC-1 | <text> | ✅ | ✅ | ✅ | ✅ | ✅ Done |
| AC-2 | <text> | ✅ | — | ⚠️ | ✅ | ⚠️ Partly |
| AC-3 | <text> | ❌ | — | — | — | ❌ Failing |
| AC-4 | <text> | — | — | — | — | ⚠️ No test |

Legend: ✅ pass  ❌ fail  ⚠️ partial/issue  — not applicable / no test

### Failures & Issues

<For each failure: test name, AC it maps to, error message (3 lines max), suggested fix>

### Screenshots
<If --screenshots: list paths — omit section otherwise>

### Next Steps
<Any AC marked ❌ or ⚠️ — recommended action>
```

---

## Output Style — Caveman Mode

All output from this skill MUST follow caveman mode: terse, token-reduced, no filler. Drop articles (a/an/the), filler words (just/really/basically/actually/simply), pleasantries, and hedging. Fragments OK. Short synonyms preferred. Technical terms stay exact. Code blocks unchanged. Errors quoted exact.

- Status updates: `"Unit tests: 12 pass, 2 fail. AC-3 broken — assertion mismatch."` not `"I ran the unit tests and found that 12 tests passed successfully, but unfortunately 2 tests failed..."`
- Report sections: keep tables, drop prose padding around them
- Failure descriptions: error message + suggested fix, no narration
- Next steps: bullet list, no intro sentence

## Rules

- **Never modify tests** to make them pass — report failures honestly
- **Run all suites regardless of earlier failures** — give a complete picture, never stop early
- **`<epic-name>` drives everything** — all file paths, PHPUnit filters, and Codeception feature file matching are derived from this single value
- **Use `data-ui-id` selectors** in all generated Playwright scripts — never CSS classes or visible text
- **Screenshots go to `src/tests/visual/e2e/screenshots/<epic-name>/`** — only when `--screenshots` flag is passed
- **Ask before deleting** generated click-through scripts — only delete if created by this skill and user has not asked to keep them
- **Map every AC** — every criterion from the PRD must appear in the final table, even with no test (mark ⚠️ No test)
- **Report JS console errors** from Playwright even when tests pass
- **Caveman mode mandatory** — all skill output must be terse and token-reduced per the Output Style section above
