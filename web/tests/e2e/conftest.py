"""Pytest fixtures for Playwright e2e tests.

Session #7 W3-A — structural-isomorphism e2e baseline.
"""
import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def playwright_instance():
    with sync_playwright() as p:
        yield p


@pytest.fixture
def browser(playwright_instance):
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture
def page(browser):
    # Grant clipboard permissions so tests for copy-link / share buttons
    # (Session #18 education assets) exercise the real navigator.clipboard
    # path — headless Chromium otherwise blocks writeText(). Harmless to
    # tests that don't touch the clipboard.
    context = browser.new_context(
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = context.new_page()
    yield page
    context.close()
