"""Tests for custom dashboard API endpoints (SAA-88)."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from src import users


@pytest.fixture
def users_db():
    """Create a temporary users database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        users_db_path = Path(tmpdir) / "test_users.db"
        yield users_db_path


# Phase 1: Backend - Tasks 1-8 (DB Migration & API)

class TestDashboardLayoutMigration:
    """Test dashboard_layout column migration."""

    def test_migration_adds_dashboard_layout_column(self, users_db):
        """Task 1: Verify dashboard_layout column is added to users table."""
        # Initialize the users database (triggers migration)
        conn = users.get_users_connection(users_db)

        # Check the column exists
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        assert "dashboard_layout" in columns, "dashboard_layout column should exist"
        assert columns["dashboard_layout"] == "TEXT", "dashboard_layout should be TEXT type"

        conn.close()

    def test_dashboard_layout_column_defaults_to_null(self, users_db):
        """Task 1: Verify dashboard_layout defaults to NULL for new users."""
        conn = users.get_users_connection(users_db)

        # Create a test user
        conn.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            ("testuser", "test@example.com", "hash", "premium")
        )
        conn.commit()

        # Check the default value
        cursor = conn.execute("SELECT dashboard_layout FROM users WHERE username = ?", ("testuser",))
        result = cursor.fetchone()

        assert result[0] is None, "dashboard_layout should default to NULL"

        conn.close()


class TestDashboardLayoutAPI:
    """Test PUT/GET /api/dashboard-layout endpoints."""

    def test_save_valid_layout(self, users_db):
        """Task 3: PUT with valid layout saves successfully."""
        # This will test the save_dashboard_layout() function when implemented
        from src.web import api

        conn = users.get_users_connection(users_db)

        # Create a test user
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # Valid layout JSON
        layout = {
            "widgets": [
                {"id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2},
                {"id": "summary", "x": 4, "y": 0, "w": 4, "h": 2}
            ]
        }

        # Save layout (function to be implemented)
        result = api.save_dashboard_layout(user.id, layout, conn)

        assert result is True, "save_dashboard_layout should return True on success"

        # Verify it was saved
        cursor = conn.execute("SELECT dashboard_layout FROM users WHERE id = ?", (user.id,))
        saved = cursor.fetchone()
        assert saved[0] is not None, "dashboard_layout should be saved"

        import json
        saved_layout = json.loads(saved[0])
        assert len(saved_layout["widgets"]) == 2, "Should have 2 widgets"

        conn.close()

    def test_save_layout_rejects_invalid_widget_id(self, users_db):
        """Task 3: PUT with invalid widget ID is rejected."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # Invalid widget ID
        layout = {
            "widgets": [
                {"id": "invalid-widget", "x": 0, "y": 0, "w": 4, "h": 2}
            ]
        }

        with pytest.raises(ValueError, match="Invalid widget ID"):
            api.save_dashboard_layout(user.id, layout, conn)

        conn.close()

    def test_save_layout_rejects_too_many_widgets(self, users_db):
        """Task 3: PUT with too many widgets (>16) is rejected."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # 17 widgets (exceeds max of 16)
        layout = {
            "widgets": [
                {"id": "quick-glance", "x": 0, "y": i, "w": 4, "h": 2}
                for i in range(17)
            ]
        }

        with pytest.raises(ValueError, match="Too many widgets"):
            api.save_dashboard_layout(user.id, layout, conn)

        conn.close()

    def test_save_layout_rejects_negative_coordinates(self, users_db):
        """Task 3: PUT with negative x/y/w/h is rejected."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # Negative coordinates
        layout = {
            "widgets": [
                {"id": "quick-glance", "x": -1, "y": 0, "w": 4, "h": 2}
            ]
        }

        with pytest.raises(ValueError, match="Invalid coordinates"):
            api.save_dashboard_layout(user.id, layout, conn)

        conn.close()

    def test_save_layout_rejects_duplicate_widget_ids(self, users_db):
        """Task 3: PUT with duplicate widget IDs is rejected."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # Duplicate widget ID
        layout = {
            "widgets": [
                {"id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2},
                {"id": "quick-glance", "x": 4, "y": 0, "w": 4, "h": 2}
            ]
        }

        with pytest.raises(ValueError, match="Duplicate widget"):
            api.save_dashboard_layout(user.id, layout, conn)

        conn.close()

    def test_get_layout_returns_saved(self, users_db):
        """Task 5: GET returns saved layout."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # Save a layout
        layout = {
            "widgets": [
                {"id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2}
            ]
        }
        api.save_dashboard_layout(user.id, layout, conn)

        # Get it back
        result = api.get_dashboard_layout(user.id, conn)

        assert result["isDefault"] is False, "Should not be default"
        assert len(result["widgets"]) == 1, "Should have 1 widget"
        assert result["widgets"][0]["id"] == "quick-glance"

        conn.close()

    def test_get_layout_returns_default_when_none_saved(self, users_db):
        """Task 5: GET returns default layout when none saved."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        # Get layout without saving anything
        result = api.get_dashboard_layout(user.id, conn)

        assert result["isDefault"] is True, "Should be default"
        assert len(result["widgets"]) == 4, "Default should have 4 widgets"
        widget_ids = [w["id"] for w in result["widgets"]]
        assert "quick-glance" in widget_ids
        assert "summary" in widget_ids
        assert "charts" in widget_ids
        assert "positions" in widget_ids

        conn.close()


class TestDashboardLayoutRoleGating:
    """Test role-based access control for dashboard layout endpoints."""

    def test_premium_user_can_save_layout(self, users_db):
        """Task 7: Premium users can save layouts."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        layout = {"widgets": [{"id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2}]}
        result = api.save_dashboard_layout(user.id, layout, conn)

        assert result is True, "Premium user should be able to save layout"
        conn.close()

    def test_admin_user_can_save_layout(self, users_db):
        """Task 7: Admin users can save layouts."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="admin", conn=conn)

        layout = {"widgets": [{"id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2}]}
        result = api.save_dashboard_layout(user.id, layout, conn)

        assert result is True, "Admin user should be able to save layout"
        conn.close()

    def test_premium_user_can_get_layout(self, users_db):
        """Task 7: Premium users can get layouts."""
        from src.web import api

        conn = users.get_users_connection(users_db)
        user, _ = users.create_user("test@example.com", role="premium", conn=conn)

        result = api.get_dashboard_layout(user.id, conn)

        assert result is not None, "Premium user should be able to get layout"
        assert "widgets" in result
        conn.close()
