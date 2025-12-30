"""tmux session management for the MCP server."""

import subprocess
import shutil
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class PaneInfo:
    """Information about a tmux pane (task)."""
    pane_id: str
    task_name: str
    command: str
    created_at: datetime


@dataclass
class SessionInfo:
    """Information about a tmux session (project)."""
    name: str
    project: str
    created_at: datetime
    working_directory: str
    panes: dict[str, PaneInfo] = field(default_factory=dict)


class TmuxNotInstalledError(Exception):
    """Raised when tmux is not available on the system."""
    pass


class SessionNotFoundError(Exception):
    """Raised when a session does not exist."""
    pass


class PaneNotFoundError(Exception):
    """Raised when a pane does not exist."""
    pass


class TmuxManager:
    """Manages tmux sessions for the MCP server.

    Architecture:
    - One session per project: claude-<project>
    - Multiple panes within session for different tasks
    """

    SESSION_PREFIX = "claude-"

    def __init__(self):
        self._verify_tmux_installed()
        self._sessions: dict[str, SessionInfo] = {}

    def _verify_tmux_installed(self) -> None:
        """Check if tmux is available on the system."""
        if shutil.which("tmux") is None:
            raise TmuxNotInstalledError(
                "tmux is not installed. Install it with: "
                "brew install tmux (macOS) or apt install tmux (Linux)"
            )

    def _run_tmux(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Execute a tmux command."""
        return subprocess.run(
            ["tmux"] + args,
            capture_output=True,
            text=True,
            check=check
        )

    def _get_session_name(self, project: str) -> str:
        """Get the tmux session name for a project."""
        from .utils import sanitize_session_name
        sanitized = sanitize_session_name(project)
        return f"{self.SESSION_PREFIX}{sanitized}"

    def _ensure_session_exists(
        self,
        project: str,
        working_directory: Optional[str] = None
    ) -> str:
        """Ensure a session exists for the project, create if needed."""
        session_name = self._get_session_name(project)

        if not self.session_exists(session_name):
            # Create new session
            args = [
                "new-session",
                "-d",  # Detached
                "-s", session_name,
                "-x", "200",
                "-y", "50",
            ]

            if working_directory:
                args.extend(["-c", working_directory])

            self._run_tmux(args)

            # Track the session
            self._sessions[session_name] = SessionInfo(
                name=session_name,
                project=project,
                created_at=datetime.now(),
                working_directory=working_directory or "",
                panes={}
            )

        return session_name

    def run_in_pane(
        self,
        command: str,
        project: str,
        task_name: str,
        working_directory: Optional[str] = None
    ) -> tuple[str, str, PaneInfo]:
        """Run a command in a new pane within the project's session.

        Returns: (session_name, pane_id, PaneInfo)
        """
        session_name = self._ensure_session_exists(project, working_directory)
        session = self._sessions.get(session_name)

        # Check if this is the first pane (session was just created with empty window)
        pane_count = self._get_pane_count(session_name)

        if pane_count == 1 and not session.panes:
            # First task - use the existing pane, just send the command
            pane_id = self._get_first_pane_id(session_name)
            self._run_tmux(["send-keys", "-t", f"{session_name}", command, "Enter"])
        else:
            # Create a new pane (split horizontally)
            result = self._run_tmux([
                "split-window",
                "-t", session_name,
                "-h",  # Horizontal split
                "-P",  # Print pane info
                "-F", "#{pane_id}",
            ] + (["-c", working_directory] if working_directory else []))

            pane_id = result.stdout.strip()

            # Send the command to the new pane
            self._run_tmux(["send-keys", "-t", pane_id, command, "Enter"])

            # Rebalance panes
            self._run_tmux(["select-layout", "-t", session_name, "tiled"], check=False)

        # Track the pane
        pane_info = PaneInfo(
            pane_id=pane_id,
            task_name=task_name,
            command=command,
            created_at=datetime.now()
        )

        if session:
            session.panes[task_name] = pane_info

        return session_name, pane_id, pane_info

    def _get_pane_count(self, session_name: str) -> int:
        """Get the number of panes in a session."""
        result = self._run_tmux([
            "list-panes", "-t", session_name, "-F", "#{pane_id}"
        ], check=False)
        if result.returncode != 0:
            return 0
        return len([p for p in result.stdout.strip().split("\n") if p])

    def _get_first_pane_id(self, session_name: str) -> str:
        """Get the ID of the first pane in a session."""
        result = self._run_tmux([
            "list-panes", "-t", session_name, "-F", "#{pane_id}"
        ])
        return result.stdout.strip().split("\n")[0]

    def capture_output(
        self,
        session_name: str,
        task_name: Optional[str] = None,
        lines: int = 100,
        include_history: bool = False
    ) -> str:
        """Capture output from a pane."""
        self._verify_session_exists(session_name)

        # Determine target (specific pane or session default)
        if task_name:
            session = self._sessions.get(session_name)
            if session and task_name in session.panes:
                target = session.panes[task_name].pane_id
            else:
                target = session_name
        else:
            target = session_name

        args = ["capture-pane", "-t", target, "-p"]

        if include_history:
            args.extend(["-S", f"-{lines}"])

        result = self._run_tmux(args, check=False)
        return result.stdout

    def send_input(
        self,
        session_name: str,
        text: str,
        task_name: Optional[str] = None,
        press_enter: bool = True
    ) -> None:
        """Send input to a pane."""
        self._verify_session_exists(session_name)

        # Determine target
        if task_name:
            session = self._sessions.get(session_name)
            if session and task_name in session.panes:
                target = session.panes[task_name].pane_id
            else:
                target = session_name
        else:
            target = session_name

        args = ["send-keys", "-t", target, text]

        if press_enter:
            args.append("Enter")

        self._run_tmux(args)

    def send_keys(self, session_name: str, keys: str, task_name: Optional[str] = None) -> None:
        """Send special keys (C-c, C-d, etc.) to a pane."""
        self._verify_session_exists(session_name)

        if task_name:
            session = self._sessions.get(session_name)
            if session and task_name in session.panes:
                target = session.panes[task_name].pane_id
            else:
                target = session_name
        else:
            target = session_name

        self._run_tmux(["send-keys", "-t", target, keys])

    def list_sessions(self) -> list[SessionInfo]:
        """List all claude-prefixed tmux sessions with their panes."""
        result = self._run_tmux(
            ["list-sessions", "-F", "#{session_name}"],
            check=False
        )

        if result.returncode != 0:
            return []

        sessions = []
        for name in result.stdout.strip().split("\n"):
            if name and name.startswith(self.SESSION_PREFIX):
                if name in self._sessions:
                    # Update pane info from tmux
                    self._refresh_panes(name)
                    sessions.append(self._sessions[name])
                else:
                    # Session exists but not tracked
                    session = SessionInfo(
                        name=name,
                        project=name.replace(self.SESSION_PREFIX, ""),
                        created_at=datetime.now(),
                        working_directory="",
                        panes={}
                    )
                    self._sessions[name] = session
                    self._refresh_panes(name)
                    sessions.append(session)

        return sessions

    def _refresh_panes(self, session_name: str) -> None:
        """Refresh pane information from tmux."""
        result = self._run_tmux([
            "list-panes", "-t", session_name,
            "-F", "#{pane_id}|#{pane_current_command}"
        ], check=False)

        if result.returncode != 0:
            return

        session = self._sessions.get(session_name)
        if not session:
            return

        # Get current pane IDs from tmux
        current_panes = {}
        for line in result.stdout.strip().split("\n"):
            if "|" in line:
                pane_id, cmd = line.split("|", 1)
                current_panes[pane_id] = cmd

        # Update tracked panes - remove any that no longer exist
        for task_name in list(session.panes.keys()):
            if session.panes[task_name].pane_id not in current_panes:
                del session.panes[task_name]

    def kill_pane(self, session_name: str, task_name: str) -> None:
        """Kill a specific pane (task) in a session."""
        self._verify_session_exists(session_name)

        session = self._sessions.get(session_name)
        if not session or task_name not in session.panes:
            raise PaneNotFoundError(f"Task '{task_name}' not found in session '{session_name}'")

        pane_id = session.panes[task_name].pane_id
        self._run_tmux(["kill-pane", "-t", pane_id], check=False)
        del session.panes[task_name]

        # If no panes left, kill the session
        if self._get_pane_count(session_name) == 0:
            self.kill_session(session_name)

    def kill_session(self, session_name: str) -> None:
        """Terminate an entire tmux session."""
        self._verify_session_exists(session_name)
        self._run_tmux(["kill-session", "-t", session_name])

        if session_name in self._sessions:
            del self._sessions[session_name]

    def session_exists(self, session_name: str) -> bool:
        """Check if a session exists."""
        result = self._run_tmux(
            ["has-session", "-t", session_name],
            check=False
        )
        return result.returncode == 0

    def _verify_session_exists(self, session_name: str) -> None:
        """Raise an error if the session does not exist."""
        if not self.session_exists(session_name):
            raise SessionNotFoundError(f"Session '{session_name}' not found")
