"""
Logging configuration for Journal Club app.
Provides structured logging with timestamps, levels, and contextual info.
"""
import logging
import sys
from pathlib import Path


def configure_logging(log_level=logging.INFO, log_file=None):
    """
    Configure logging for the application.

    Args:
        log_level: logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: optional path to log file; if set, logs to both file and console

    Example:
        configure_logging(logging.DEBUG)  # console only, debug level
        configure_logging(logging.INFO, "journal_club.log")  # file + console, info level
    """
    root = logging.getLogger()
    root.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    root.addHandler(console_handler)

    # File handler (if log_file specified)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)
        print(f"Logging to {log_path}")

    return root


def get_logger(name):
    """Get a logger for a module."""
    return logging.getLogger(name)
