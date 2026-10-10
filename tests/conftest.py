"""Shared pytest fixtures for headless wxPython UI and accessibility tests."""

from __future__ import annotations

from collections.abc import Generator
import pytest
import wx


@pytest.fixture(scope="session")
def wx_app() -> Generator[wx.App, None, None]:
    """Provide a shared wx.App instance for the test session."""
    app = wx.App.Get()
    if app is None:
        app = wx.App(False)
    yield app
