"""Tests for MCP server tools."""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from datetime import datetime

from mcp_tmux.server import (
    _get_project_name,
    run_in_terminal,
    get_terminal_output,
    send_input,
    list_sessions,
    kill_session,
    kill_task,
)
from mcp_tmux.tmux_manager import (
    TmuxManager,
    TmuxNotInstalledError,
    SessionNotFoundError,
    PaneNotFoundError,
    SessionInfo,
    PaneInfo,
)


class TestGetProjectName:
    """Tests for _get_project_name function."""

    def test_returns_default_for_none(self):
        """Should return 'default' when working_directory is None."""
        assert _get_project_name(None) == "default"

    def test_returns_default_for_empty_string(self):
        """Should return 'default' when working_directory is empty."""
        assert _get_project_name("") == "default"

    def test_finds_git_root(self):
        """Should find project name from git root directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a project structure: tmpdir/myproject/.git
            project_dir = os.path.join(tmpdir, "myproject")
            git_dir = os.path.join(project_dir, ".git")
            subdir = os.path.join(project_dir, "src", "backend")

            os.makedirs(git_dir)
            os.makedirs(subdir)

            # From subdir, should find myproject as project name
            result = _get_project_name(subdir)
            assert result == "myproject"

    def test_returns_last_component_without_git(self):
        """Should return last path component when no .git found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create directory without .git
            subdir = os.path.join(tmpdir, "somedir", "myapp")
            os.makedirs(subdir)

            result = _get_project_name(subdir)
            assert result == "myapp"

    def test_handles_nested_git_repos(self):
        """Should find nearest git root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested git repos
            outer = os.path.join(tmpdir, "outer")
            inner = os.path.join(outer, "inner")

            os.makedirs(os.path.join(outer, ".git"))
            os.makedirs(os.path.join(inner, ".git"))
            os.makedirs(os.path.join(inner, "src"))

            # From inner/src, should find "inner" as the project
            result = _get_project_name(os.path.join(inner, "src"))
            assert result == "inner"


class TestRunInTerminal:
    """Tests for run_in_terminal tool."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock TmuxManager."""
        manager = MagicMock(spec=TmuxManager)
        manager.run_in_pane.return_value = (
            "claude-myapp",
            "%0",
            PaneInfo("%0", "test", "echo hello", datetime.now())
        )
        return manager

    def test_successful_run(self, mock_manager):
        """Should successfully start a command."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            with patch("mcp_tmux.server._get_project_name", return_value="myapp"):
                result = run_in_terminal(
                    command="echo hello",
                    task_name="test",
                    working_directory="/path/to/myapp"
                )

                assert result["success"] is True
                assert result["session_name"] == "claude-myapp"
                assert result["command"] == "echo hello"
                assert "attach_command" in result

    def test_uses_explicit_project_name(self, mock_manager):
        """Should use explicit project parameter over auto-detection."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = run_in_terminal(
                command="npm run dev",
                project="myapp",
                working_directory="/path/to/myapp/frontend"
            )

            # Verify run_in_pane was called with explicit project
            call_kwargs = mock_manager.run_in_pane.call_args[1]
            assert call_kwargs["project"] == "myapp"

    def test_extracts_task_from_command(self, mock_manager):
        """Should extract task name from command when not provided."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            with patch("mcp_tmux.server._get_project_name", return_value="myapp"):
                run_in_terminal(command="npm run dev")

                call_kwargs = mock_manager.run_in_pane.call_args[1]
                assert call_kwargs["task_name"] == "npm"

    def test_handles_tmux_not_installed(self):
        """Should return error when tmux is not installed."""
        with patch("mcp_tmux.server.get_tmux_manager") as mock_get:
            mock_get.side_effect = TmuxNotInstalledError("tmux not found")

            result = run_in_terminal(command="echo hello")

            assert result["success"] is False
            assert result["error_type"] == "tmux_not_installed"

    def test_handles_general_error(self, mock_manager):
        """Should handle unexpected errors gracefully."""
        mock_manager.run_in_pane.side_effect = Exception("Unexpected error")

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            with patch("mcp_tmux.server._get_project_name", return_value="test"):
                result = run_in_terminal(command="echo hello")

                assert result["success"] is False
                assert result["error_type"] == "unknown"


class TestGetTerminalOutput:
    """Tests for get_terminal_output tool."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock TmuxManager."""
        manager = MagicMock(spec=TmuxManager)
        manager._get_session_name.return_value = "claude-myapp"
        manager.capture_output.return_value = "line 1\nline 2\nline 3\n"
        return manager

    def test_successful_capture(self, mock_manager):
        """Should successfully capture output."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = get_terminal_output(project="myapp")

            assert result["success"] is True
            assert result["project"] == "myapp"
            assert "line 1" in result["output"]
            assert result["lines_captured"] == 3

    def test_capture_specific_task(self, mock_manager):
        """Should capture from specific task."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = get_terminal_output(project="myapp", task_name="frontend")

            assert result["task_name"] == "frontend"
            mock_manager.capture_output.assert_called_once()

    def test_clamps_lines_to_max(self, mock_manager):
        """Should clamp lines to maximum value."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            get_terminal_output(project="myapp", lines=50000)

            call_kwargs = mock_manager.capture_output.call_args[1]
            assert call_kwargs["lines"] == 10000

    def test_clamps_lines_to_min(self, mock_manager):
        """Should clamp lines to minimum value."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            get_terminal_output(project="myapp", lines=-10)

            call_kwargs = mock_manager.capture_output.call_args[1]
            assert call_kwargs["lines"] == 1

    def test_handles_session_not_found(self, mock_manager):
        """Should return error when session doesn't exist."""
        mock_manager.capture_output.side_effect = SessionNotFoundError("Not found")

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = get_terminal_output(project="nonexistent")

            assert result["success"] is False
            assert result["error_type"] == "session_not_found"


class TestSendInput:
    """Tests for send_input tool."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock TmuxManager."""
        manager = MagicMock(spec=TmuxManager)
        manager._get_session_name.return_value = "claude-myapp"
        return manager

    def test_send_text_input(self, mock_manager):
        """Should send text input."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = send_input(project="myapp", text="ls -la")

            assert result["success"] is True
            assert result["sent"] == "ls -la"
            assert result["pressed_enter"] is True
            mock_manager.send_input.assert_called_once()

    def test_send_special_key(self, mock_manager):
        """Should send special keys."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = send_input(project="myapp", text="C-c")

            assert result["success"] is True
            assert result["type"] == "special_key"
            mock_manager.send_keys.assert_called_once()

    def test_send_without_enter(self, mock_manager):
        """Should send without Enter key when specified."""
        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = send_input(project="myapp", text="partial", press_enter=False)

            assert result["pressed_enter"] is False

    def test_handles_session_not_found(self, mock_manager):
        """Should return error when session doesn't exist."""
        mock_manager.send_input.side_effect = SessionNotFoundError("Not found")

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = send_input(project="nonexistent", text="hello")

            assert result["success"] is False
            assert result["error_type"] == "session_not_found"


class TestListSessions:
    """Tests for list_sessions tool."""

    def test_list_sessions_success(self):
        """Should list all sessions."""
        mock_manager = MagicMock(spec=TmuxManager)
        mock_manager.list_sessions.return_value = [
            SessionInfo(
                name="claude-app1",
                project="app1",
                created_at=datetime.now(),
                working_directory="/path/app1",
                panes={"web": PaneInfo("%0", "web", "npm start", datetime.now())}
            ),
            SessionInfo(
                name="claude-app2",
                project="app2",
                created_at=datetime.now(),
                working_directory="/path/app2",
                panes={}
            )
        ]

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = list_sessions()

            assert result["success"] is True
            assert result["count"] == 2
            assert len(result["sessions"]) == 2

    def test_list_sessions_empty(self):
        """Should handle empty session list."""
        mock_manager = MagicMock(spec=TmuxManager)
        mock_manager.list_sessions.return_value = []

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = list_sessions()

            assert result["success"] is True
            assert result["count"] == 0
            assert result["sessions"] == []


class TestKillSession:
    """Tests for kill_session tool."""

    def test_kill_session_success(self):
        """Should kill session successfully."""
        mock_manager = MagicMock(spec=TmuxManager)
        mock_manager._get_session_name.return_value = "claude-myapp"

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = kill_session(project="myapp")

            assert result["success"] is True
            assert result["project"] == "myapp"
            mock_manager.kill_session.assert_called_once_with("claude-myapp")

    def test_kill_session_not_found(self):
        """Should return error when session doesn't exist."""
        mock_manager = MagicMock(spec=TmuxManager)
        mock_manager._get_session_name.return_value = "claude-nonexistent"
        mock_manager.kill_session.side_effect = SessionNotFoundError("Not found")

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = kill_session(project="nonexistent")

            assert result["success"] is False
            assert result["error_type"] == "session_not_found"


class TestKillTask:
    """Tests for kill_task tool."""

    def test_kill_task_success(self):
        """Should kill specific task."""
        mock_manager = MagicMock(spec=TmuxManager)
        mock_manager._get_session_name.return_value = "claude-myapp"

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = kill_task(project="myapp", task_name="frontend")

            assert result["success"] is True
            assert result["project"] == "myapp"
            assert result["task_name"] == "frontend"
            mock_manager.kill_pane.assert_called_once()

    def test_kill_task_not_found(self):
        """Should return error when task doesn't exist."""
        mock_manager = MagicMock(spec=TmuxManager)
        mock_manager._get_session_name.return_value = "claude-myapp"
        mock_manager.kill_pane.side_effect = PaneNotFoundError("Not found")

        with patch("mcp_tmux.server.get_tmux_manager", return_value=mock_manager):
            result = kill_task(project="myapp", task_name="nonexistent")

            assert result["success"] is False
            assert result["error_type"] == "pane_not_found"
