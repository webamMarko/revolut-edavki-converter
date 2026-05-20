# Architecture Reference

> This document is the primary input for the `architect-advisor` agent. When an architecture decision arises — during brainstorming, spec writing, or implementation — invoke that agent. It will read this file and return a structured recommendation with options, rationale, and consequences.

## Repo Layout

Two repos in one working tree:
- **`dev-environment`** (this repo) — Docker Compose, `bin/` scripts, `env/`, `config/`
- **`src/`** (separate git repo, gitignored) — Magento 2.4.7-p8 CE application

All PHP runs inside the `phpfpm` container. Commands are proxied via `bin/` scripts.

## Custom Module Namespaces

| Namespace | Role |
|-----------|------|
| `Atlantis/` | **Primary** — business logic (Sales, Checkout, Customer, Catalog, Payments, Vouchers) |
| `Dhimahi/` | Utility/infrastructure (GDPR, SEO, AI content, image import) |
| `Eventim/` | External integrations (SSO, Tixx ticketing API) |
| `Plazathemes/` | Theme modules |

Custom modules live in `src/app/code/<Namespace>/<Module>/`.

## Standard Module Structure

```
etc/module.xml          # module metadata & sequence dependencies
etc/di.xml              # DI config: preferences, plugins, virtual types
etc/events.xml          # event observers
etc/adminhtml/system.xml # admin config UI
Block/                  # UI blocks (legacy; prefer ViewModel)
Controller/             # HTTP controllers
Model/                  # business logic & ORM entities
ResourceModel/          # DB access (resource + collection)
Api/Data/               # DTO interfaces (data contracts)
Plugin/                 # interceptors (before/after/around)
Observer/               # event listeners
Setup/                  # schema patches & data patches
view/frontend/templates/ # .phtml templates
view/adminhtml/          # admin templates & UI components
i18n/en_US.csv          # translations (required for all __() strings)
i18n/de_DE.csv
Test/Unit/              # unit tests (no DB/container needed)
Test/Integration/       # integration tests
```

## DI Patterns

```xml
<!-- Replace interface with concrete class -->
<preference for="Vendor\Api\SomeInterface" type="Vendor\Model\SomeModel"/>

<!-- Inject dependencies into a service -->
<type name="Vendor\Model\MyService">
  <arguments>
    <argument name="helper" xsi:type="object">Vendor\Model\OtherService</argument>
  </arguments>
</type>

<!-- Register a plugin interceptor -->
<type name="Magento\Core\SomeClass">
  <plugin name="vendor_module_plugin" type="Vendor\Plugin\SomePlugin"/>
</type>
```

## Core Design Rules

**PHP**
- PHP 8.3+, fully typed: properties, arguments, return types (including `void`)
- Constructor injection only — no `ObjectManager::getInstance()`, no `new Foo()` in business logic
- Depend on interfaces, not concrete classes
- Use Repository interfaces to load/save entities; Factory only when no repository exists or creating new unsaved models
- No inline FQCNs — always add `use` imports; alias on collision
- No Helper classes — create focused service classes instead
- No logic in constructors

**Templates**
- ViewModel (implements `ArgumentInterface`) instead of Helper — inject via layout XML, access via `$block->getData('...')`
- Every interactive/structural HTML element needs `data-ui-id="kebab-case-name"` — QA uses these exclusively
- All user-facing strings wrapped in `__()` with entries in both `i18n/en_US.csv` and `i18n/de_DE.csv`

**Unit testability**
- Mock with Mockery for generated/factory classes; PHPUnit `createMock()` for real interfaces
- No static methods or global state in business logic
- No raw `curl_*` or direct I/O inline — wrap in injectable service

## External API Clients (private Satis packages)

- `atlantis/eventim-tixx-auth-client` — SSO/auth
- `atlantis/eventim-tixx-client` — Tixx ticketing API
- `atlantis/eventim-voucher-client` — Voucher/gift card API
- `atlantis/magento-rest-client` — Magento REST

## Frontend Theme

`src/app/design/frontend/Eventim/` — custom storefront theme (Hyva-compatible).
Hyva modules exist for Checkout (`CheckoutHyva`), `ShirtConfiguratorHyva`, `VoucherDiscountTotalHyva`.

## Code Quality (pre-commit, must all pass)

1. `php-cs-fixer` — auto-fix + re-stage
2. `phpcs` — Magento2 coding standard
3. `phplint`
4. `phpstan` — level 5
5. `phpunit` — full test suite

Run manually: `bin/phpcs`, `bin/phpcbf`, `bin/analyse`, `bin/dev-test-run unit|integration`

## Git Workflow

Use `/git-gitlab-vcs` skill for commit, push, branch, MR (default target: `develop`).
Never skip hooks (`--no-verify`).

## After Code Changes

```bash
bin/cache-clean                  # quick cache clear
bin/magento cache:flush          # full flush
bin/dhimahi-full-compile         # di:compile + upgrade + static content + reindex + cache flush
```
