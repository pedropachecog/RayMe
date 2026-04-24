"""Backend harness smoke tests."""

from fastapi import FastAPI

from app.main import create_app


def test_main_exports_create_app() -> None:
    assert callable(create_app)


def test_create_app_sets_api_title(app: FastAPI) -> None:
    assert app.title == "RayMe Web UI API"
