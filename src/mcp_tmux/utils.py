"""Utility functions for the MCP tmux server."""

import re
from datetime import datetime


def sanitize_session_name(name: str, max_length: int = 20) -> str:
    """
    Sanitize a string for use as a tmux session name.

    tmux session names cannot contain periods or colons.
    """
    # Replace problematic characters
    sanitized = re.sub(r'[.:\s/\\]', '-', name)
    # Remove consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    # Lowercase and truncate
    return sanitized.lower()[:max_length]


def format_timestamp() -> str:
    """Generate a compact timestamp for session naming."""
    return datetime.now().strftime("%H%M%S")


def parse_session_name(full_name: str) -> dict:
    """
    Parse a claude session name into its components.

    Format: claude-{task}-{timestamp}
    """
    parts = full_name.split('-')
    if len(parts) >= 3 and parts[0] == "claude":
        return {
            "prefix": parts[0],
            "task": '-'.join(parts[1:-1]),
            "timestamp": parts[-1]
        }
    return {"raw": full_name}
