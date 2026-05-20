---
name: implement-epic
description: "Implements a complete epic from its technical specification using a TDD workflow: analyze spec → write tests → implement → lightweight verify per component → static quality gate → full QA via verify-epic. Usage: /implement-epic <epic-name>"
---

# Implement Epic

Implements an epic end-to-end from its technical specification using strict TDD. Each component goes through a red→green→refactor cycle with a lightweight unit test check only. Full QA (integration, acceptance, Playwright) is delegated to `verify-epic` at the very end.

## Input

One argument: the **epic name slug** (e.g. `/implement-epic epic-1`).

This value is used throughout — for spec/PRD file paths and as the argument passed to `verify-epic` at completion.

## File Conventions

- Spec: `specs/<epic-name>-spec.md`
- PRD: `specs/<epic-name>-prd.md`
- Implementation: `src/app/code/<Namespace>/<Module>/` (as defined in the spec)
- Tests: `src/app/code/<Namespace>/<Module>/Test/Unit/`

---

## Workflow

### Step 1: Analyze Specification

1. Read `specs/<epic-name>-spec.md` in full.
2. Read `specs/<epic-name>-prd.md` for the acceptance criteria list.
3. If the spec does not exist, stop:
   > "No spec found at `specs/<epic-name>-spec.md`. Please run `/write-spec <epic-name>` first."
4. Extract and internally track:
   - **All AC** from the PRD — the pass/fail gate for `verify-epic` at the end
   - **All TDD tasks** from the spec's Implementation Plan — the unit-of-work for this skill
   - **All components** from Key Components (class names, interfaces, module paths)
   - **All ADRs** — resolved decisions to honour throughout
5. Present a brief plan to the user:
   - Modules and files to be created
   - Number of TDD tasks and AC items
   - Confirm: > "Ready to implement `<epic-name>`. This will create/modify the above files. Proceed?"

---

### Step 2: Write Failing Tests (Red)

For each component in the spec's TDD Task List, write the unit test **before any implementation code**.

#### 2a. Consult advisors

- **Test structure decisions** (Mockery vs createMock, setUp layout, data providers) → invoke `coding-advisor`
- **UX/template assertions** (expected markup, `data-ui-id` values) → invoke `ux-advisor`

#### 2b. Create test file

`src/app/code/<Namespace>/<Module>/Test/Unit/<SubPath>/<ClassNameTest>.php`

```php
<?php
declare(strict_types=1);
namespace <Namespace>\<Module>\Test\Unit\<SubPath>;

use Mockery\Adapter\Phpunit\MockeryPHPUnitIntegration;
use PHPUnit\Framework\TestCase;

class <ClassNameTest> extends TestCase
{
    use MockeryPHPUnitIntegration;

    protected function setUp(): void { /* mock setup */ }

    public function test_<snake_case_description>(): void { /* ... */ } // AC-N
}
```

Requirements:
- Every behaviour in the spec's TDD Task List for this component must have a test
- Each test references its AC via a `// AC-N` comment
- Mockery for factories/generated classes; PHPUnit `createMock()` for plain interfaces
- `static::assert*()` — never `$this->assert*()`
- No Magento instance or database dependency

#### 2c. Confirm red

Run only the new test class:
```bash
cd /Users/marko/Projects/dev-environment/src && vendor/bin/phpunit --filter "<TestClassName>" 2>/dev/null | tail -10
```

Expected: failure with "class not found" or missing method — **not** a syntax error. Fix syntax errors now before proceeding.

---

### Step 3: Implement (Green)

Implement components in dependency order — foundational classes first, consumers after.

#### 3a. Consult advisors before writing code

- **Architecture decisions** not resolved in the spec's ADRs → invoke `architect-advisor`
- **Coding/implementation decisions** (class structure, naming, exception handling) → invoke `coding-advisor`
- **UX/template decisions** (component choice, token usage, `data-ui-id` naming) → invoke `ux-advisor`

Never implement a component before open decisions are resolved.

#### 3b. Write implementation

Conventions from `.claude/_coding-guidelines.md` and `.claude/_architecture-reference.md`:

- `declare(strict_types=1)` on every PHP file
- Promoted `private readonly` constructor parameters
- Fully typed: all properties, parameters, return types (PHP 8.3+)
- `use` imports only — no inline FQCNs
- No `ObjectManager::getInstance()`
- Repository over Factory where applicable
- ViewModel over Helper in templates
- Every interactive/structural HTML element: `data-ui-id="kebab-case-name"`
- All user-facing strings: `__()` + entries in `i18n/en_US.csv` and `i18n/de_DE.csv`

#### 3c. Register in DI and schema

- `etc/di.xml` — preferences, plugins, virtual types per ADRs
- `etc/db_schema.xml` — new tables
- `etc/events.xml` — observers
- `etc/module.xml` — sequence dependencies if new inter-module dependencies are introduced

---

### Step 4: Lightweight Component Check (per component)

After implementing each component, run **only that component's tests** — nothing broader:

```bash
cd /Users/marko/Projects/dev-environment/src && vendor/bin/phpunit --filter "<TestClassName>" 2>/dev/null | tail -10
```

**If tests pass (green):** proceed to the next component in Step 2.

**If tests fail:** fix the implementation — not the test. Re-run until green. If a fix requires changing a test because the spec was genuinely ambiguous, stop and ask the user before changing any test.

Repeat the Step 2 → Step 3 → Step 4 cycle for every component in the TDD Task List.

---

### Step 5: Static Quality Gate

Once all components are implemented and all unit tests are green, run the full static analysis and code style check across all affected modules:

```bash
bin/analyse src/app/code/<Namespace>/<Module>
bin/phpcs src/app/code/<Namespace>/<Module>
```

Fix all issues before continuing:
- **PHPStan errors**: fix typing or structural issues. Never suppress with `@phpstan-ignore` unless the spec explicitly allows it.
- **PHPCS violations**: run `bin/phpcbf src/app/code/<Namespace>/<Module>` first, then fix remaining violations manually.

Do not proceed to Step 6 until both tools report clean.

---

### Step 6: Full QA via verify-epic

With all unit tests green and static analysis clean, flush caches and run the full QA suite:

```bash
bin/magento cache:flush
```

If new DI configuration, templates, or static assets were added, run full compile first:
```bash
bin/dhimahi-full-compile
```

Then invoke `verify-epic` with the same epic name:

> Invoking `/verify-epic <epic-name>` for full QA…

`verify-epic` will run: unit tests → integration tests → Codeception acceptance tests → Playwright click-through, and produce the final AC coverage report.

The implementation is complete when `verify-epic` returns its Verification Report. Do not produce a separate AC coverage table — `verify-epic` owns that output.

---

## Rules

- **Tests before implementation** — never write implementation code before the failing test exists
- **Lightweight testing per component** — Step 4 runs only the current component's test class, never the full suite. The full suite runs once in Step 6 via `verify-epic`
- **Never modify a test to make it pass** — fix the implementation; only change a test when the spec is genuinely ambiguous, and only after user confirmation
- **Honour all ADRs** — do not re-open resolved decisions
- **Consult advisors proactively** — `architect-advisor`, `coding-advisor`, `ux-advisor` for any decision not already resolved in the spec
- **One component at a time** — complete red→green for each component before starting the next
- **Static analysis must be clean** before `verify-epic` is invoked
- **Never use `--no-verify`** on git operations
- **AC coverage is owned by `verify-epic`** — do not duplicate it here
