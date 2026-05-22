"""Test offline banner implementation for PWA."""

import unittest
from pathlib import Path


class TestOfflineBanner(unittest.TestCase):
    """Test offline detection banner."""

    def setUp(self):
        """Set up test paths."""
        self.project_root = Path(__file__).parent.parent
        self.base_template_path = self.project_root / "src" / "templates" / "base.html.j2"
        self.common_css_path = self.project_root / "src" / "templates" / "assets" / "common.css"

    def test_base_template_has_offline_banner(self):
        """Verify base template includes offline banner HTML."""
        content = self.base_template_path.read_text()
        self.assertIn('id="offline-banner"', content, "Should have offline banner element")
        self.assertIn("offline-banner-content", content, "Should have banner content container")
        self.assertIn("offline-text", content, "Should have offline text element")
        self.assertIn("offline-dismiss", content, "Should have dismiss button")

    def test_base_template_has_offline_detection_script(self):
        """Verify base template includes offline detection JavaScript."""
        content = self.base_template_path.read_text()
        self.assertIn("showOfflineBanner", content, "Should define showOfflineBanner function")
        self.assertIn("hideOfflineBanner", content, "Should define hideOfflineBanner function")
        self.assertIn("dismissOfflineBanner", content, "Should define dismissOfflineBanner function")

    def test_offline_script_listens_to_events(self):
        """Verify offline script listens to online/offline events."""
        content = self.base_template_path.read_text()
        self.assertIn("addEventListener('online'", content, "Should listen to online event")
        self.assertIn("addEventListener('offline'", content, "Should listen to offline event")
        self.assertIn("navigator.onLine", content, "Should check navigator.onLine")

    def test_offline_banner_auto_dismisses_on_online(self):
        """Verify banner auto-dismisses when connection restored."""
        content = self.base_template_path.read_text()
        # Check that online event handler calls hideOfflineBanner
        lines = content.split('\n')
        online_handler_found = False
        hide_call_found = False

        for i, line in enumerate(lines):
            if "addEventListener('online'" in line:
                online_handler_found = True
                # Check next few lines for hideOfflineBanner call
                for j in range(i, min(i + 5, len(lines))):
                    if 'hideOfflineBanner' in lines[j]:
                        hide_call_found = True
                        break

        self.assertTrue(online_handler_found, "Should have online event listener")
        self.assertTrue(hide_call_found, "Online handler should call hideOfflineBanner")

    def test_offline_banner_shows_on_offline(self):
        """Verify banner shows when connection lost."""
        content = self.base_template_path.read_text()
        # Check that offline event handler calls showOfflineBanner
        lines = content.split('\n')
        offline_handler_found = False
        show_call_found = False

        for i, line in enumerate(lines):
            if "addEventListener('offline'" in line:
                offline_handler_found = True
                # Check next few lines for showOfflineBanner call
                for j in range(i, min(i + 5, len(lines))):
                    if 'showOfflineBanner' in lines[j]:
                        show_call_found = True
                        break

        self.assertTrue(offline_handler_found, "Should have offline event listener")
        self.assertTrue(show_call_found, "Offline handler should call showOfflineBanner")

    def test_offline_banner_css_exists(self):
        """Verify offline banner CSS is defined."""
        content = self.common_css_path.read_text()
        self.assertIn(".offline-banner", content, "Should define offline-banner class")
        self.assertIn("position: fixed", content, "Banner should be fixed position")
        self.assertIn("top: 0", content, "Banner should be at top")
        self.assertIn("z-index", content, "Banner should have high z-index")

    def test_offline_banner_has_dismiss_button_styling(self):
        """Verify dismiss button is styled."""
        content = self.common_css_path.read_text()
        self.assertIn(".offline-dismiss", content, "Should define offline-dismiss class")
        self.assertIn("cursor: pointer", content, "Dismiss button should be clickable")

    def test_offline_banner_has_animation(self):
        """Verify banner has slide-down animation."""
        content = self.common_css_path.read_text()
        self.assertIn("@keyframes slideDown", content, "Should define slideDown animation")
        self.assertIn("animation:", content, "Banner should use animation")

    def test_offline_banner_has_icon(self):
        """Verify banner includes offline icon."""
        content = self.base_template_path.read_text()
        self.assertIn("offline-icon", content, "Should have offline icon element")
        self.assertIn("<svg", content, "Icon should be SVG")

    def test_offline_banner_is_responsive(self):
        """Verify banner has mobile-responsive styles."""
        content = self.common_css_path.read_text()
        # Check if there's a media query affecting the banner
        self.assertIn("@media", content, "Should have media queries")


if __name__ == "__main__":
    unittest.main()
