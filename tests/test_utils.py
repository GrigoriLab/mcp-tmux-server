"""Tests for utility functions."""

import pytest
from datetime import datetime
from mcp_tmux.utils import sanitize_session_name, format_timestamp, parse_session_name


class TestSanitizeSessionName:
    """Tests for sanitize_session_name function."""

    def test_simple_name(self):
        """Simple name should be lowercased."""
        assert sanitize_session_name("MyProject") == "myproject"

    def test_replaces_periods(self):
        """Periods should be replaced with hyphens."""
        assert sanitize_session_name("my.project") == "my-project"

    def test_replaces_colons(self):
        """Colons should be replaced with hyphens."""
        assert sanitize_session_name("my:project") == "my-project"

    def test_replaces_spaces(self):
        """Spaces should be replaced with hyphens."""
        assert sanitize_session_name("my project") == "my-project"

    def test_replaces_slashes(self):
        """Forward and back slashes should be replaced with hyphens."""
        assert sanitize_session_name("my/project") == "my-project"
        assert sanitize_session_name("my\\project") == "my-project"

    def test_removes_consecutive_hyphens(self):
        """Multiple consecutive hyphens should be collapsed."""
        assert sanitize_session_name("my..project") == "my-project"
        assert sanitize_session_name("my...project") == "my-project"
        assert sanitize_session_name("my  project") == "my-project"

    def test_removes_leading_trailing_hyphens(self):
        """Leading and trailing hyphens should be removed."""
        assert sanitize_session_name(".myproject") == "myproject"
        assert sanitize_session_name("myproject.") == "myproject"
        assert sanitize_session_name("..myproject..") == "myproject"

    def test_truncates_to_max_length(self):
        """Name should be truncated to max_length."""
        long_name = "a" * 30
        assert len(sanitize_session_name(long_name)) == 20
        assert sanitize_session_name(long_name, max_length=10) == "a" * 10

    def test_custom_max_length(self):
        """Custom max_length should be respected."""
        assert sanitize_session_name("myproject", max_length=5) == "mypro"

    def test_empty_string(self):
        """Empty string should return empty string."""
        assert sanitize_session_name("") == ""

    def test_only_special_chars(self):
        """String with only special chars should return empty."""
        assert sanitize_session_name("...") == ""
        assert sanitize_session_name(":::") == ""

    def test_complex_path(self):
        """Complex path-like strings should be handled."""
        assert sanitize_session_name("/path/to/my.project") == "path-to-my-project"


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_returns_string(self):
        """Should return a string."""
        result = format_timestamp()
        assert isinstance(result, str)

    def test_format_is_hhmmss(self):
        """Should return 6-digit HHMMSS format."""
        result = format_timestamp()
        assert len(result) == 6
        assert result.isdigit()

    def test_valid_time_range(self):
        """Hours, minutes, seconds should be in valid ranges."""
        result = format_timestamp()
        hours = int(result[:2])
        minutes = int(result[2:4])
        seconds = int(result[4:6])
        assert 0 <= hours <= 23
        assert 0 <= minutes <= 59
        assert 0 <= seconds <= 59


class TestParseSessionName:
    """Tests for parse_session_name function."""

    def test_valid_session_name(self):
        """Valid claude session name should be parsed correctly."""
        result = parse_session_name("claude-npm-dev-123456")
        assert result["prefix"] == "claude"
        assert result["task"] == "npm-dev"
        assert result["timestamp"] == "123456"

    def test_simple_task_name(self):
        """Simple task without hyphens should work."""
        result = parse_session_name("claude-myapp-123456")
        assert result["prefix"] == "claude"
        assert result["task"] == "myapp"
        assert result["timestamp"] == "123456"

    def test_complex_task_name(self):
        """Task with multiple hyphens should preserve them."""
        result = parse_session_name("claude-my-complex-task-name-123456")
        assert result["prefix"] == "claude"
        assert result["task"] == "my-complex-task-name"
        assert result["timestamp"] == "123456"

    def test_non_claude_prefix(self):
        """Non-claude prefixed name should return raw."""
        result = parse_session_name("other-session-123456")
        assert "raw" in result
        assert result["raw"] == "other-session-123456"

    def test_too_few_parts(self):
        """Name with too few parts should return raw."""
        result = parse_session_name("claude-only")
        assert "raw" in result
        assert result["raw"] == "claude-only"

    def test_single_part(self):
        """Single part name should return raw."""
        result = parse_session_name("noseparators")
        assert "raw" in result
        assert result["raw"] == "noseparators"

    def test_empty_string(self):
        """Empty string should return raw."""
        result = parse_session_name("")
        assert "raw" in result
        assert result["raw"] == ""
