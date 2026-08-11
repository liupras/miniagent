#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-02-11
# @description: Logger configuration using loguru

"""
Log Configuration Module

Uses Loguru for log management, supporting:
- Console output (color-coded)
- File output (rotating by date/size)
- Separation of logs at different levels
- Structured logs
- Performance monitoring
"""

import logging
import sys
from loguru import logger
from app.core.config import settings


class InterceptHandler(logging.Handler):
    """Bridge stdlib logging to Loguru.

    Third-party libraries (uvicorn, sqlalchemy, chromadb, etc.) use Python's
    standard logging module. Without this handler their log records never reach
    Loguru's configured sinks and are either lost or printed with a different
    format. This handler forwards every stdlib log record to Loguru.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Map the stdlib level to a Loguru level name.
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk the call stack to find the actual caller so that Loguru
        # reports the correct module/function/line instead of this handler.
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logger():
    """
    Configure the logging system

    Log policies:
    1. Console: All levels (color output)
    2. Regular log files: INFO level and above (rotating by date)
    3. Error log files: ERROR level and above (rotating by size)
    4. Debug log files: DEBUG level (development environment only)
    """
    
    # Remove the default handler
    logger.remove()

    # Default extra fields so format strings referencing {extra[...]} never
    # raise KeyError outside a request context (e.g. during startup).
    logger.configure(extra={"request_id": "-"})

    # Get the log file path
    log_dir = settings.get_log_dir()

    # ==================== 1. console output ====================
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{extra[request_id]}</cyan> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        level=settings.log_level,
        colorize=True,
        backtrace=True,
        diagnose=settings.debug
    )

    # ==================== 2. Ordinary log file ====================
    # INFO and higher levels, rotating by date
    logger.add(
        log_dir / "miniagent_{time:YYYY-MM-DD}.log",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{extra[request_id]} | "
            "{name}:{function}:{line} | "
            "{message}"
        ),
        level="INFO",
        rotation="00:00",  # Rotating every midnight
        retention="30 days",  # Keep for 30 days
        compression="zip",  # Compress old logs
        encoding="utf-8",
        backtrace=True,
        diagnose=settings.debug
    )

    # ==================== 3. Error log file ====================
    # ERROR and above levels will be rotated according to their magnitude.
    logger.add(
        log_dir / "error.log",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{extra[request_id]} | "
            "{name}:{function}:{line} | "
            "{message}\n"
            "{exception}"
        ),
        level="ERROR",
        rotation="10 MB",  # Rotate when the file reaches 10MB
        retention=10,  # Keep the 10 most recent files
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=settings.debug
    )

    # ==================== 4. Debug log files (development environment only)====================
    if settings.debug:
        logger.add(
            log_dir / "debug.log",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{extra[request_id]} | "
                "{name}:{function}:{line} | "
                "{message}"
            ),
            level="DEBUG",
            rotation="100 MB",
            retention=3,
            compression="zip",
            encoding="utf-8",
            backtrace=True,
            diagnose=settings.debug
        )
    
    # ==================== Bridge stdlib logging to Loguru ====================
    # Redirect all standard-library logging (uvicorn, sqlalchemy, chromadb, etc.)
    # through Loguru so every log line shares the same sinks, format and rotation.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # Some libraries (e.g. uvicorn) install their own handlers on named child
    # loggers; override those so nothing bypasses the InterceptHandler.
    for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        _logger = logging.getLogger(_name)
        _logger.handlers = [InterceptHandler()]
        _logger.propagate = False

    # ==================== JSON structured logs (for log aggregation) ====================
    # Enabled when settings.json_log_enabled is True (set JSON_LOG_ENABLED=true in .env).
    # Outputs each log record as a JSON object, ideal for ELK / Loki / Grafana ingestion.
    if settings.json_log_enabled:
        logger.add(
            log_dir / "structured_{time:YYYY-MM-DD}.json",
            format="{message}",
            level="INFO",
            rotation="00:00",
            retention="30 days",
            compression="zip",
            serialize=True,  # Loguru serializes the full record (including extra fields) as JSON
            encoding="utf-8",
            backtrace=True,
            diagnose=settings.debug
        )
    
    # Record configuration complete
    logger.info("=" * 60)
    logger.info("📝 Log system configuration complete")
    logger.info(f"📂 Log directory: {log_dir}")
    logger.info(f"📊 Log levels: {settings.log_level}")
    logger.info(f"🐛 Debug mode: {settings.debug}")
    logger.info(f"📄 JSON structured log: {'enabled' if settings.json_log_enabled else 'disabled'}")
    logger.info("=" * 60)


def get_logger(name: str = None):
    """
    Get a logger instance
    
    Args:
        name: Logger name (usually using __name__)
    
    Returns:
        logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger


# ==================== Usage Example ====================
if __name__ == "__main__":
    # Explicitly configure logging when running this module directly.
    setup_logger()

    # Basic Log
    logger.debug("This is a DEBUG level log.")
    logger.info("This is a INFO level log.日志")
    logger.warning("This is a WARNING level log.")
    logger.error("This is a ERROR level log.")
    logger.critical("This is a CRITICAL level log.")
    
    # Context-sensitive logging
    logger.info("User Login", extra={"user_id": "admin", "ip": "192.168.1.1"})
    
    # Exception Log
    try:
        1 / 0
    except Exception as e:
        logger.exception("Exception caught during division operation")
    
    # Use a named logger
    module_logger = get_logger(__name__)
    module_logger.info("Logs from the module")
    
    # Structured logs
    logger.bind(
        user_id="user123",
        action="create_agent"
    ).info("User creates Agent", agent_name="test_agent")
    
    logger.success("✅ Log test complete!")
    logger.info(f"📂 Log file location: {settings.get_log_dir()}")
