"""Дымовой UI-тест: главная страница открывается. Остальные UI-тесты — через Page Object (ЛР3)."""

from playwright.sync_api import Page, expect


def test_home_page_opens(page: Page):
    page.goto("/")
    expect(page).to_have_title("Книжная лавка")
