# Technical Specification: Migrate Inline HTML to Jinja2 Templates

**Epic:** SAA-15
**PRD:** specs/SAA-15.md
**Created:** 2026-05-22

## Overview

Migrate 16 inline HTML f-string functions (~2,200 lines) from `src/web.py` into Jinja2 templates under `src/templates/pages/`, using a shared base template and partials. The existing Jinja2 Environment in `src/html_report.py` is extended to serve both report and page templates.

## Architecture

### Template Hierarchy

```
src/templates/
├── base.html.j2              # NEW: shared layout (head, nav, footer, theme, scripts)
├── partials/
│   ├── nav.html.j2           # NEW: from _header_html()
│   └── drop_import.html.j2   # NEW: from _global_drop_import_html()
├── pages/
│   ├── login.html.j2         # NEW: from _login_html()
│   ├── invite.html.j2        # NEW: from _invite_html()
│   ├── reset_password_request.html.j2
│   ├── reset_password_confirm.html.j2
│   ├── error.html.j2
│   ├── shared_expired.html.j2
│   ├── account.html.j2
│   ├── admin.html.j2
│   ├── settings.html.j2
│   ├── pricing.html.j2
│   ├── upload.html.j2
│   └── import_wizard.html.j2
├── assets/
│   ├── common.css            # NEW: from _COMMON_CSS
│   ├── styles.css            # existing (report)
│   └── ...                   # existing JS assets
├── sections/                 # existing (report)
└── report.html.j2            # existing (untouched)
```

### Jinja2 Environment Setup

Create a shared `_page_env` in `src/web.py`:

```python
from jinja2 import Environment, FileSystemLoader
from src.i18n import get_translations

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_page_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)
_page_env.globals["t"] = lambda key, lang="en": get_translations(lang).get(key, key)
```

Each `_serve_*` method calls `_page_env.get_template("pages/foo.html.j2").render(...)` instead of calling `_foo_html()`.

### base.html.j2 Structure

```jinja2
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  {% block meta %}{% endblock %}
  {{ fouc_script }}
  <title>{% block title %}WealthEagle{% endblock %}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/common.css">
  {% block extra_css %}{% endblock %}
</head>
<body>
  {% block header %}
    {% if show_header %}
      {% include "partials/nav.html.j2" %}
    {% endif %}
  {% endblock %}

  {% block content %}{% endblock %}

  {% if show_drop_import %}
    {% include "partials/drop_import.html.j2" %}
  {% endif %}

  {{ common_js }}
  {% block extra_js %}{% endblock %}
</body>
</html>
```

### Static File Serving

Add a route for `/static/common.css` in `do_GET()` that serves `src/templates/assets/common.css` with `Content-Type: text/css` and `Cache-Control: public, max-age=3600`.

### Migration Pattern Per Page

For each `_*_html()` function:

1. Create `pages/<name>.html.j2` extending `base.html.j2`
2. Move HTML body content into `{% block content %}`
3. Replace f-string variables with Jinja2 `{{ variable }}` expressions
4. Replace conditional blocks with `{% if %}`/`{% else %}`/`{% endif %}`
5. Update the `_serve_*` method to render the template with context dict
6. Delete the old `_*_html()` function

### i18n Integration

- Register `t` as a Jinja2 global that accepts `(key, lang="en")`
- The `lang` parameter comes from the user's session or browser Accept-Language
- Templates use `{{ t("nav.login") }}` for server-rendered strings
- JS translations continue to be loaded separately for client-side dynamic content

### Security: Autoescape

`autoescape=True` on the Environment ensures all `{{ }}` expressions are HTML-escaped by default. Use `{{ value|safe }}` only for pre-sanitized HTML (e.g., rendered Chart.js containers). This is an improvement over the current f-string approach which has no automatic escaping.

## Implementation Tasks (Subtasks)

### Subtask A: Base Template + Auth Pages
- Create `base.html.j2`, `partials/nav.html.j2`, `partials/drop_import.html.j2`
- Extract `_COMMON_CSS` to `assets/common.css`
- Add `/static/common.css` route
- Set up `_page_env` with `t()` global
- Migrate: `_login_html`, `_invite_html`, `_reset_password_request_html`, `_reset_password_confirm_html`
- **Test**: login, invite, reset-password E2E flows

### Subtask B: Admin/Settings/Account Pages
- Migrate: `_account_html`, `_admin_html`, `_settings_html`
- **Test**: admin user management, settings, account page E2E

### Subtask C: Dashboard/Upload/Import Pages
- Migrate: `_upload_html`, `_import_wizard_html`, `_import_wizard_html_with_user`
- **Test**: file upload, import wizard preview/validate/run E2E

### Subtask D: Pricing/Error/Misc Pages
- Migrate: `_pricing_html`, `_error_html`, `_shared_expired_html`
- Delete remaining inline HTML helper functions
- Final cleanup: remove `_COMMON_CSS`, `_COMMON_JS` constants if fully absorbed
- **Test**: full E2E suite, verify zero inline HTML remains

## Risks

- **Large CSS block**: moving `_COMMON_CSS` to a static file adds an HTTP request; mitigated by Cache-Control headers
- **Template variable mismatches**: f-string variables must map 1:1 to template context; test each page after migration
- **`_COMMON_JS` embedding**: some JS references Python variables — these need to become template variables or data attributes

## Dependencies

- Jinja2 already in `requirements.txt` (used by `html_report.py`)
- No new dependencies required
