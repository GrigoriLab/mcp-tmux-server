# MCP tmux Terminal Server

An MCP server that provides interactive tmux terminal sessions for Claude Code. Run background tasks in tmux sessions that you can attach to and interact with directly.

## Features

- **Project-based Sessions**: One tmux session per project (folder), multiple tasks as panes
- **Interactive Background Tasks**: Commands run in tmux panes you can attach to
- **Full Terminal Access**: Attach with `tmux attach -t claude-<project>` for full control
- **Output Monitoring**: Claude Code can capture and monitor terminal output
- **Send Input**: Send commands or special keys (Ctrl+C, etc.) to specific tasks
- **Task Management**: List, monitor, and kill individual tasks or entire project sessions

## Architecture

```
Project: myapp/
├── Session: claude-myapp
│   ├── Pane 1: backend (python manage.py runserver)
│   ├── Pane 2: frontend (npm run dev)
│   └── Pane 3: tests (pytest --watch)
```

All tasks for a project share one tmux session with multiple panes.

## Prerequisites

- Python >= 3.10
- [Poetry](https://python-poetry.org/docs/#installation) for dependency management
- tmux installed on your system:
  - macOS: `brew install tmux`
  - Linux: `apt install tmux` or `yum install tmux`

## Installation

```bash
cd mcp-tmux-server
poetry install
```

## Register with Claude Code

```bash
claude mcp add --transport stdio --scope user tmux-terminal -- \
  poetry --directory /path/to/mcp-tmux-server run python -m mcp_tmux.server
```

Or using the virtualenv directly:

```bash
claude mcp add --transport stdio --scope user tmux-terminal -- \
  /path/to/mcp-tmux-server/.venv/bin/python -m mcp_tmux.server
```

### Verify Registration

```bash
claude mcp list
```

## Available Tools

### `run_in_terminal`

Start a command in a new pane within the project's session.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `command` | string | Yes | Shell command to execute |
| `project` | string | No | Project name for grouping tasks (overrides auto-detection from working_directory) |
| `task_name` | string | No | Descriptive name for the task (pane) |
| `working_directory` | string | No | Directory to run in (used for project name if `project` not specified) |

**Example:**
```json
{
  "command": "npm run dev",
  "project": "myapp",
  "task_name": "frontend",
  "working_directory": "/path/to/myapp/frontend"
}
```

Note: If `project` is not specified, the project name is extracted from the last folder component of `working_directory`. Use `project` explicitly when tasks in subdirectories should share a session.

**Returns:**
```json
{
  "success": true,
  "session_name": "claude-myapp",
  "project": "myapp",
  "task_name": "frontend",
  "attach_command": "tmux attach -t claude-myapp"
}
```

### `get_terminal_output`

Capture output from a project session or specific task.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project` | string | Yes | Project name (folder name) |
| `task_name` | string | No | Specific task to capture from |
| `lines` | int | No | Number of lines (default: 100, max: 10000) |
| `include_history` | bool | No | Include scrollback history |

### `send_input`

Send text or special keys to a project session or specific task.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project` | string | Yes | Project name (folder name) |
| `text` | string | Yes | Text to send, or special key |
| `task_name` | string | No | Specific task to send to |
| `press_enter` | bool | No | Press Enter after text (default: true) |

**Special keys:** `C-c` (Ctrl+C), `C-d` (Ctrl+D), `C-z` (Ctrl+Z), `C-l` (Ctrl+L), `Escape`

### `list_sessions`

List all active project sessions with their tasks.

**Returns:**
```json
{
  "success": true,
  "count": 1,
  "sessions": [
    {
      "name": "claude-myapp",
      "project": "myapp",
      "attach_command": "tmux attach -t claude-myapp",
      "panes": [
        {"task_name": "frontend", "command": "npm run dev"},
        {"task_name": "backend", "command": "python manage.py runserver"}
      ]
    }
  ]
}
```

### `kill_session`

Terminate all tasks for a project.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project` | string | Yes | Project name to terminate |

### `kill_task`

Terminate a specific task within a project.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project` | string | Yes | Project name |
| `task_name` | string | Yes | Task to terminate |

## Usage Examples

### Start Multiple Tasks for a Project

Ask Claude Code:
> "Start the backend and frontend for my project"

Claude runs two `run_in_terminal` calls with the same `working_directory`:
```
Task 'backend' started in project session 'claude-myapp'.
Task 'frontend' started in project session 'claude-myapp'.
Attach with: tmux attach -t claude-myapp
```

Both tasks appear as panes in the same tmux session.

### View All Tasks

```bash
tmux attach -t claude-myapp
```

Use `Ctrl+B, arrow keys` to switch between panes.

### Stop a Specific Task

Ask Claude Code:
> "Stop the frontend task in myapp"

Claude uses `kill_task` with `project: "myapp", task_name: "frontend"`.

### Stop All Tasks

Ask Claude Code:
> "Kill all tasks for myapp"

Claude uses `kill_session` with `project: "myapp"`.

## tmux Quick Reference

| Action | Command |
|--------|---------|
| List sessions | `tmux list-sessions` |
| Attach to project | `tmux attach -t claude-<project>` |
| Switch panes | `Ctrl+B`, then arrow keys |
| Detach (keep running) | `Ctrl+B`, then `D` |
| Kill session | `tmux kill-session -t claude-<project>` |
| Scroll in tmux | `Ctrl+B`, then `[`, then arrow keys |
| Exit scroll mode | `Q` |

## Debugging

### Claude Code MCP Debug Mode

```bash
claude --mcp-debug
```

### Test Server Manually

```bash
poetry run python -m mcp_tmux.server
```

### Check Server Health

```bash
claude mcp list
```

## Troubleshooting

### "tmux is not installed"

Install tmux:
- macOS: `brew install tmux`
- Ubuntu/Debian: `sudo apt install tmux`
- RHEL/CentOS: `sudo yum install tmux`

### "Session not found"

The session may have been killed. Check active sessions:
```bash
tmux list-sessions
```

## License

MIT
