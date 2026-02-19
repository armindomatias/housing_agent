"""Unit tests for the structlog logging configuration."""

import structlog

from app.logging_config import setup_logging


class TestSetupLogging:
    def test_setup_logging_runs_without_error_debug(self):
        setup_logging(debug=True)
        logger = structlog.get_logger("test")
        # Should not raise
        logger.info("test_event", key="value")

    def test_setup_logging_runs_without_error_production(self):
        setup_logging(debug=False)
        logger = structlog.get_logger("test")
        # Should not raise
        logger.info("test_event", key="value")


class TestStructlogContextBinding:
    def test_context_binding_works(self):
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="test-123", property_url="https://example.com")

        bound = structlog.contextvars.get_contextvars()
        assert bound["request_id"] == "test-123"
        assert bound["property_url"] == "https://example.com"

        structlog.contextvars.clear_contextvars()
        assert structlog.contextvars.get_contextvars() == {}

    def test_context_cleared_between_requests(self):
        structlog.contextvars.bind_contextvars(request_id="req-1")
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="req-2")

        assert structlog.contextvars.get_contextvars()["request_id"] == "req-2"
        structlog.contextvars.clear_contextvars()
