---
name: init-docs
description: "Analyzes an existing domain in the Magento 2 codebase and writes domain-driven documentation to docs/. Reads modules, services, controllers, events, and tests for the domain, then produces a structured docs/domain-<name>.md and updates docs/domain-index.md. Usage: /init-docs <domain>"
---

# Init Docs — Domain Documentation Generator

This skill analyzes an existing domain in the codebase and produces structured domain documentation optimized for planning, spec writing, and implementation agents.

## Input

The skill takes one argument: the **domain name** (e.g. `/init-docs voucher`).

The domain name maps to one or more Magento modules, typically under `src/app/code/Atlantis/<Domain>`, `src/app/code/Dhimahi/<Domain>`, or related modules sharing a business concept.

## Output Files

- `docs/domain-<name>.md` — full domain documentation
- `docs/domain-index.md` — navigation index updated with this domain entry

---

## Workflow

### Step 1: Locate Domain Code

Search for modules, classes, controllers, services, models, and tests related to the domain:

```bash
find src/app/code -type d -iname "*<domain>*"
grep -rl "<domain>" src/app/code --include="*.php" -l | head -40
find src/app/code -path "*/Test/Unit/*" -iname "*<domain>*"
find src/app/code -path "*/Test/Integration/*" -iname "*<domain>*"
```

Also search for:
- Events dispatched with domain-related names: `grep -r "dispatch.*<domain>" src/app/code --include="*.php"`
- REST API routes: `grep -r "<domain>" src/app/code --include="webapi.xml"`
- DB schema: `grep -r "<domain>" src/app/code --include="db_schema.xml"`

### Step 2: Analyze Each Module

For each module found, read and extract:

1. **Domain Model** — from `Model/`, `Api/Data/`, `etc/db_schema.xml`:
   - Entities and their fields
   - Relationships between entities
   - Status enumerations and state machines

2. **API Endpoints** — from `etc/webapi.xml`, controllers in `Controller/`, REST resources:
   - Route, HTTP method, interface method, ACL resource
   - Request/response shapes (from `Api/Data/` interfaces)

3. **Key Behaviors** — from `Observer/`, `Plugin/`, `Service/`, `etc/events.xml`:
   - Events dispatched and observed
   - Plugins and their interception points
   - Cron jobs (`etc/crontab.xml`)
   - Queue consumers (`etc/communication.xml`, `etc/queue.xml`)

4. **Key Components** — all significant classes:
   - Services and their public methods
   - Repositories and their interface contracts
   - Block/ViewModel classes
   - Helpers (note if any exist — they violate the ViewModel rule)

5. **Tests** — from `Test/Unit/` and `Test/Integration/`:
   - Which behaviors are covered
   - Notable test gaps (important classes or methods without tests)

### Step 3: Write `docs/domain-<name>.md`

Create or overwrite the file with the following structure:

```markdown
# Domain: <Name>

**Last updated:** <date>
**Modules:** <comma-separated list of module paths>

## Summary

<2-3 sentence description of what this domain does and why it exists in the system>

## Domain Model

### Entities

| Entity | Table | Key Fields | Notes |
|--------|-------|------------|-------|
| <EntityName> | <table_name> | id, status, created_at... | <any notes> |

### State Machines

<For each entity with a status field, describe the valid transitions>

```
draft → active → redeemed
        active → cancelled
```

### Relationships

<Brief description or diagram of how entities relate to each other>

## API Endpoints

| Method | Route | Interface Method | ACL |
|--------|-------|-----------------|-----|
| GET | /V1/<domain>/... | `InterfaceName::method` | `Module::resource` |

<If no REST API exists, state: "No REST API endpoints. Domain is internal-only.">

## Key Behaviors

### Events

| Event Name | Dispatched In | Observed By | Purpose |
|-----------|---------------|-------------|---------|
| `<event_name>` | `Class::method` | `Observer\Name` | <what it triggers> |

### Plugins

| Plugin Class | Target | Type | Purpose |
|-------------|--------|------|---------|
| `Plugin\Name` | `TargetClass::method` | before/around/after | <what it changes> |

### Queues / Consumers

| Queue | Consumer | Payload | Purpose |
|-------|----------|---------|---------|
| `<queue.name>` | `Consumer\Name` | `DataInterface` | <async operation> |

### Cron Jobs

| Job Code | Schedule | Class | Purpose |
|----------|----------|-------|---------|
| `<job_code>` | `*/5 * * * *` | `Cron\Name` | <what it runs> |

## Key Components

### Services

| Class | Responsibility | Key Methods |
|-------|---------------|-------------|
| `Service\<Name>` | <one-line> | `method1()`, `method2()` |

### Repositories

| Interface | Implementation | Entity |
|-----------|---------------|--------|
| `Api\<Name>RepositoryInterface` | `Model\<Name>Repository` | `<Entity>` |

### ViewModels / Blocks

| Class | Template | Purpose |
|-------|----------|---------|
| `ViewModel\<Name>` | `view/frontend/templates/<name>.phtml` | <purpose> |

## Test Coverage

### Covered

- <list of classes/behaviors with tests>

### Gaps

- <list of classes or behaviors with no test coverage — flag critical ones>

## Features

<Numbered list of user-visible or business-visible features this domain provides, each with acceptance criteria>

### Feature 1: <Name>

**AC:**
- [ ] <criterion>
- [ ] <criterion>

### Feature 2: <Name>

**AC:**
- [ ] <criterion>
```

### Step 4: Update `docs/domain-index.md`

If `docs/domain-index.md` does not exist, create it with this header:

```markdown
# Domain Index

This file is the navigation map for all domain documentation in this project.
Agents that require project documentation or domain knowledge should read this file first, then follow links to specific domain files.

**Indexed domains:**

| Domain | File | Description |
|--------|------|-------------|
```

Then add (or update) the row for this domain:

```
| <Name> | [domain-<name>.md](domain-<name>.md) | <one-line summary> |
```

If the domain already has a row, update it in place.

### Step 5: Report

After writing both files, output a short summary:

```
## Docs written

- `docs/domain-<name>.md` — <N> entities, <N> API endpoints, <N> key components, <N> features
- `docs/domain-index.md` — updated

### Coverage gaps flagged

- <list any classes or behaviors that appear to have no test coverage>

### Suggested next domains

- <list any adjacent modules or concepts that appear related but were not included>
```

---

## Rules

- Read actual code — never guess field names, method signatures, or route paths.
- If a module directory is found but is empty or has only `registration.php`, note it as a stub and skip.
- If two modules clearly belong to the same domain (e.g. `Atlantis/TixxVoucher` and `Atlantis/TixxVoucherGenerator`), document them together under a single domain file.
- Do not document third-party vendor code (under `vendor/`).
- Mark any Helper classes found with a note: "⚠ Helper — should be migrated to ViewModel/Service per project standards."
- If `webapi.xml` is absent, state explicitly that no REST API exists.
- Keep entity field lists concise — include only fields that matter for planning (IDs, FKs, status, key business fields). Skip `created_at`, `updated_at` unless they drive behavior.
- The Features section must use present tense and be written from the perspective of the business stakeholder, not the developer.
