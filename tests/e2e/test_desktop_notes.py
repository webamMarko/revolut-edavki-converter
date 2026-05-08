"""Desktop investment notes CRUD tests."""

import pytest


def _go_to_notes(page, server_url):
    """Navigate to the notes page within the report."""
    page.goto(f"{server_url}/report")
    page.wait_for_selector("#summary", timeout=15000)
    page.locator('.nav-item[data-page="notes"]').click()
    page.wait_for_timeout(300)


class TestNotesView:
    def test_notes_page_shows_empty_state(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)
        empty = premium_desktop_page.locator("#notesEmpty")
        # May or may not be visible depending on existing notes
        notes_list = premium_desktop_page.locator("#notesList .note-card")
        if notes_list.count() == 0:
            assert empty.is_visible()

    def test_add_note_button_visible_for_premium(
        self, premium_desktop_page, server_url
    ):
        _go_to_notes(premium_desktop_page, server_url)
        assert premium_desktop_page.locator("#btnAddNote").is_visible()


class TestNotesModal:
    def test_open_close_modal_escape(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)
        assert premium_desktop_page.locator("#noteModal").is_visible()

        premium_desktop_page.keyboard.press("Escape")
        premium_desktop_page.wait_for_timeout(200)
        assert not premium_desktop_page.locator("#noteModal").is_visible()

    def test_open_close_modal_cancel(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)

        premium_desktop_page.locator(".btn-cancel").click()
        premium_desktop_page.wait_for_timeout(200)
        assert not premium_desktop_page.locator("#noteModal").is_visible()

    def test_note_validation(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)

        # Try to save without filling fields
        premium_desktop_page.locator("#btnSaveNote").click()
        premium_desktop_page.wait_for_timeout(300)

        error = premium_desktop_page.locator("#noteModalError")
        assert error.text_content().strip() != ""


class TestNotesCRUD:
    def test_create_note(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)

        premium_desktop_page.locator("#nfTitle").fill("Test Note Title")
        premium_desktop_page.locator("#nfSummary").fill("Test summary text")
        premium_desktop_page.locator("#btnSaveNote").click()
        premium_desktop_page.wait_for_timeout(500)

        # Modal should close
        assert not premium_desktop_page.locator("#noteModal").is_visible()

        # Note card should appear
        cards = premium_desktop_page.locator("#notesList .note-card")
        assert cards.count() > 0
        assert "Test Note Title" in cards.last.text_content()

    def test_expand_note(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        # Create a note first
        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)
        premium_desktop_page.locator("#nfTitle").fill("Expandable Note")
        premium_desktop_page.locator("#nfSummary").fill("Click to expand")
        premium_desktop_page.locator("#btnSaveNote").click()
        premium_desktop_page.wait_for_timeout(500)

        # Find the card containing "Expandable Note"
        card = premium_desktop_page.locator(
            "#notesList .note-card", has_text="Expandable Note"
        ).first
        card.locator(".note-header").click()
        premium_desktop_page.wait_for_timeout(300)

        # Detail section should be visible
        detail = card.locator(".note-detail")
        assert detail.is_visible()

    def test_edit_note(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        # Create a note
        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)
        premium_desktop_page.locator("#nfTitle").fill("Edit Me")
        premium_desktop_page.locator("#nfSummary").fill("Original summary")
        premium_desktop_page.locator("#btnSaveNote").click()
        premium_desktop_page.wait_for_timeout(500)

        # Find the card containing "Edit Me"
        card = premium_desktop_page.locator(
            "#notesList .note-card", has_text="Edit Me"
        ).first
        card.locator(".note-header").click()
        premium_desktop_page.wait_for_timeout(300)

        # Click Edit
        card.locator(".note-action-btn.edit").click()
        premium_desktop_page.wait_for_timeout(300)

        # Modal should open with pre-filled title
        assert premium_desktop_page.locator("#noteModal").is_visible()
        title_val = premium_desktop_page.locator("#nfTitle").input_value()
        assert "Edit Me" in title_val

        # Change the title
        premium_desktop_page.locator("#nfTitle").fill("Edited Title")
        premium_desktop_page.locator("#btnSaveNote").click()
        premium_desktop_page.wait_for_timeout(500)

        # Verify the title was updated
        card = premium_desktop_page.locator(
            "#notesList .note-card", has_text="Edited Title"
        ).first
        assert card.is_visible()

    def test_delete_note(self, premium_desktop_page, server_url):
        _go_to_notes(premium_desktop_page, server_url)

        # Create a note
        premium_desktop_page.locator("#btnAddNote").click()
        premium_desktop_page.wait_for_timeout(200)
        premium_desktop_page.locator("#nfTitle").fill("Delete Me")
        premium_desktop_page.locator("#nfSummary").fill("Will be deleted")
        premium_desktop_page.locator("#btnSaveNote").click()
        premium_desktop_page.wait_for_timeout(500)

        count_before = premium_desktop_page.locator("#notesList .note-card").count()

        # Find the card containing "Delete Me"
        card = premium_desktop_page.locator(
            "#notesList .note-card", has_text="Delete Me"
        ).first
        card.locator(".note-header").click()
        premium_desktop_page.wait_for_timeout(300)

        # Handle confirm dialog
        premium_desktop_page.on("dialog", lambda d: d.accept())

        # Click Delete
        card.locator(".note-action-btn.del").click()
        premium_desktop_page.wait_for_timeout(500)

        count_after = premium_desktop_page.locator("#notesList .note-card").count()
        assert count_after < count_before
