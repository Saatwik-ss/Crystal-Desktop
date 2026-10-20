import logging
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Core tools exposed to the agent (fewer tools = more reliable tool calling)
AGENT_TOOL_NAMES = {
    "search_repository",
    "read_file",
    "list_files",
    "ast_lookup",
    "find_references",
    "create_plan",
    "update_todo",
    "apply_patch",
    "propose_edit",
    "run_terminal",
    "terminal_spawn",
    "terminal_read",
    "terminal_write",
    "terminal_kill",
    "browser_navigate",
    "browser_click",
    "browser_type",
    "browser_press_key",
    "browser_screenshot",
    "browser_extract_state",
    "git_checkpoint",
    "git_rollback",
    "worktree_create",
    "worktree_list",
    "worktree_diff",
    "worktree_commit",
    "desktop_screenshot",
    "desktop_click",
    "desktop_type",
    "desktop_key_combo",
    "finish",
}

# Allowlisted terminal command prefixes (lowercase match on stripped command)
TERMINAL_ALLOWLIST_PREFIXES = (
    "pytest",
    "python -m pytest",
    "python -m unittest",
    "python -m py_compile",
    "python -m compileall",
    "python -c ",
    "npm test",
    "npm run ",
    "npx ",
    "pnpm test",
    "pnpm run ",
    "yarn test",
    "yarn ",
    "tsc",
    "eslint",
    "ruff ",
    "ruff.",
    "mypy ",
    "cargo test",
    "cargo check",
    "go test",
    "dotnet test",
    "dotnet build",
    "pip show",
    "pip list",
    "node ",
    "ls",
    "dir",
    "type ",
    "cat ",
    "head ",
    "wc ",
    "git status",
    "git diff",
    "git log",
    "git worktree",
    "git branch",
    "git commit",
)

@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable

class ToolExecutor:
    """
    Manages tool execution for LLM.
    Allows LLM to call tools without guessing about repository state.
    """
    
    def __init__(
        self,
        repository_manager,
        ast_service,
        search_service,
        edit_history=None,
        terminal_manager=None,
        process_supervisor=None,
        policy_engine=None,
        browser_manager=None,
        mcp_client_manager=None,
        desktop_agent=None,
        git_checkpoints=None,
        git_worktree_manager=None,
    ):
        self.repository_manager = repository_manager
        self.ast_service = ast_service
        self.search_service = search_service
        self.edit_history = edit_history
        self.terminal_manager = terminal_manager
        self.process_supervisor = process_supervisor
        self.policy_engine = policy_engine
        self.browser_manager = browser_manager
        self.mcp_client_manager = mcp_client_manager
        self.desktop_agent = desktop_agent
        self.git_checkpoints = git_checkpoints
        self.git_worktree_manager = git_worktree_manager
        # Per-request agent session state (set by AgentPlanner)
        self.session_request_id: Optional[str] = None
        self.session_repo_id: str = ""
        self.session_soft_apply: bool = False
        self.session_plan: Optional[Dict[str, Any]] = None
        self.session_snapshots: List[Dict[str, str]] = []
        # Browser-only files are available to tools for the lifetime of one
        # agent request, but are never persisted by local sessions.
        self.session_virtual_files: Dict[str, str] = {}
        self.session_worktree_path: Optional[str] = None
        self.session_ticket_id: Optional[str] = None

        # Register built-in tools
        self.tools: Dict[str, Tool] = {}
        self._register_builtin_tools()

    def begin_session(
        self,
        request_id: str,
        repo_id: str = "",
        soft_apply: bool = False,
        selected_file: Optional[str] = None,
        selected_code: Optional[str] = None,
        worktree_path: Optional[str] = None,
        ticket_id: Optional[str] = None,
    ) -> None:
        self.session_request_id = request_id
        self.session_repo_id = repo_id
        self.session_soft_apply = soft_apply
        self.session_plan = None
        self.session_snapshots = []
        self.session_virtual_files = {}
        self.session_worktree_path = worktree_path
        self.session_ticket_id = ticket_id
        if selected_file and selected_code is not None:
            self.session_virtual_files[self._normalize_file_path(selected_file)] = selected_code

    def end_session(self) -> Dict[str, Any]:
        saved = False
        if (
            self.edit_history
            and self.session_request_id
            and self.session_snapshots
            and self.session_repo_id
            and self.session_repo_id not in ("local", "none", "__none__", "")
        ):
            self.edit_history.save_snapshot(
                self.session_repo_id,
                self.session_request_id,
                [
                    {
                        "file_path": s["file_path"],
                        "before": s["before"],
                        "after": s["after"],
                    }
                    for s in self.session_snapshots
                ],
            )
            saved = True
        info = {
            "request_id": self.session_request_id,
            "snapshots": list(self.session_snapshots),
            "saved": saved,
        }
        self.session_request_id = None
        self.session_repo_id = ""
        self.session_soft_apply = False
        self.session_plan = None
        self.session_snapshots = []
        self.session_virtual_files = {}
        self.session_worktree_path = None
        self.session_ticket_id = None
        return info

    @staticmethod
    def _normalize_file_path(file_path: Any) -> str:
        """Normalize relative editor and repository paths for session lookups."""
        if isinstance(file_path, list):
            file_path = file_path[0] if file_path else ""
        return str(file_path or "").replace("\\", "/").lstrip("./")

    async def _resolve_file_content(self, repo_id: str, file_path: str) -> str:
        """Read the session buffer first, then active worktree, then repository."""
        normalized_path = self._normalize_file_path(file_path)
        if normalized_path in self.session_virtual_files:
            return self.session_virtual_files[normalized_path]
        if self.session_worktree_path:
            target = Path(self.session_worktree_path) / normalized_path
            if target.exists() and target.is_file():
                return target.read_text(encoding="utf-8", errors="replace")
        return await self.repository_manager.read_file(repo_id, normalized_path)

    def _update_virtual_file(self, file_path: str, content: str) -> None:
        """Keep dependent local tool calls in sync with a successful edit."""
        normalized_path = self._normalize_file_path(file_path)
        if normalized_path in self.session_virtual_files:
            self.session_virtual_files[normalized_path] = content

    async def _soft_write(
        self, repo_id: str, file_path: str, before: str, after: str
    ) -> bool:
        """Write file during agent session and record snapshot for undo."""
        if not self.session_soft_apply:
            return False
        if repo_id in ("local", "none", "__none__", None, "") and not self.session_worktree_path:
            return False
        if self.session_worktree_path:
            target = Path(self.session_worktree_path) / self._normalize_file_path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(after, encoding="utf-8")
        else:
            await self.repository_manager.write_file(repo_id, file_path, after)
        # Keep first "before" if same file patched multiple times
        existing = next(
            (s for s in self.session_snapshots if s["file_path"] == file_path),
            None,
        )
        if existing:
            existing["after"] = after
        else:
            self.session_snapshots.append({
                "file_path": file_path,
                "before": before,
                "after": after,
                "repo_id": repo_id,
            })
        return True
    
    def _register_builtin_tools(self):
        """Register all built-in tools"""
        
        # Repository search
        self.register_tool(
            "search_repository",
            "Search repository semantically or by keyword",
            {
                "query": {"type": "string", "description": "Search query"},
                "search_type": {
                    "type": "string",
                    "enum": ["semantic", "keyword", "hybrid"],
                    "default": "semantic"
                },
                "top_k": {"type": "integer", "description": "Number of results", "default": 5}
            },
            self._search_repository
        )
        
        # Semantic search
        self.register_tool(
            "semantic_search",
            "Perform semantic search in repository",
            {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 5}
            },
            self._semantic_search
        )
        
        # Read file
        self.register_tool(
            "read_file",
            "Read file content from repository. Use parameter file_path (or path).",
            {
                "file_path": {"type": "string", "description": "Path to file", "default": ""},
                "path": {"type": "string", "description": "Alias for file_path", "default": ""},
                "line_start": {"type": "integer", "description": "Optional start line", "default": 1},
                "line_end": {"type": "integer", "description": "Optional end line", "default": -1}
            },
            self._read_file
        )
        
        # Write file (registered but not in AGENT_TOOL_NAMES — apply goes through HTTP)
        self.register_tool(
            "write_file",
            "Write content to file",
            {
                "file_path": {"type": "string", "description": "Path to file", "default": ""},
                "path": {"type": "string", "description": "Alias for file_path", "default": ""},
                "content": {"type": "string", "description": "File content", "default": ""}
            },
            self._write_file
        )

        # Propose edit (staged; may soft-apply during agent sessions)
        self.register_tool(
            "propose_edit",
            "Propose a complete file replacement for NEW or tiny files. Prefer apply_patch for existing files. Pass FULL new file content.",
            {
                "file_path": {"type": "string", "description": "Path to file to edit", "default": ""},
                "path": {"type": "string", "description": "Alias for file_path", "default": ""},
                "new_content": {"type": "string", "description": "Complete new file content", "default": ""},
                "content": {"type": "string", "description": "Alias for new_content", "default": ""},
                "rationale": {
                    "type": "string",
                    "description": "Brief reason for the change",
                    "default": "",
                },
            },
            self._propose_edit,
        )

        self.register_tool(
            "apply_patch",
            "Apply an exact search/replace patch to an existing file. Use file_path (or path). old_string must uniquely match once.",
            {
                "file_path": {
                    "type": "string",
                    "description": "Path to existing file",
                    "default": "",
                },
                "path": {
                    "type": "string",
                    "description": "Alias for file_path",
                    "default": "",
                },
                "old_string": {"type": "string", "description": "Exact text to find (must be unique)"},
                "new_string": {"type": "string", "description": "Replacement text"},
                "rationale": {
                    "type": "string",
                    "description": "Brief reason for the change",
                    "default": "",
                },
            },
            self._apply_patch,
        )

        self.register_tool(
            "create_plan",
            "Create an implementation plan with ordered todos for non-trivial work. Call once early before editing.",
            {
                "goal": {"type": "string", "description": "One-sentence goal"},
                "steps": {
                    "type": "array",
                    "description": "Ordered steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                        },
                        "required": ["id", "title"],
                    },
                },
            },
            self._create_plan,
        )

        self.register_tool(
            "update_todo",
            "Update a plan step status as you work.",
            {
                "id": {"type": "string", "description": "Step id from create_plan"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed", "cancelled"],
                },
                "note": {
                    "type": "string",
                    "description": "Optional short note",
                    "default": "",
                },
            },
            self._update_todo,
        )

        self.register_tool(
            "run_terminal",
            "Run an allowlisted verify command (pytest, npm test, tsc, eslint, ruff, mypy, cargo test, go test, etc.) in the repo root.",
            {
                "command": {"type": "string", "description": "Full command string to run (e.g. 'pytest -q'). Do NOT pass a list or array.", "default": ""},
                "cmd": {"type": "string", "description": "Alias for command string. Do NOT pass a list or array.", "default": ""},
            },
            self._run_terminal,
        )

        self.register_tool(
            "finish",
            "Call when the implementation is done (or cannot proceed). Ends the agent loop.",
            {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what changed or why stopping",
                    "default": "",
                },
            },
            self._finish,
        )

        # List files
        self.register_tool(
            "list_files",
            "List all files in repository",
            {},
            self._list_files
        )
        
        # AST lookup
        self.register_tool(
            "ast_lookup",
            "Look up symbol in AST (functions, classes, etc.)",
            {
                "symbol": {"type": "string", "description": "Symbol name"},
                "file_path": {"type": "string", "description": "File to search in"}
            },
            self._ast_lookup
        )
        
        # Find references
        self.register_tool(
            "find_references",
            "Find all references to a symbol",
            {
                "symbol": {"type": "string", "description": "Symbol name"},
                "file_path": {"type": "string", "description": "File to search in"}
            },
            self._find_references
        )
        
        # Build dependency graph
        self.register_tool(
            "build_dependency_graph",
            "Build dependency graph for repository",
            {},
            self._build_dependency_graph
        )
        
        # Generate embeddings
        self.register_tool(
            "generate_embeddings",
            "Generate embeddings for repository",
            {},
            self._generate_embeddings
        )
        
        # Reindex repository
        self.register_tool(
            "reindex_repository",
            "Reindex repository after changes",
            {},
            self._reindex_repository
        )
        
        # Execute terminal
        self.register_tool(
            "execute_terminal",
            "Execute safe terminal command",
            {
                "command": {"type": "string", "description": "Command to execute"}
            },
            self._execute_terminal
        )
        # --- Interactive Terminal & Process Supervision ---
        self.register_tool(
            "terminal_spawn",
            "Spawn an interactive terminal session or background daemon process. Returns session/task ID.",
            {
                "command": {"type": "string", "description": "Command to spawn"},
                "is_daemon": {"type": "boolean", "description": "True for long-running server/watcher", "default": False},
                "name": {"type": "string", "description": "Optional name for process", "default": ""},
            },
            self._terminal_spawn,
        )

        self.register_tool(
            "terminal_read",
            "Read recent stdout/stderr output lines from a terminal session or background daemon.",
            {
                "session_id": {"type": "string", "description": "Terminal session ID or task ID"},
                "lines": {"type": "integer", "description": "Max recent lines to fetch", "default": 50},
            },
            self._terminal_read,
        )

        self.register_tool(
            "terminal_write",
            "Send keyboard input or interactive answers (e.g. 'y\\n') to a running terminal session.",
            {
                "session_id": {"type": "string", "description": "Terminal session ID"},
                "text": {"type": "string", "description": "Input text or keystrokes to send"},
            },
            self._terminal_write,
        )

        self.register_tool(
            "terminal_kill",
            "Terminate an active interactive terminal session or background daemon.",
            {
                "session_id": {"type": "string", "description": "Terminal session ID or task ID"},
            },
            self._terminal_kill,
        )

        # --- Playwright Browser Automation & Multimodal Perception ---
        self.register_tool(
            "browser_navigate",
            "Navigate the browser to a URL and capture page accessibility tree and error telemetry.",
            {
                "url": {"type": "string", "description": "URL to navigate to (e.g. http://localhost:5173)"},
            },
            self._browser_navigate,
        )

        self.register_tool(
            "browser_click",
            "Click an interactive element in the browser using [ref=ID] from accessibility tree or selector.",
            {
                "ref": {"type": "string", "description": "Element ref ID (e.g. '12' or 'ref=12') or CSS selector"},
            },
            self._browser_click,
        )

        self.register_tool(
            "browser_type",
            "Type text into an input or textarea element in the browser.",
            {
                "ref": {"type": "string", "description": "Element ref ID or CSS selector"},
                "text": {"type": "string", "description": "Text to fill into element"},
            },
            self._browser_type,
        )

        self.register_tool(
            "browser_press_key",
            "Press a keyboard key in the browser (e.g. 'Enter', 'Escape', 'Tab').",
            {
                "key": {"type": "string", "description": "Key name to press"},
            },
            self._browser_press_key,
        )

        self.register_tool(
            "browser_screenshot",
            "Capture a high-fidelity viewport screenshot for visual layout and UI verification.",
            {},
            self._browser_screenshot,
        )

        self.register_tool(
            "browser_extract_state",
            "Extract the current page URL, title, compact accessibility DOM tree, and telemetry errors.",
            {},
            self._browser_extract_state,
        )

        # --- Git Checkpoints & Rollbacks ---
        self.register_tool(
            "git_checkpoint",
            "Create an atomic workspace snapshot before making risky edits, allowing automatic rollback.",
            {
                "message": {"type": "string", "description": "Description of checkpoint", "default": "agent-checkpoint"},
            },
            self._git_checkpoint,
        )

        self.register_tool(
            "git_rollback",
            "Roll back the workspace to a previously saved checkpoint if tests or edits fail.",
            {
                "checkpoint_id": {"type": "string", "description": "Checkpoint ID returned from git_checkpoint"},
            },
            self._git_rollback,
        )

        # --- Desktop OS / GUI Control ---
        self.register_tool(
            "desktop_screenshot",
            "Capture a full-desktop screenshot for inspecting native OS windows outside the browser.",
            {},
            self._desktop_screenshot,
        )

        self.register_tool(
            "desktop_click",
            "Click native desktop coordinates (x, y). Moving mouse to corner aborts as safety fail-safe.",
            {
                "x": {"type": "integer", "description": "X coordinate"},
                "y": {"type": "integer", "description": "Y coordinate"},
                "button": {"type": "string", "enum": ["left", "right"], "default": "left"},
                "double": {"type": "boolean", "default": False},
            },
            self._desktop_click,
        )

        self.register_tool(
            "desktop_type",
            "Type text into the currently focused native desktop application.",
            {
                "text": {"type": "string", "description": "Text to type"},
            },
            self._desktop_type,
        )

        self.register_tool(
            "desktop_key_combo",
            "Send key combination (e.g. ['ctrl', 's']) to the focused desktop application.",
            {
                "keys": {"type": "array", "items": {"type": "string"}, "description": "List of key names"},
            },
            self._desktop_key_combo,
        )

        # --- Git Worktree Tools for Isolated Execution ---
        self.register_tool(
            "worktree_create",
            "Create an isolated git worktree for a ticket or experiment",
            {
                "name": {"type": "string", "description": "Worktree name/ticket ID (e.g. tkt-142)"},
                "branch": {"type": "string", "description": "Branch name (optional, defaults to mesh/<name>)"},
            },
            self._worktree_create,
        )
        self.register_tool(
            "worktree_list",
            "List all git worktrees in the repository",
            {},
            self._worktree_list,
        )
        self.register_tool(
            "worktree_diff",
            "Compute git diff in the active worktree against base branch",
            {
                "worktree_path": {"type": "string", "description": "Optional worktree path"},
            },
            self._worktree_diff,
        )
        self.register_tool(
            "worktree_commit",
            "Commit all modified files in the active worktree",
            {
                "message": {"type": "string", "description": "Commit message"},
                "worktree_path": {"type": "string", "description": "Optional worktree path"},
            },
            self._worktree_commit,
        )

    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable
    ):
        """Register a new tool"""
        self.tools[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler
        )
        logger.info(f"Tool registered: {name}")
    
    async def execute_tool(
        self,
        tool_name: str,
        repo_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute a tool with given parameters"""
        if not isinstance(kwargs, dict):
            kwargs = {}

        if tool_name == "read_file" and "path" in kwargs and "file_path" not in kwargs:
            kwargs["file_path"] = kwargs.pop("path")
        if tool_name == "write_file" and "path" in kwargs and "file_path" not in kwargs:
            kwargs["file_path"] = kwargs.pop("path")
        if tool_name == "propose_edit" and "path" in kwargs and "file_path" not in kwargs:
            kwargs["file_path"] = kwargs.pop("path")
        if tool_name == "propose_edit" and "content" in kwargs and "new_content" not in kwargs:
            kwargs["new_content"] = kwargs.pop("content")
        if tool_name == "apply_patch" and "path" in kwargs and "file_path" not in kwargs:
            kwargs["file_path"] = kwargs.pop("path")
        if "cmd" in kwargs and "command" not in kwargs:
            kwargs["command"] = kwargs.pop("cmd")

        # Defensively normalize command argument
        if "command" in kwargs:
            c_val = kwargs["command"]
            if isinstance(c_val, list):
                if len(c_val) >= 3 and c_val[0] in ("bash", "sh", "zsh") and c_val[1] in ("-c", "-lc", "-cl"):
                    kwargs["command"] = str(c_val[2]).strip()
                elif len(c_val) >= 2 and c_val[0] in ("bash", "sh", "zsh") and c_val[1].startswith("-c"):
                    kwargs["command"] = " ".join(str(x) for x in c_val[1:]).strip()
                else:
                    kwargs["command"] = " ".join(str(x) for x in c_val).strip()
            elif not isinstance(c_val, str):
                kwargs["command"] = str(c_val or "").strip()

        # Defensively normalize file_path argument
        if "file_path" in kwargs:
            fp_val = kwargs["file_path"]
            if isinstance(fp_val, list):
                kwargs["file_path"] = str(fp_val[0] if fp_val else "").strip()
            elif not isinstance(fp_val, str):
                kwargs["file_path"] = str(fp_val or "").strip()

        # Defensively normalize new_content argument
        if "new_content" in kwargs:
            nc_val = kwargs["new_content"]
            if isinstance(nc_val, list):
                kwargs["new_content"] = "\n".join(str(x) for x in nc_val)
            elif not isinstance(nc_val, str):
                kwargs["new_content"] = str(nc_val or "")

        if tool_name in self.tools:
            allowed = set(self.tools[tool_name].parameters.keys())
            # create_plan steps is required; allow empty properties tools
            if allowed:
                kwargs = {key: value for key, value in kwargs.items() if key in allowed}
        
        # 1. MCP Dynamic Tool Routing
        if tool_name.startswith("mcp__") and self.mcp_client_manager:
            try:
                res = await self.mcp_client_manager.execute_tool(tool_name, kwargs)
                return {"status": "success", "result": str(res)}
            except Exception as e:
                return {"status": "error", "error": f"MCP execution failed: {e}"}

        # 2. Safety Policy Evaluation & HITL Gate
        if self.policy_engine:
            action_category = "safe"
            if tool_name in ("run_terminal", "terminal_spawn", "terminal_write"):
                action_category = "terminal_command"
            elif tool_name in ("write_file", "apply_patch", "propose_edit"):
                action_category = tool_name
            elif tool_name.startswith("browser_"):
                action_category = tool_name
            elif tool_name.startswith("desktop_"):
                action_category = tool_name

            tier, needs_approval, reason = self.policy_engine.evaluate(action_category, kwargs)
            if needs_approval:
                action_id = self.policy_engine.compute_action_id(action_category, kwargs)
                self.policy_engine.register_pending_approval(action_id, {
                    "action_id": action_id,
                    "tool_name": tool_name,
                    "action_category": action_category,
                    "details": kwargs,
                    "reason": reason,
                    "tier": tier.value,
                })
                return {
                    "status": "approval_required",
                    "action_id": action_id,
                    "tool_name": tool_name,
                    "reason": reason,
                    "tier": tier.value,
                    "details": kwargs,
                }

        if tool_name not in self.tools:
            return {
                "status": "error",
                "error": f"Tool not found: {tool_name}"
            }
        
        try:
            tool = self.tools[tool_name]
            result = await tool.handler(repo_id, **kwargs)
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            logger.error(f"Tool execution error ({tool_name}): {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    # Tool implementations
    
    async def _search_repository(
        self,
        repo_id: str,
        query: str,
        search_type: str = "semantic",
        top_k: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Search repository"""
        return await self.search_service.search_repository(
            repo_id, query, search_type, top_k
        )
    
    async def _semantic_search(
        self,
        repo_id: str,
        query: str,
        top_k: int = 5,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Semantic search"""
        return await self.search_service._semantic_search(repo_id, query, top_k)
    
    async def _read_file(self, repo_id: str, file_path: Any = "", **kwargs) -> str:
        """Read file"""
        if isinstance(file_path, list):
            file_path = file_path[0] if file_path else ""
        raw_target = file_path or kwargs.get("path") or ""
        if isinstance(raw_target, list):
            raw_target = raw_target[0] if raw_target else ""
        target_path = str(raw_target or "").strip()
        if not target_path:
            return "Error: file_path is required"
        content = await self._resolve_file_content(repo_id, target_path)
        
        # Optionally handle line_start and line_end
        line_start = kwargs.get('line_start')
        line_end = kwargs.get('line_end')
        
        if line_start is not None or line_end is not None:
            lines = content.splitlines(keepends=True)
            start_idx = max(0, int(line_start) - 1) if line_start is not None else 0
            end_idx = int(line_end) if line_end is not None and int(line_end) > 0 else len(lines)
            return "".join(lines[start_idx:end_idx])
            
        return content
    
    async def _write_file(
        self,
        repo_id: str,
        file_path: str,
        content: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Write file"""
        return await self.repository_manager.write_file(repo_id, file_path, content)

    def _detect_language(self, file_path: str) -> str:
        lower = file_path.lower()
        if lower.endswith(".py"):
            return "python"
        if lower.endswith((".ts", ".tsx")):
            return "typescript"
        if lower.endswith((".js", ".jsx")):
            return "javascript"
        return "unknown"

    def _validate_proposed_content(
        self,
        file_path: str,
        original: str,
        proposed: str,
    ) -> Dict[str, Any]:
        """Syntax/AST validation for proposed file content."""
        language = self._detect_language(file_path)
        errors: List[str] = []

        if language == "python":
            try:
                compile(proposed, file_path, "exec")
            except SyntaxError as e:
                errors.append(f"Python syntax error: {e.msg} (line {e.lineno})")
            if self.ast_service:
                parsed = self.ast_service.parse_file(proposed, "python")
                if parsed is None and original.strip():
                    # Original may also fail; only fail if proposed is unparsable
                    try:
                        compile(proposed, file_path, "exec")
                    except SyntaxError:
                        pass  # already recorded
                    else:
                        # compile ok but parse_file failed — still ok
                        pass
            return {
                "ok": len(errors) == 0,
                "errors": errors,
                "language": language,
                "skipped": False,
            }

        if language in ("javascript", "typescript"):
            if self.ast_service and self.ast_service.has_tree_sitter:
                parsed = self.ast_service.parse_file(proposed, language)
                # tree-sitter usually returns a tree even for broken code;
                # treat empty/None as failure
                if parsed is None:
                    errors.append(f"{language} parse failed")
                return {
                    "ok": len(errors) == 0,
                    "errors": errors,
                    "language": language,
                    "skipped": False,
                }
            return {
                "ok": True,
                "errors": [],
                "language": language,
                "skipped": True,
            }

        return {
            "ok": True,
            "errors": [],
            "language": language,
            "skipped": True,
        }

    async def _propose_edit(
        self,
        repo_id: str,
        file_path: str,
        new_content: str,
        rationale: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """Propose a full-file edit; soft-apply during agent sessions when enabled."""
        import difflib

        file_path = self._normalize_file_path(file_path)
        original = ""
        try:
            original = await self._resolve_file_content(repo_id, file_path)
        except FileNotFoundError:
            original = ""
        except Exception:
            original = ""

        proposed = new_content if new_content is not None else ""
        validation = self._validate_proposed_content(file_path, original, proposed)

        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
        )
        diff_text = "\n".join(line.rstrip("\n") for line in diff_lines)

        applied = False
        if validation.get("ok", True):
            applied = await self._soft_write(repo_id, file_path, original, proposed)
            self._update_virtual_file(file_path, proposed)

        return {
            "file_path": file_path,
            "original": original,
            "proposed": proposed,
            "diff": diff_text,
            "rationale": rationale or "",
            "validation": validation,
            "is_new_file": original == "" and proposed != "",
            "applied": applied,
        }

    async def _apply_patch(
        self,
        repo_id: str,
        file_path: str,
        old_string: str,
        new_string: str,
        rationale: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        """Apply unique search/replace and optionally soft-write."""
        import difflib

        file_path = self._normalize_file_path(file_path)
        if isinstance(old_string, list):
            old_string = "\n".join(str(x) for x in old_string)
        if isinstance(new_string, list):
            new_string = "\n".join(str(x) for x in new_string)
        old_string = str(old_string or "")
        new_string = str(new_string or "")

        try:
            original = await self._resolve_file_content(repo_id, file_path)
        except Exception as e:
            return {
                "file_path": file_path,
                "error": f"Cannot read file: {e}",
                "validation": {"ok": False, "errors": [str(e)]},
                "applied": False,
            }

        if not old_string:
            return {
                "file_path": file_path,
                "error": "old_string is empty",
                "validation": {"ok": False, "errors": ["old_string is empty"]},
                "applied": False,
            }

        count = original.count(old_string)
        if count == 0:
            return {
                "file_path": file_path,
                "error": "old_string not found in file",
                "validation": {"ok": False, "errors": ["old_string not found"]},
                "applied": False,
                "original": original,
            }
        if count > 1:
            return {
                "file_path": file_path,
                "error": f"old_string matched {count} times; must be unique",
                "validation": {
                    "ok": False,
                    "errors": [f"old_string matched {count} times"],
                },
                "applied": False,
            }

        proposed = original.replace(old_string, new_string if new_string is not None else "", 1)
        validation = self._validate_proposed_content(file_path, original, proposed)
        diff_lines = list(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                proposed.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm="",
            )
        )
        diff_text = "\n".join(line.rstrip("\n") for line in diff_lines)

        applied = False
        if validation.get("ok", True):
            applied = await self._soft_write(repo_id, file_path, original, proposed)
            self._update_virtual_file(file_path, proposed)

        return {
            "file_path": file_path,
            "original": original,
            "proposed": proposed,
            "diff": diff_text,
            "rationale": rationale or "",
            "validation": validation,
            "is_new_file": False,
            "applied": applied,
        }

    async def _create_plan(
        self, repo_id: str, goal: str, steps: Any = None
    ) -> Dict[str, Any]:
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except json.JSONDecodeError:
                steps = []
        if not isinstance(steps, list):
            steps = []
        todos = []
        for i, step in enumerate(steps):
            if isinstance(step, str):
                todos.append({
                    "id": f"step-{i + 1}",
                    "title": step,
                    "status": "pending",
                    "note": "",
                })
            elif isinstance(step, dict):
                todos.append({
                    "id": str(step.get("id") or f"step-{i + 1}"),
                    "title": str(step.get("title") or step.get("name") or f"Step {i + 1}"),
                    "status": "pending",
                    "note": "",
                })
        plan = {"goal": goal or "", "todos": todos}
        self.session_plan = plan
        return plan

    async def _update_todo(
        self,
        repo_id: str,
        id: str,
        status: str,
        note: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        if not self.session_plan:
            self.session_plan = {"goal": "", "todos": []}
        todos = self.session_plan.get("todos") or []
        found = False
        for todo in todos:
            if todo.get("id") == id:
                todo["status"] = status
                if note:
                    todo["note"] = note
                found = True
                break
        if not found:
            todos.append({
                "id": id,
                "title": id,
                "status": status,
                "note": note or "",
            })
            self.session_plan["todos"] = todos
        return {
            "id": id,
            "status": status,
            "note": note or "",
            "plan": self.session_plan,
        }

    async def _run_terminal(self, repo_id: str, command: str, **kwargs) -> Dict[str, Any]:
        return await self._execute_terminal(repo_id, command)

    async def _finish(self, repo_id: str, summary: str = "", **kwargs) -> Dict[str, Any]:
        return {"done": True, "summary": summary or ""}

    async def _list_files(self, repo_id: str, **kwargs) -> List[Dict[str, Any]]:
        """List files"""
        return await self.repository_manager.list_files(repo_id)
    
    async def _ast_lookup(
        self,
        repo_id: str,
        symbol: str,
        file_path: str,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """Look up symbol in AST"""
        content = await self.repository_manager.read_file(repo_id, file_path)
        language = "python" if file_path.endswith(".py") else "javascript"
        ast_data = self.ast_service.parse_file(content, language)
        
        if ast_data:
            return self.ast_service.find_symbol(ast_data, symbol)
        return None
    
    async def _find_references(
        self,
        repo_id: str,
        symbol: str,
        file_path: str,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """Find references"""
        content = await self.repository_manager.read_file(repo_id, file_path)
        language = "python" if file_path.endswith(".py") else "javascript"
        ast_data = self.ast_service.parse_file(content, language)
        
        if ast_data:
            return self.ast_service.find_references(ast_data, symbol)
        return []
    
    async def _build_dependency_graph(self, repo_id: str) -> Dict[str, Any]:
        """Build dependency graph"""
        # This is already done during indexing
        return {"status": "already_indexed"}
    
    async def _generate_embeddings(self, repo_id: str) -> Dict[str, Any]:
        """Generate embeddings"""
        return {"status": "already_generated_during_indexing"}
    
    async def _reindex_repository(self, repo_id: str) -> Dict[str, Any]:
        """Reindex repository"""
        asyncio.create_task(self.repository_manager.index_repository(repo_id))
        return {"status": "reindexing_started"}
    
    async def _execute_terminal(self, repo_id: str, command: Any, **kwargs) -> Dict[str, Any]:
        """Execute allowlisted terminal command in the repo directory."""
        import subprocess

        if isinstance(command, list):
            if len(command) >= 3 and command[0] in ("bash", "sh", "zsh") and command[1] in ("-c", "-lc", "-cl"):
                command = command[2]
            elif len(command) >= 2 and command[0] in ("bash", "sh", "zsh") and command[1].startswith("-c"):
                command = " ".join(str(x) for x in command[1:])
            else:
                command = " ".join(str(x) for x in command)
        elif not isinstance(command, str):
            command = str(command or "")

        cmd = command.strip()
        if not cmd:
            return {"status": "error", "error": "Empty command", "returncode": 1}

        dangerous_patterns = [
            "rm -rf", "rmdir ", "del /", "format ", "dd ",
            "mkfs ", "fdisk ", "sudo ", "chown ", "chmod ",
            ">|", "curl ", "wget ", "Invoke-WebRequest",
        ]
        lower = cmd.lower()
        for pattern in dangerous_patterns:
            if pattern.lower() in lower:
                return {
                    "status": "error",
                    "error": f"Command not allowed: {pattern}",
                    "returncode": 1,
                }

        allowed = any(
            lower == p.rstrip() or lower.startswith(p)
            for p in TERMINAL_ALLOWLIST_PREFIXES
        )
        if not allowed:
            return {
                "status": "error",
                "error": (
                    "Command not on allowlist. Use pytest, npm test/run, tsc, "
                    "eslint, ruff, mypy, cargo test, go test, etc."
                ),
                "returncode": 1,
            }

        if self.session_worktree_path and Path(self.session_worktree_path).exists():
            cwd = self.session_worktree_path
        elif repo_id in ("local", "none", "__none__", None, ""):
            cwd = str(Path.cwd())
        else:
            try:
                repo_path = await self.repository_manager.get_repo_path(repo_id)
                cwd = str(repo_path)
            except Exception:
                cwd = str(self.repository_manager.upload_dir / repo_id)

        import sys, os
        python_path = sys.executable
        python_dir = str(Path(python_path).parent)
        scripts_dir = str(Path(python_path).parent / "Scripts")
        current_path = os.environ.get("PATH", "")
        extended_path = f"{scripts_dir};{python_dir};{current_path}"
        env = {
            **os.environ,
            "PATH": extended_path,
            "PYTHONPATH": f"{cwd};{os.environ.get('PYTHONPATH', '')}",
            "PYTHONUNBUFFERED": "1",
        }

        exec_cmd = cmd
        if cmd == "pytest" or cmd.startswith("pytest "):
            args = cmd[6:].strip()
            exec_cmd = f'"{python_path}" -m pytest {args}'

        try:
            result = subprocess.run(
                exec_cmd,
                shell=True,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            stdout = (result.stdout or "")[:8000]
            stderr = (result.stderr or "")[:4000]
            return {
                "status": "success" if result.returncode == 0 else "failed",
                "stdout": stdout,
                "stderr": stderr,
                "returncode": result.returncode,
                "command": cmd,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "error": "Command timeout (60s)",
                "returncode": 1,
                "command": cmd,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "returncode": 1,
                "command": cmd,
            }
    

    # --- New Agentic Tool Handlers ---

    def _get_target_cwd(self, repo_id: str) -> str:
        if repo_id in ("local", "none", "__none__", None, ""):
            return str(Path.cwd())
        return str(self.repository_manager.upload_dir / repo_id)

    async def _terminal_spawn(self, repo_id: str, command: str, is_daemon: bool = False, name: str = "", **kwargs) -> Dict[str, Any]:
        cwd = self._get_target_cwd(repo_id)
        if is_daemon and self.process_supervisor:
            task_id = self.process_supervisor.spawn(command, cwd=cwd, name=name)
            return {"status": "success", "task_id": task_id, "type": "daemon", "message": f"Daemon process '{name or command}' started"}
        elif self.terminal_manager:
            session = self.terminal_manager.create_session(cwd=cwd)
            session.write(command + "\r\n")
            return {"status": "success", "session_id": session.session_id, "type": "interactive", "message": f"Interactive terminal session {session.session_id} spawned"}
        return {"status": "error", "error": "Terminal manager not initialized"}

    async def _terminal_read(self, repo_id: str, session_id: str, lines: int = 50, **kwargs) -> Dict[str, Any]:
        if self.process_supervisor and session_id in self.process_supervisor.processes:
            output = self.process_supervisor.get_logs(session_id, tail_lines=lines)
            return {"status": "success", "session_id": session_id, "type": "daemon", "output": output}
        elif self.terminal_manager and session_id in self.terminal_manager.sessions:
            session = self.terminal_manager.sessions[session_id]
            history = session.get_history()
            last_lines = "\n".join(history.splitlines()[-lines:])
            return {"status": "success", "session_id": session_id, "type": "interactive", "output": last_lines, "is_alive": session.is_alive()}
        return {"status": "error", "error": f"Session or task {session_id} not found"}

    async def _terminal_write(self, repo_id: str, session_id: str, text: str, **kwargs) -> Dict[str, Any]:
        if self.terminal_manager and session_id in self.terminal_manager.sessions:
            session = self.terminal_manager.sessions[session_id]
            session.write(text)
            return {"status": "success", "session_id": session_id, "action": f"Sent {len(text)} characters"}
        return {"status": "error", "error": f"Interactive session {session_id} not found"}

    async def _terminal_kill(self, repo_id: str, session_id: str, **kwargs) -> Dict[str, Any]:
        killed = False
        if self.process_supervisor and self.process_supervisor.terminate(session_id):
            killed = True
        elif self.terminal_manager and session_id in self.terminal_manager.sessions:
            self.terminal_manager.close_session(session_id)
            killed = True
        if killed:
            return {"status": "success", "session_id": session_id, "message": "Terminated successfully"}
        return {"status": "error", "error": f"Could not find or terminate {session_id}"}

    async def _browser_navigate(self, repo_id: str, url: str, **kwargs) -> Dict[str, Any]:
        if not self.browser_manager:
            return {"status": "error", "error": "Browser manager not initialized"}
        return await self.browser_manager.navigate(url)

    async def _browser_click(self, repo_id: str, ref: str, **kwargs) -> Dict[str, Any]:
        if not self.browser_manager:
            return {"status": "error", "error": "Browser manager not initialized"}
        return await self.browser_manager.click(ref)

    async def _browser_type(self, repo_id: str, ref: str, text: str, **kwargs) -> Dict[str, Any]:
        if not self.browser_manager:
            return {"status": "error", "error": "Browser manager not initialized"}
        return await self.browser_manager.type_text(ref, text)

    async def _browser_press_key(self, repo_id: str, key: str, **kwargs) -> Dict[str, Any]:
        if not self.browser_manager:
            return {"status": "error", "error": "Browser manager not initialized"}
        return await self.browser_manager.press_key(key)

    async def _browser_screenshot(self, repo_id: str, **kwargs) -> Dict[str, Any]:
        if not self.browser_manager:
            return {"status": "error", "error": "Browser manager not initialized"}
        return await self.browser_manager.screenshot()

    async def _browser_extract_state(self, repo_id: str, **kwargs) -> Dict[str, Any]:
        if not self.browser_manager:
            return {"status": "error", "error": "Browser manager not initialized"}
        return await self.browser_manager.get_state()

    async def _git_checkpoint(self, repo_id: str, message: str = "agent-checkpoint", **kwargs) -> Dict[str, Any]:
        cwd = self._get_target_cwd(repo_id)
        if not self.git_checkpoints:
            return {"status": "error", "error": "Git checkpoints manager not available"}
        cp_id = self.git_checkpoints.create_checkpoint(cwd, message=message)
        if cp_id:
            return {"status": "success", "checkpoint_id": cp_id, "message": f"Checkpoint {cp_id} created"}
        return {"status": "error", "error": "Could not create git checkpoint (not a git repository or clean tree)"}

    async def _git_rollback(self, repo_id: str, checkpoint_id: str, **kwargs) -> Dict[str, Any]:
        if not self.git_checkpoints:
            return {"status": "error", "error": "Git checkpoints manager not available"}
        success = self.git_checkpoints.rollback(checkpoint_id)
        if success:
            return {"status": "success", "checkpoint_id": checkpoint_id, "message": f"Rolled back to {checkpoint_id}"}
        return {"status": "error", "error": f"Failed to rollback to {checkpoint_id}"}

    async def _desktop_screenshot(self, repo_id: str, **kwargs) -> Dict[str, Any]:
        if not self.desktop_agent:
            return {"status": "error", "error": "Desktop agent not available"}
        return self.desktop_agent.screenshot()

    async def _desktop_click(self, repo_id: str, x: int, y: int, button: str = "left", double: bool = False, **kwargs) -> Dict[str, Any]:
        if not self.desktop_agent:
            return {"status": "error", "error": "Desktop agent not available"}
        return self.desktop_agent.mouse_click(x, y, button=button, double=double)

    async def _desktop_type(self, repo_id: str, text: str, **kwargs) -> Dict[str, Any]:
        if not self.desktop_agent:
            return {"status": "error", "error": "Desktop agent not available"}
        return self.desktop_agent.type_text(text)

    async def _desktop_key_combo(self, repo_id: str, keys: list, **kwargs) -> Dict[str, Any]:
        if not self.desktop_agent:
            return {"status": "error", "error": "Desktop agent not available"}
        return self.desktop_agent.key_combo(keys)

    def get_tool_schemas(self, tool_names: set[str] | None = None) -> List[Dict[str, Any]]:
        """Get schemas for tools (for LLM function calling)"""
        schemas = []
        for tool_name, tool in self.tools.items():
            if tool_names is not None and tool_name not in tool_names:
                continue

            properties = {}
            required = []
            for key, spec in tool.parameters.items():
                properties[key] = {k: v for k, v in spec.items() if k != "default"}
                if "default" not in spec:
                    required.append(key)

            param_schema: Dict[str, Any] = {
                "type": "object",
                "properties": properties,
            }
            if required:
                param_schema["required"] = required

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool.description,
                    "parameters": param_schema,
                }
            })
        if self.mcp_client_manager:
            for mcp_tool in self.mcp_client_manager.get_all_tools():
                if tool_names is None or mcp_tool["name"] in tool_names:
                    schemas.append({
                        "type": "function",
                        "function": {
                            "name": mcp_tool["name"],
                            "description": mcp_tool["description"],
                            "parameters": {
                                "type": "object",
                                "properties": mcp_tool["parameters"],
                            },
                        }
                    })
        return schemas

    def get_agent_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get schemas for the curated agent tool set"""
        return self.get_tool_schemas(AGENT_TOOL_NAMES)
    async def _worktree_create(self, repo_id: str, name: str, branch: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Create an isolated worktree and bind it to the current agent session."""
        if not self.git_worktree_manager:
            return {"status": "error", "error": "Worktree manager not configured"}
        repo_path = await self.repository_manager.get_repo_path(repo_id)
        wt = self.git_worktree_manager.create_worktree(str(repo_path), name, branch_name=branch)
        self.session_worktree_path = wt["path"]
        return wt

    async def _worktree_list(self, repo_id: str, **kwargs) -> List[Dict[str, Any]]:
        """List active worktrees in the repository."""
        if not self.git_worktree_manager:
            return []
        repo_path = await self.repository_manager.get_repo_path(repo_id)
        return self.git_worktree_manager.list_worktrees(str(repo_path))

    async def _worktree_diff(self, repo_id: str, worktree_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Get diff of the current worktree."""
        if not self.git_worktree_manager:
            return {"status": "error", "error": "Worktree manager not configured"}
        target_path = worktree_path or self.session_worktree_path
        if not target_path:
            return {"status": "error", "error": "No worktree path specified or active"}
        return self.git_worktree_manager.get_diff(target_path)

    async def _worktree_commit(self, repo_id: str, message: str, worktree_path: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Commit changes in the active worktree and record in change ledger."""
        if not self.git_worktree_manager:
            return {"status": "error", "error": "Worktree manager not configured"}
        target_path = worktree_path or self.session_worktree_path
        if not target_path:
            return {"status": "error", "error": "No worktree path specified or active"}
        res = self.git_worktree_manager.commit(target_path, message)
        if res.get("success"):
            try:
                from services.ledger_service import ledger_service
                asyncio.create_task(ledger_service.record_event(
                    project_id=repo_id,
                    ticket_id=self.session_ticket_id,
                    actor_type="agent",
                    actor_id="Crystal Agent",
                    worktree_path=target_path,
                    event_type="commit",
                    summary=f"Commit: {message}",
                    github_references={"commit_sha": res.get("commit_hash")},
                ))
            except Exception as e:
                logger.warning(f"Could not record commit to ledger: {e}")
        return res

