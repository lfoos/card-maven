import json

import pytest
import structlog

from card_maven.shared.logging import configure_logging, get_logger


def test_json_logs_include_bound_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)
    structlog.contextvars.bind_contextvars(request_id="req-123")
    try:
        get_logger("test").info("hello", count=2)
    finally:
        structlog.contextvars.clear_contextvars()
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["event"] == "hello"
    assert line["count"] == 2
    assert line["request_id"] == "req-123"
    assert line["level"] == "info"


def test_level_filters(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", json=True)
    get_logger("test").info("hidden")
    assert "hidden" not in capsys.readouterr().out


def test_console_renderer(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=False)
    get_logger("test").info("readable")
    assert "readable" in capsys.readouterr().out
