"""MCP server for interactive tmux terminal sessions."""

import os
import sys
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .tmux_manager import (
    TmuxManager,
    TmuxNotInstalledError,
    SessionNotFoundError,
    PaneNotFoundError,
)

# Configure logging to stderr (critical for stdio transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("tmux-terminal")

# Global tmux manager instance
_tmux_manager: Optional[TmuxManager] = None


def get_tmux_manager() -> TmuxManager:
    """Get or create the tmux manager singleton."""
    global _tmux_manager
    if _tmux_manager is None:
        _tmux_manager = TmuxManager()
    return _tmux_manager


def _get_project_name(working_directory: Optional[str]) -> str:
    """Extract project name from working directory by finding git root."""
    if not working_directory:
        return "default"

    # Walk up to find .git directory (project root)
    current = os.path.normpath(working_directory)
    while current != os.path.dirname(current):  # Stop at filesystem root
        if os.path.isdir(os.path.join(current, ".git")):
            return os.path.basename(current)
        current = os.path.dirname(current)

    # Fallback to last directory component if no git root found
    return os.path.basename(os.path.normpath(working_directory))


@mcp.tool()
def run_in_terminal(
    command: str,
    project: Optional[str] = None,
    task_name: Optional[str] = None,
    working_directory: Optional[str] = None
) -> dict:
    """
    Start a command in a new tmux session for background execution.

    Use this for long-running processes like dev servers, test suites,
    or any command the user might want to interact with.

    Args:
        command: The shell command to execute (e.g., "npm start", "pytest -v")
        project: Project name for grouping tasks (defaults to folder name from working_directory)
        task_name: Optional descriptive name for the task (used in session name)
        working_directory: Optional directory to run the command in

    Returns:
        Session information including the attach command for the user
    """
    try:
        manager = get_tmux_manager()

        # Use explicit project name, or extract from working_directory
        project_name = project or _get_project_name(working_directory)
        task = task_name or command.split()[0] if command else "task"

        session_name, pane_id, pane_info = manager.run_in_pane(
            command=command,
            project=project_name,
            task_name=task,
            working_directory=working_directory
        )

        return {
            "success": True,
            "session_name": session_name,
            "project": project_name,
            "task_name": task,
            "pane_id": pane_id,
            "command": command,
            "attach_command": f"tmux attach -t {session_name}",
            "message": (
                f"Task '{task}' started in project session '{session_name}'. "
                f"Attach with: tmux attach -t {session_name}"
            )
        }

    except TmuxNotInstalledError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "tmux_not_installed"
        }
    except Exception as e:
        logger.exception("Failed to create terminal session")
        return {
            "success": False,
            "error": str(e),
            "error_type": "unknown"
        }


@mcp.tool()
def get_terminal_output(
    project: str,
    task_name: Optional[str] = None,
    lines: int = 100,
    include_history: bool = False
) -> dict:
    """
    Capture output from a project's tmux session.

    Use this to check on the status of a background task or see recent output.

    Args:
        project: Name of the project (folder name)
        task_name: Optional task name to capture from specific pane
        lines: Number of lines to capture (default 100, max 10000)
        include_history: If True, include scrollback history

    Returns:
        The captured terminal output
    """
    try:
        manager = get_tmux_manager()
        session_name = manager._get_session_name(project)

        # Clamp lines to reasonable bounds
        lines = max(1, min(lines, 10000))

        output = manager.capture_output(
            session_name=session_name,
            task_name=task_name,
            lines=lines,
            include_history=include_history
        )

        return {
            "success": True,
            "project": project,
            "task_name": task_name,
            "output": output,
            "lines_captured": len(output.splitlines())
        }

    except SessionNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "session_not_found"
        }
    except TmuxNotInstalledError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "tmux_not_installed"
        }
    except Exception as e:
        logger.exception("Failed to capture terminal output")
        return {
            "success": False,
            "error": str(e),
            "error_type": "unknown"
        }


@mcp.tool()
def send_input(
    project: str,
    text: str,
    task_name: Optional[str] = None,
    press_enter: bool = True
) -> dict:
    """
    Send input to a project's tmux session.

    Use this to type commands or respond to prompts in a running session.
    For special keys like Ctrl+C, use special key names.

    Args:
        project: Name of the project (folder name)
        text: Text to send, or special key like "C-c" for Ctrl+C, "C-d" for Ctrl+D
        task_name: Optional task name to send to specific pane
        press_enter: Whether to press Enter after the text (default True)

    Returns:
        Confirmation of input sent
    """
    try:
        manager = get_tmux_manager()
        session_name = manager._get_session_name(project)

        # Check for special key sequences
        special_keys = {
            "C-c": "C-c",      # Ctrl+C (interrupt)
            "C-d": "C-d",      # Ctrl+D (EOF)
            "C-z": "C-z",      # Ctrl+Z (suspend)
            "C-l": "C-l",      # Ctrl+L (clear)
            "Escape": "Escape",
        }

        if text in special_keys:
            manager.send_keys(session_name, special_keys[text], task_name)
            return {
                "success": True,
                "project": project,
                "task_name": task_name,
                "sent": text,
                "type": "special_key"
            }
        else:
            manager.send_input(session_name, text, task_name, press_enter)
            return {
                "success": True,
                "project": project,
                "task_name": task_name,
                "sent": text,
                "pressed_enter": press_enter
            }

    except SessionNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "session_not_found"
        }
    except TmuxNotInstalledError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "tmux_not_installed"
        }
    except Exception as e:
        logger.exception("Failed to send input to session")
        return {
            "success": False,
            "error": str(e),
            "error_type": "unknown"
        }


@mcp.tool()
def list_sessions() -> dict:
    """
    List all active tmux sessions created by this tool.

    Returns:
        List of session information including names and attach commands
    """
    try:
        manager = get_tmux_manager()
        sessions = manager.list_sessions()

        return {
            "success": True,
            "count": len(sessions),
            "sessions": [
                {
                    "name": s.name,
                    "project": s.project,
                    "working_directory": s.working_directory,
                    "attach_command": f"tmux attach -t {s.name}",
                    "panes": [
                        {
                            "task_name": p.task_name,
                            "command": p.command,
                            "pane_id": p.pane_id
                        }
                        for p in s.panes.values()
                    ]
                }
                for s in sessions
            ]
        }

    except TmuxNotInstalledError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "tmux_not_installed"
        }
    except Exception as e:
        logger.exception("Failed to list sessions")
        return {
            "success": False,
            "error": str(e),
            "error_type": "unknown"
        }


@mcp.tool()
def kill_session(project: str) -> dict:
    """
    Terminate a tmux session for a project.

    Use this to clean up all background tasks for a project.

    Args:
        project: Name of the project (folder name) to terminate

    Returns:
        Confirmation of session termination
    """
    try:
        manager = get_tmux_manager()

        # Convert project name to session name
        session_name = manager._get_session_name(project)
        manager.kill_session(session_name)

        return {
            "success": True,
            "project": project,
            "session_name": session_name,
            "message": f"All tasks for project '{project}' terminated"
        }

    except SessionNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "session_not_found"
        }
    except TmuxNotInstalledError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "tmux_not_installed"
        }
    except Exception as e:
        logger.exception("Failed to kill session")
        return {
            "success": False,
            "error": str(e),
            "error_type": "unknown"
        }


@mcp.tool()
def kill_task(project: str, task_name: str) -> dict:
    """
    Terminate a specific task (pane) within a project session.

    Use this to stop a specific background task without killing the entire session.

    Args:
        project: Name of the project (folder name)
        task_name: Name of the task to terminate

    Returns:
        Confirmation of task termination
    """
    try:
        manager = get_tmux_manager()
        session_name = manager._get_session_name(project)
        manager.kill_pane(session_name, task_name)

        return {
            "success": True,
            "project": project,
            "task_name": task_name,
            "message": f"Task '{task_name}' terminated in project '{project}'"
        }

    except SessionNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "session_not_found"
        }
    except PaneNotFoundError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "pane_not_found"
        }
    except TmuxNotInstalledError as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": "tmux_not_installed"
        }
    except Exception as e:
        logger.exception("Failed to kill task")
        return {
            "success": False,
            "error": str(e),
            "error_type": "unknown"
        }


def main():
    """Entry point for the MCP server."""
    try:
        # Verify tmux is available at startup
        get_tmux_manager()
        logger.info("tmux-terminal MCP server starting...")
        mcp.run(transport="stdio")
    except TmuxNotInstalledError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
