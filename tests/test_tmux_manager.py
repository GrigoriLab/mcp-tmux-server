"""Tests for TmuxManager class."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
import subprocess

from mcp_tmux.tmux_manager import (
    TmuxManager,
    TmuxNotInstalledError,
    SessionNotFoundError,
    PaneNotFoundError,
    SessionInfo,
    PaneInfo,
)


@pytest.fixture
def mock_tmux_installed():
    """Mock shutil.which to return tmux path."""
    with patch("shutil.which", return_value="/usr/bin/tmux"):
        yield


@pytest.fixture
def mock_tmux_not_installed():
    """Mock shutil.which to return None (tmux not found)."""
    with patch("shutil.which", return_value=None):
        yield


@pytest.fixture
def manager(mock_tmux_installed):
    """Create a TmuxManager with mocked tmux check."""
    return TmuxManager()


class TestTmuxManagerInit:
    """Tests for TmuxManager initialization."""

    def test_init_with_tmux_installed(self, mock_tmux_installed):
        """Should initialize successfully when tmux is installed."""
        manager = TmuxManager()
        assert manager is not None
        assert manager._sessions == {}

    def test_init_without_tmux_raises(self, mock_tmux_not_installed):
        """Should raise TmuxNotInstalledError when tmux is not installed."""
        with pytest.raises(TmuxNotInstalledError) as exc_info:
            TmuxManager()
        assert "tmux is not installed" in str(exc_info.value)


class TestGetSessionName:
    """Tests for _get_session_name method."""

    def test_simple_project_name(self, manager):
        """Simple project name should be prefixed with claude-."""
        assert manager._get_session_name("myproject") == "claude-myproject"

    def test_sanitizes_special_chars(self, manager):
        """Special characters should be sanitized."""
        assert manager._get_session_name("my.project") == "claude-my-project"

    def test_lowercases_name(self, manager):
        """Project name should be lowercased."""
        assert manager._get_session_name("MyProject") == "claude-myproject"


class TestSessionExists:
    """Tests for session_exists method."""

    def test_session_exists_returns_true(self, manager):
        """Should return True when session exists."""
        with patch.object(manager, "_run_tmux") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert manager.session_exists("claude-test") is True
            mock_run.assert_called_once_with(
                ["has-session", "-t", "claude-test"],
                check=False
            )

    def test_session_not_exists_returns_false(self, manager):
        """Should return False when session doesn't exist."""
        with patch.object(manager, "_run_tmux") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert manager.session_exists("claude-nonexistent") is False


class TestEnsureSessionExists:
    """Tests for _ensure_session_exists method."""

    def test_creates_new_session_when_not_exists(self, manager):
        """Should create a new session if it doesn't exist."""
        with patch.object(manager, "session_exists", return_value=False):
            with patch.object(manager, "_run_tmux") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")

                result = manager._ensure_session_exists("testproject", "/path/to/project")

                assert result == "claude-testproject"
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "new-session" in call_args
                assert "-d" in call_args
                assert "-s" in call_args
                assert "claude-testproject" in call_args
                assert "-c" in call_args
                assert "/path/to/project" in call_args

    def test_reuses_existing_session(self, manager):
        """Should return existing session name without creating."""
        with patch.object(manager, "session_exists", return_value=True):
            with patch.object(manager, "_run_tmux") as mock_run:
                # Pre-populate the sessions dict
                manager._sessions["claude-testproject"] = SessionInfo(
                    name="claude-testproject",
                    project="testproject",
                    created_at=datetime.now(),
                    working_directory="/path"
                )

                result = manager._ensure_session_exists("testproject")

                assert result == "claude-testproject"
                mock_run.assert_not_called()


class TestRunInPane:
    """Tests for run_in_pane method."""

    def test_first_pane_uses_existing_window(self, manager):
        """First task should use the existing pane created with session."""
        with patch.object(manager, "_ensure_session_exists", return_value="claude-myapp"):
            with patch.object(manager, "_get_pane_count", return_value=1):
                with patch.object(manager, "_get_first_pane_id", return_value="%0"):
                    with patch.object(manager, "_run_tmux") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0)

                        # Set up the session in the manager
                        manager._sessions["claude-myapp"] = SessionInfo(
                            name="claude-myapp",
                            project="myapp",
                            created_at=datetime.now(),
                            working_directory="/path",
                            panes={}
                        )

                        session_name, pane_id, pane_info = manager.run_in_pane(
                            command="npm run dev",
                            project="myapp",
                            task_name="frontend"
                        )

                        assert session_name == "claude-myapp"
                        assert pane_id == "%0"
                        assert pane_info.task_name == "frontend"
                        assert pane_info.command == "npm run dev"

    def test_subsequent_pane_splits_window(self, manager):
        """Subsequent tasks should create new panes via split."""
        with patch.object(manager, "_ensure_session_exists", return_value="claude-myapp"):
            with patch.object(manager, "_get_pane_count", return_value=2):
                with patch.object(manager, "_run_tmux") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="%1\n")

                    manager._sessions["claude-myapp"] = SessionInfo(
                        name="claude-myapp",
                        project="myapp",
                        created_at=datetime.now(),
                        working_directory="/path",
                        panes={"existing": PaneInfo("%0", "existing", "cmd", datetime.now())}
                    )

                    session_name, pane_id, pane_info = manager.run_in_pane(
                        command="python manage.py runserver",
                        project="myapp",
                        task_name="backend"
                    )

                    # Verify split-window was called
                    calls = [str(c) for c in mock_run.call_args_list]
                    assert any("split-window" in c for c in calls)


class TestCaptureOutput:
    """Tests for capture_output method."""

    def test_capture_output_basic(self, manager):
        """Should capture output from a pane."""
        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                mock_run.return_value = MagicMock(stdout="test output\nline 2\n")

                result = manager.capture_output("claude-test")

                assert result == "test output\nline 2\n"
                mock_run.assert_called_once()
                call_args = mock_run.call_args[0][0]
                assert "capture-pane" in call_args

    def test_capture_output_with_history(self, manager):
        """Should include history flag when requested."""
        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                mock_run.return_value = MagicMock(stdout="output")

                manager.capture_output("claude-test", lines=500, include_history=True)

                call_args = mock_run.call_args[0][0]
                assert "-S" in call_args
                assert "-500" in call_args

    def test_capture_output_specific_task(self, manager):
        """Should capture from specific task pane."""
        manager._sessions["claude-test"] = SessionInfo(
            name="claude-test",
            project="test",
            created_at=datetime.now(),
            working_directory="/path",
            panes={"frontend": PaneInfo("%5", "frontend", "npm run dev", datetime.now())}
        )

        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                mock_run.return_value = MagicMock(stdout="output")

                manager.capture_output("claude-test", task_name="frontend")

                call_args = mock_run.call_args[0][0]
                assert "%5" in call_args


class TestSendInput:
    """Tests for send_input method."""

    def test_send_input_with_enter(self, manager):
        """Should send text with Enter key."""
        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                manager.send_input("claude-test", "ls -la")

                call_args = mock_run.call_args[0][0]
                assert "send-keys" in call_args
                assert "ls -la" in call_args
                assert "Enter" in call_args

    def test_send_input_without_enter(self, manager):
        """Should send text without Enter key when specified."""
        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                manager.send_input("claude-test", "partial", press_enter=False)

                call_args = mock_run.call_args[0][0]
                assert "send-keys" in call_args
                assert "partial" in call_args
                assert "Enter" not in call_args


class TestSendKeys:
    """Tests for send_keys method."""

    def test_send_special_keys(self, manager):
        """Should send special key sequences."""
        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                manager.send_keys("claude-test", "C-c")

                call_args = mock_run.call_args[0][0]
                assert "send-keys" in call_args
                assert "C-c" in call_args


class TestListSessions:
    """Tests for list_sessions method."""

    def test_list_sessions_empty(self, manager):
        """Should return empty list when no sessions exist."""
        with patch.object(manager, "_run_tmux") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = manager.list_sessions()

            assert result == []

    def test_list_sessions_filters_claude_prefix(self, manager):
        """Should only return claude-prefixed sessions."""
        with patch.object(manager, "_run_tmux") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="claude-myapp\nother-session\nclaude-test\n"
            )
            with patch.object(manager, "_refresh_panes"):
                result = manager.list_sessions()

                assert len(result) == 2
                names = [s.name for s in result]
                assert "claude-myapp" in names
                assert "claude-test" in names
                assert "other-session" not in names


class TestKillSession:
    """Tests for kill_session method."""

    def test_kill_session_success(self, manager):
        """Should kill session and remove from tracking."""
        manager._sessions["claude-test"] = SessionInfo(
            name="claude-test",
            project="test",
            created_at=datetime.now(),
            working_directory="/path"
        )

        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                manager.kill_session("claude-test")

                call_args = mock_run.call_args[0][0]
                assert "kill-session" in call_args
                assert "claude-test" in call_args
                assert "claude-test" not in manager._sessions

    def test_kill_nonexistent_session_raises(self, manager):
        """Should raise SessionNotFoundError for nonexistent session."""
        with patch.object(manager, "session_exists", return_value=False):
            with pytest.raises(SessionNotFoundError):
                manager.kill_session("claude-nonexistent")


class TestKillPane:
    """Tests for kill_pane method."""

    def test_kill_pane_success(self, manager):
        """Should kill specific pane."""
        manager._sessions["claude-test"] = SessionInfo(
            name="claude-test",
            project="test",
            created_at=datetime.now(),
            working_directory="/path",
            panes={"frontend": PaneInfo("%1", "frontend", "npm run dev", datetime.now())}
        )

        with patch.object(manager, "_verify_session_exists"):
            with patch.object(manager, "_run_tmux") as mock_run:
                with patch.object(manager, "_get_pane_count", return_value=1):
                    manager.kill_pane("claude-test", "frontend")

                    # Verify kill-pane was called
                    calls = [str(c) for c in mock_run.call_args_list]
                    assert any("kill-pane" in c for c in calls)
                    assert "frontend" not in manager._sessions["claude-test"].panes

    def test_kill_nonexistent_pane_raises(self, manager):
        """Should raise PaneNotFoundError for nonexistent pane."""
        manager._sessions["claude-test"] = SessionInfo(
            name="claude-test",
            project="test",
            created_at=datetime.now(),
            working_directory="/path",
            panes={}
        )

        with patch.object(manager, "_verify_session_exists"):
            with pytest.raises(PaneNotFoundError):
                manager.kill_pane("claude-test", "nonexistent")


class TestVerifySessionExists:
    """Tests for _verify_session_exists method."""

    def test_raises_when_session_not_found(self, manager):
        """Should raise SessionNotFoundError when session doesn't exist."""
        with patch.object(manager, "session_exists", return_value=False):
            with pytest.raises(SessionNotFoundError) as exc_info:
                manager._verify_session_exists("claude-nonexistent")
            assert "claude-nonexistent" in str(exc_info.value)

    def test_passes_when_session_exists(self, manager):
        """Should not raise when session exists."""
        with patch.object(manager, "session_exists", return_value=True):
            manager._verify_session_exists("claude-test")  # Should not raise
