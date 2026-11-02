"""Фикстуры для UI-тестов на Playwright (pytest-playwright).

base_url переопределён: page.goto("/") открывает учебное приложение на live_server.
Перед каждым UI-тестом данные магазина сбрасываются.
"""

import pytest


@pytest.fixture(scope="session")
def base_url(live_server):
    return live_server.url


@pytest.fixture(autouse=True)
def _fresh_shop(live_server):
    live_server.reset()
