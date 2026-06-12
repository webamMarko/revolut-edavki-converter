"""TDD tests for SAA-613 (SAA-576b): empty state role gating + 'Manage Properties' link.

Spec: the RE empty state CTA must only render for premium/admin/cofounder users
(hidden for guests), and the section header must show a 'Manage Properties' link
to /properties.
"""
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RE_JS_PATH = PROJECT_ROOT / "src" / "templates" / "assets" / "sections" / "real_estate.js"
RE_HTML_PATH = PROJECT_ROOT / "src" / "templates" / "sections" / "real_estate.html.j2"


def _js() -> str:
    return RE_JS_PATH.read_text(encoding="utf-8")


def _html() -> str:
    return RE_HTML_PATH.read_text(encoding="utf-8")


class TestEmptyStateRoleGating(unittest.TestCase):
    """Empty state must only be rendered for premium/admin/cofounder users."""

    def test_empty_state_branch_checks_user_role(self):
        js = _js()
        empty_idx = js.find('reEmptyState')
        self.assertGreater(empty_idx, -1, "JS must reference reEmptyState")
        preceding = js[:empty_idx]
        role_check_idx = preceding.rfind("D.user")
        self.assertGreater(role_check_idx, -1,
            "A D.user role check must precede the reEmptyState rendering")

    def test_role_check_allows_premium_admin_cofounder(self):
        js = _js()
        for role in ("premium", "admin", "cofounder"):
            self.assertIn(f"'{role}'", js,
                f"Role guard must include '{role}' so empty state shows for that role")

    def test_role_check_uses_includes_or_equivalent_membership_test(self):
        js = _js()
        self.assertTrue(
            re.search(r"\[\s*'premium'\s*,\s*'admin'\s*,\s*'cofounder'\s*\]\.includes\(", js),
            "Role guard must test D.user.role membership against "
            "['premium', 'admin', 'cofounder']"
        )


class TestManagePropertiesLink(unittest.TestCase):
    """Section header must expose a 'Manage Properties' link to /properties."""

    def test_html_has_manage_link_with_data_role(self):
        html = _html()
        self.assertIn('data-role="reManageLink"', html,
            "real_estate.html.j2 must have a data-role='reManageLink' element")

    def test_manage_link_points_to_properties_page(self):
        html = _html()
        idx = html.find('data-role="reManageLink"')
        self.assertGreater(idx, -1)
        tag_start = html.rfind('<a', 0, idx)
        tag_end = html.find('>', idx)
        tag = html[tag_start:tag_end + 1]
        self.assertIn('href="/properties"', tag,
            "Manage Properties link must point to /properties")

    def test_manage_link_text_mentions_manage_properties(self):
        html = _html()
        idx = html.find('data-role="reManageLink"')
        tag_end = html.find('>', idx)
        close_idx = html.find('</a>', tag_end)
        link_text = html[tag_end + 1:close_idx]
        self.assertIn('Manage Properties', link_text,
            "Manage Properties link text must read 'Manage Properties'")

    def test_manage_link_lives_inside_section_header(self):
        html = _html()
        h2_start = html.find('<h2>')
        h2_end = html.find('</h2>')
        link_idx = html.find('data-role="reManageLink"')
        self.assertGreater(h2_start, -1)
        self.assertGreater(h2_end, h2_start)
        self.assertTrue(h2_start < link_idx < h2_end,
            "Manage Properties link must be inside the <h2> section header")


if __name__ == "__main__":
    unittest.main()
