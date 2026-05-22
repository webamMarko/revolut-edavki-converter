"""Test service worker implementation for PWA."""

import unittest
from pathlib import Path


class TestServiceWorker(unittest.TestCase):
    """Test service worker file and integration."""

    def setUp(self):
        """Set up test paths."""
        self.project_root = Path(__file__).parent.parent
        self.sw_path = self.project_root / "src" / "templates" / "assets" / "sw.js"
        self.server_path = self.project_root / "src" / "web" / "server.py"
        self.base_template_path = self.project_root / "src" / "templates" / "base.html.j2"

    def test_service_worker_file_exists(self):
        """Verify sw.js file exists."""
        self.assertTrue(self.sw_path.exists(), "Service worker file should exist")

    def test_service_worker_has_cache_version(self):
        """Verify service worker has cache versioning."""
        content = self.sw_path.read_text()
        self.assertIn("CACHE_VERSION", content, "Service worker should define cache version")
        self.assertIn("STATIC_CACHE", content, "Service worker should define static cache name")
        self.assertIn("DYNAMIC_CACHE", content, "Service worker should define dynamic cache name")

    def test_service_worker_has_event_listeners(self):
        """Verify service worker has required event listeners."""
        content = self.sw_path.read_text()
        self.assertIn("addEventListener('install'", content, "Should have install event listener")
        self.assertIn("addEventListener('activate'", content, "Should have activate event listener")
        self.assertIn("addEventListener('fetch'", content, "Should have fetch event listener")

    def test_service_worker_caches_static_assets(self):
        """Verify service worker pre-caches static assets."""
        content = self.sw_path.read_text()
        self.assertIn("STATIC_ASSETS", content, "Should define static assets array")
        self.assertIn("/static/common.css", content, "Should cache common.css")
        self.assertIn("/manifest.json", content, "Should cache manifest")
        self.assertIn("/static/icons/", content, "Should cache icons")

    def test_service_worker_route_exists(self):
        """Verify /sw.js route is defined in server.py."""
        content = self.server_path.read_text()
        self.assertIn('path == "/sw.js"', content, "Should have /sw.js route")
        self.assertIn("_serve_service_worker", content, "Should call _serve_service_worker method")

    def test_service_worker_method_exists(self):
        """Verify _serve_service_worker method exists in server.py."""
        content = self.server_path.read_text()
        self.assertIn("def _serve_service_worker(self):", content, "Should define _serve_service_worker method")
        self.assertIn('Content-Type", "application/javascript', content, "Should set JavaScript content type")
        self.assertIn("no-cache", content, "Service worker should use no-cache header")

    def test_base_template_has_registration(self):
        """Verify base template includes service worker registration."""
        content = self.base_template_path.read_text()
        self.assertIn("serviceWorker", content, "Base template should reference serviceWorker")
        self.assertIn("navigator.serviceWorker.register", content, "Should call register method")
        self.assertIn("/sw.js", content, "Should register /sw.js")

    def test_service_worker_cache_strategies(self):
        """Verify service worker implements correct cache strategies."""
        content = self.sw_path.read_text()
        # Should have cache-first logic for static assets
        self.assertIn("caches.match(request)", content, "Should check cache first")
        # Should have network-first logic for dynamic content
        self.assertIn("fetch(request)", content, "Should fetch from network")
        # Should handle offline scenarios
        self.assertIn("catch", content, "Should handle network failures")

    def test_service_worker_cleans_old_caches(self):
        """Verify service worker cleans up old caches on activate."""
        content = self.sw_path.read_text()
        self.assertIn("caches.delete", content, "Should delete old caches")
        self.assertIn("activate", content, "Should handle activate event")


if __name__ == "__main__":
    unittest.main()
