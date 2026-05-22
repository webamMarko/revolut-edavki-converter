"""Jinja2 environment and common HTML rendering helpers."""

from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from src.i18n import get_translations

# Jinja2 Environment for page templates
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
page_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)
page_env.globals["t"] = lambda key, lang="en": get_translations(lang).get(key, key)

# Prevent flash of unstyled content — runs before paint
FOUC_SCRIPT = (
    "<script>(function(){var t=localStorage.getItem('theme');"
    "if(!t&&window.matchMedia&&window.matchMedia('(prefers-color-scheme:light)').matches)t='light';"
    "if(t)document.documentElement.setAttribute('data-theme',t);})()</script>"
)

# Theme toggle JS — same logic as report's nav.js
COMMON_JS = r"""
<script>
function toggleTheme(){
  var c=document.documentElement.getAttribute('data-theme');
  var n=c==='light'?'dark':'light';
  if(n==='dark'){document.documentElement.removeAttribute('data-theme');localStorage.removeItem('theme');}
  else{document.documentElement.setAttribute('data-theme',n);localStorage.setItem('theme',n);}
  document.querySelectorAll('.theme-icon').forEach(function(el){el.textContent=n==='light'?'\u{1F319}':'☀️';});
}
(function(){
  var isDark=document.documentElement.getAttribute('data-theme')!=='light';
  document.querySelectorAll('.theme-icon').forEach(function(el){el.textContent=isDark?'☀️':'\u{1F319}';});
})();
</script>
"""


def html_response(handler, html: str, status: int = 200):
    """Send an HTML response."""
    encoded = html.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(encoded)))
    handler._add_security_headers()
    handler.end_headers()
    handler.wfile.write(encoded)


def error_response(handler, message: str, status: int = 400):
    """Render and send an error page using the error template."""
    template = page_env.get_template("pages/error.html.j2")
    html = template.render(
        message=message,
        fouc_script=FOUC_SCRIPT,
        common_js=COMMON_JS,
        show_header=False,
        show_drop_import=False
    )
    html_response(handler, html, status=status)


def json_response(handler, data, status=200):
    """Send a JSON response."""
    import json
    body = json.dumps(data).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler._add_security_headers()
    handler.end_headers()
    handler.wfile.write(body)


def redirect(handler, path: str):
    """Send a redirect response."""
    handler.send_response(302)
    handler.send_header("Location", path)
    handler.end_headers()
