"""
utils.py — Shared utilities for GitHub Activity Automation System.

Provides:
- Configuration loading
- Structured logging setup
- Kill switch checking
- State persistence helpers
"""

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# ── Project root (the directory containing this file) ──────────────────────
ROOT_DIR = Path(__file__).parent
CONFIG_PATH = ROOT_DIR / "config.json"


# ── Configuration ───────────────────────────────────────────────────────────

def load_config(config_path: Path = CONFIG_PATH) -> dict:
    """Load and return the JSON configuration file."""
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found at {config_path}. "
            "Copy config.json to the project root and try again."
        )
    with config_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def get_config_value(config: dict, *keys: str, default: Any = None) -> Any:
    """Safely retrieve a nested config value using dot-path keys."""
    node = config
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node


# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logger(name: str, config: dict) -> logging.Logger:
    """
    Create a logger that writes structured entries to both stdout and a
    rotating log file.  All entries include timestamp and severity.
    """
    log_cfg = config.get("logging", {})
    log_file = ROOT_DIR / log_cfg.get("log_file", "logs/automation.log")
    log_level_str = log_cfg.get("log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    max_bytes = log_cfg.get("max_log_size_mb", 10) * 1024 * 1024
    backup_count = log_cfg.get("backup_count", 3)

    # Ensure log directory exists
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger  # Already configured (e.g. during tests)

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # Stdout handler
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger


# ── Kill switch ───────────────────────────────────────────────────────────────

def is_kill_switch_active(config: dict, logger: logging.Logger) -> bool:
    """
    Return True if the kill switch is enabled in config.
    When active, agents must exit without making any API calls.
    """
    if config.get("kill_switch", False):
        logger.warning("Kill switch is ACTIVE — agent will not run.")
        return True
    return False


# ── State persistence ─────────────────────────────────────────────────────────

def load_state(state_file: str) -> dict:
    """Load JSON state from disk; return an empty dict if missing or corrupt."""
    path = ROOT_DIR / state_file
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state_file: str, state: dict) -> None:
    """Persist state dict to disk as JSON (creates parent dirs if needed)."""
    path = ROOT_DIR / state_file
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2, default=str)


def today_str() -> str:
    """Return today's date as an ISO-8601 string (YYYY-MM-DD)."""
    return datetime.utcnow().strftime("%Y-%m-%d")


# ── GitHub token ──────────────────────────────────────────────────────────────

def get_github_token() -> str:
    """
    Read the GitHub Personal Access Token from the environment.
    Raises EnvironmentError with a helpful message if missing.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise EnvironmentError(
            "GITHUB_TOKEN is not set.  "
            "Create a .env file with GITHUB_TOKEN=<your_token> and run:\n"
            "  export $(cat .env | xargs)   # Linux/macOS\n"
            "  set /p GITHUB_TOKEN=<.env    # Windows CMD"
        )
    return token
