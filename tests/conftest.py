"""Shared pytest fixtures and markers."""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "gui: tests that open a PsychoPy window (require a display)",
    )
