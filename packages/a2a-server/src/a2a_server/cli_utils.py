"""ANSI color helpers for CLI output."""

from __future__ import annotations

import os
import sys

# Detect NO_COLOR convention and dumb terminals
_NO_COLOR = bool(os.environ.get("NO_COLOR")) or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty()

_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _wrap(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"{code}{text}{_RESET}"


def success(text: str) -> str:
    """Green text for success messages."""
    return _wrap(_GREEN, f"\u2713 {text}")


def error(text: str) -> str:
    """Red text for error messages."""
    return _wrap(_RED, f"\u2717 {text}")


def warning(text: str) -> str:
    """Yellow text for warning messages."""
    return _wrap(_YELLOW, f"! {text}")


def info(text: str) -> str:
    """Cyan text for informational messages."""
    return _wrap(_CYAN, text)


def header(text: str) -> str:
    """Bold text for section headers."""
    return _wrap(_BOLD, text)


def suggestion(text: str) -> str:
    """Dim text for suggestions and hints."""
    return _wrap(_DIM, f"  \u2192 {text}")
