"""structlog configuration module."""

import logging
import sys

import structlog


def setup_logging(debug: bool = False) -> None:
    """
    Configure structlog and stdlib logging.

    In debug mode: colored, human-readable console output.
    In production mode: JSON output for log aggregation.

    Args:
        debug: If True, use ConsoleRenderer; otherwise use JSONRenderer.
    """

    # Configuring what will show up in the logging
    shared_processors: list = [
        structlog.contextvars.merge_contextvars, # request_id, property_url (from middleware)
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging through structlog so existing logging.getLogger()
    # calls also produce structured output.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if debug else logging.INFO,
    )
