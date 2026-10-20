import os
import logging
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException, WebSocketDisconnect, Query
from starlette.websockets import WebSocketState
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import time
import uuid
from starlette.requests import Request
import httpx
from typing import Optional, List, Dict, Any, Set

from services.repository_manager import RepositoryManager
from services.embedding_service import EmbeddingService
from services.ast_service import ASTService
from services.search_service import SearchService
from services.chat_service import ChatService
from services.code_completion_service import CodeCompletionService
from services.tool_executor import ToolExecutor
from services.agent_planner import AgentPlanner
from services.terminal.terminal_manager import TerminalManager
from services.terminal.process_supervisor import ProcessSupervisor
from services.safety.policy_engine import PolicyEngine
from services.safety.git_checkpoints import GitCheckpointManager
from services.browser.browser_manager import BrowserManager
from services.mcp.client_manager import MCPClientManager
from services.os_control.desktop_agent import DesktopAgent
from services.git.worktree_manager import GitWorktreeManager
from services.ledger_service import ledger_service
from services.ticket_service import ticket_service
from services.edit_history import EditHistory
from services.provider_router import detect_provider, get_provider_info, GEMINI_CHAT_MODELS
from database.db import init_db, get_db
from api import repository_routes, chat_routes, search_routes, completion_routes
from services.session_service import SessionService, generate_title_from_text
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global service instances
repository_manager: Optional[RepositoryManager] = None
embedding_service: Optional[EmbeddingService] = None
ast_service: Optional[ASTService] = None
search_service: Optional[SearchService] = None
chat_service: Optional[ChatService] = None
code_completion_service: Optional[CodeCompletionService] = None
tool_executor: Optional[ToolExecutor] = None
agent_planner: Optional[AgentPlanner] = None
edit_history: Optional[EditHistory] = None
terminal_manager: Optional[TerminalManager] = None
process_supervisor: Optional[ProcessSupervisor] = None
policy_engine: Optional[PolicyEngine] = None
git_checkpoints: Optional[GitCheckpointManager] = None
browser_manager: Optional[BrowserManager] = None
mcp_client_manager: Optional[MCPClientManager] = None
desktop_agent: Optional[DesktopAgent] = None
git_worktree_manager: Optional[GitWorktreeManager] = None

class WriteFileBody(BaseModel):
    content: str

class ApplyEditItem(BaseModel):
    file_path: str
    proposed: str

class ApplyEditsBody(BaseModel):
    request_id: str
    edits: List[ApplyEditItem]

class UndoEditsBody(BaseModel):
    request_id: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, cleanup on shutdown"""
    global repository_manager, embedding_service, ast_service, search_service
    global chat_service, code_completion_service, tool_executor, agent_planner, edit_history
    global terminal_manager, process_supervisor, policy_engine, git_checkpoints
    global browser_manager, mcp_client_manager, desktop_agent, git_worktree_manager
    
    logger.info("Initializing services...")
    
    # Initialize database
    await init_db()
    
    # Initialize services
    embedding_service = EmbeddingService()
    repository_manager = RepositoryManager(embedding_service=embedding_service)
    ast_service = ASTService()
    search_service = SearchService(embedding_service)
    chat_service = ChatService()
    code_completion_service = CodeCompletionService()

    terminal_manager = TerminalManager()
    process_supervisor = ProcessSupervisor()
    policy_engine = PolicyEngine(mode="balanced")
    git_checkpoints = GitCheckpointManager()
    browser_manager = BrowserManager(headless=False)
    mcp_client_manager = MCPClientManager()
    desktop_agent = DesktopAgent(enabled=True)
    git_worktree_manager = GitWorktreeManager()
    try:
        await mcp_client_manager.initialize()
    except Exception as e:
        logger.warning(f"MCP client init warning: {e}")

    tool_executor = ToolExecutor(
        repository_manager,
        ast_service,
        search_service,
        edit_history=None,
        terminal_manager=terminal_manager,
        process_supervisor=process_supervisor,
        policy_engine=policy_engine,
        browser_manager=browser_manager,
        mcp_client_manager=mcp_client_manager,
        desktop_agent=desktop_agent,
        git_checkpoints=git_checkpoints,
        git_worktree_manager=git_worktree_manager,
    )
    # edit_history created next; wire after both exist
    edit_history = EditHistory()
    tool_executor.edit_history = edit_history
    agent_planner = AgentPlanner(tool_executor, chat_service)
    
    logger.info("Services initialized successfully")
    
    yield
    
    logger.info("Shutting down services...")
    if terminal_manager:
        terminal_manager.close_all()
    if process_supervisor:
        process_supervisor.terminate_all()
    if browser_manager:
        await browser_manager.close()
    if mcp_client_manager:
        await mcp_client_manager.close_all()
    await embedding_service.close()

app = FastAPI(
    title="AI Coding Assistant",
    description="Full-stack AI coding assistant with repository understanding",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Terminal Status & Health Logging Middleware
@app.middleware("http")
async def terminal_status_middleware(request: Request, call_next):
    req_id = str(uuid.uuid4())[:8]
    start_time = time.perf_counter()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    method = request.method
    path = request.url.path

    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        status_code = response.status_code

        # Health & Color formatting
        if status_code < 400:
            health_tag = "\033[92m[HEALTH: OK]\033[0m"
            status_tag = f"\033[92m{status_code} OK\033[0m" if status_code == 200 else f"\033[92m{status_code}\033[0m"
        elif status_code < 500:
            health_tag = "\033[93m[HEALTH: WARN]\033[0m"
            status_tag = f"\033[93m{status_code} CLIENT_ERROR\033[0m"
        else:
            health_tag = "\033[91m[HEALTH: ERROR]\033[0m"
            status_tag = f"\033[91m{status_code} SERVER_ERROR\033[0m"

        print(
            f"[{timestamp}] [UUID: {req_id}] {health_tag} {method} {path} -> {status_tag} ({duration_ms}ms)",
            flush=True,
        )
        return response
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        health_tag = "\033[91m[HEALTH: ERROR]\033[0m"
        print(
            f"[{timestamp}] [UUID: {req_id}] {health_tag} {method} {path} -> \033[91m500 EXCEPTION\033[0m ({duration_ms}ms) | Error: {exc}",
            flush=True,
        )
        raise exc


# Include routers
app.include_router(repository_routes.router)
app.include_router(chat_routes.router)
app.include_router(search_routes.router)
app.include_router(completion_routes.router)

class ModelsRequest(BaseModel):
    api_key: str

@app.post("/api/models")
async def get_models(body: ModelsRequest):
    api_key = body.api_key.strip()
    if not api_key:
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="No API key provided")
        
    provider = detect_provider(api_key)
    provider_info = get_provider_info(provider)
    models_url = provider_info["models_url"]

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            resp.raise_for_status()
            data = resp.json()
            if provider == "gemini" and "data" in data and isinstance(data["data"], list):
                chat_models = [
                    m for m in data["data"]
                    if "gemini" in m.get("id", "").lower()
                    and not any(x in m.get("id", "").lower() for x in ["embedding", "imagen", "aqa"])
                ]
                if chat_models:
                    data["data"] = chat_models
                else:
                    data["data"] = [{"id": m, "object": "model"} for m in GEMINI_CHAT_MODELS]
            return data
        except Exception as e:
            if provider == "gemini" and isinstance(e, httpx.HTTPStatusError):
                err_text = str(e)
                try:
                    err_json = e.response.json()
                    if "error" in err_json and "message" in err_json["error"]:
                        err_text = err_json["error"]["message"]
                except Exception:
                    pass
                raise HTTPException(status_code=400, detail=err_text)
            raise HTTPException(status_code=400, detail=str(e))

@app.get("/health")

async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


class CreateWorktreeBody(BaseModel):
    name: str
    branch: Optional[str] = None
    base_commit: str = "HEAD"

class CommitWorktreeBody(BaseModel):
    message: str
    author_name: str = "Crystal Agent"
    author_email: str = "agent@crystal.local"

class CreateTicketBody(BaseModel):
    title: str
    description: str = ""
    priority: str = "medium"
    assignee_type: str = "unassigned"
    assignee_id: Optional[str] = None
    criteria: Optional[List[Dict[str, Any]]] = None
    github_issue_number: Optional[int] = None
    github_issue_url: Optional[str] = None

class UpdateTicketBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_type: Optional[str] = None
    assignee_id: Optional[str] = None
    reviewer_id: Optional[str] = None
    active_branch: Optional[str] = None
    active_worktree: Optional[str] = None

class AddCriterionBody(BaseModel):
    description: str
    criterion_type: str = "automated_test"
    verification_command: Optional[str] = None

class UpdateCriterionBody(BaseModel):
    is_satisfied: bool
    evidence_event_id: Optional[str] = None

class RecordLedgerEventBody(BaseModel):
    summary: str
    event_type: str = "edit"
    actor_id: str = "Developer"
    actor_type: str = "human"
    ticket_id: Optional[str] = None
    branch: Optional[str] = None
    worktree_path: Optional[str] = None
    files_changed: Optional[List[str]] = None
    diff_stats: Optional[Dict[str, Any]] = None
    diff_patch: Optional[str] = None
    verification_status: str = "not_run"
    verification_details: Optional[Dict[str, Any]] = None

class OpenLocalRepoBody(BaseModel):
    path: str

@app.post("/api/open-local-repository")
async def open_local_repository(body: OpenLocalRepoBody):
    """Mount a local repository on disk directly without copying files."""
    try:
        return await repository_manager.open_local_repository(body.path)
    except Exception as e:
        logger.error(f"Open local repository error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/upload-repository")
async def upload_repository(
    files: list[UploadFile] = File(...),
    repo_id: Optional[str] = Query(None),
    finalize: bool = Query(True),
):
    """
    Upload and index a repository.
    Accepts multiple files/folders. Send at most 30 files per request
    and pass repo_id to append; set finalize=true on the last batch to start indexing.
    """
    try:
        saved_id = await repository_manager.process_upload(files, repo_id=repo_id)

        if finalize:
            asyncio.create_task(repository_manager.index_repository(saved_id))

        return {
            "id": saved_id,
            "name": saved_id,
            "path": str(repository_manager.upload_dir / saved_id),
            "created_at": datetime.utcnow().isoformat() + "Z",
            "status": "indexing" if finalize else "uploading",
            "message": (
                "Repository uploaded. Indexing started..."
                if finalize
                else "Batch stored. Send remaining files with the same repo_id."
            ),
        }
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/repositories")
async def cleanup_all_repositories():
    """Remove every stored repository, file, and folder row from SQLite."""
    try:
        return await repository_manager.cleanup_sql()
    except Exception as e:
        logger.error(f"Cleanup all error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/repositories/{repo_id}")
async def cleanup_repository(repo_id: str):
    """Remove one repository's files/folders from SQLite, Chroma, and disk."""
    try:
        return await repository_manager.cleanup_sql(repo_id)
    except Exception as e:
        logger.error(f"Cleanup error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/repositories/{repo_id}/status")
async def repository_status(repo_id: str):
    """Get repository indexing status"""
    try:
        status = await repository_manager.get_repository_status(repo_id)
        return status
    except Exception as e:
        logger.error(f"Status error: {e}")
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/repositories/{repo_id}/files")
async def list_repository_files(repo_id: str):
    """List all files in repository"""
    try:
        files = await repository_manager.list_files(repo_id)
        return {"files": files}
    except Exception as e:
        logger.error(f"List files error: {e}")
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/api/repositories/{repo_id}/file/{file_path:path}")
async def read_file(repo_id: str, file_path: str):
    """Read file content"""
    try:
        content = await repository_manager.read_file(repo_id, file_path)
        return {"path": file_path, "content": content}
    except Exception as e:
        logger.error(f"Read file error: {e}")
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/repositories/{repo_id}/file/{file_path:path}")
async def write_file(repo_id: str, file_path: str, body: WriteFileBody):
    """Write file content to disk"""
    try:
        result = await repository_manager.write_file(repo_id, file_path, body.content)
        return result
    except Exception as e:
        logger.error(f"Write file error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/repositories/{repo_id}/edits/apply")
async def apply_edits(repo_id: str, body: ApplyEditsBody):
    """Apply proposed edits after snapshotting current contents for undo."""
    if repo_id in ("local", "none", "__none__"):
        raise HTTPException(
            status_code=400,
            detail="Local sessions apply edits on the client",
        )
    try:
        snapshots = []
        applied = []
        for edit in body.edits:
            file_path = edit.file_path.replace("\\", "/")
            try:
                before = await repository_manager.read_file(repo_id, file_path)
            except FileNotFoundError:
                before = ""
            except Exception:
                before = ""

            snapshots.append({
                "file_path": file_path,
                "before": before,
                "after": edit.proposed,
            })
            await repository_manager.write_file(repo_id, file_path, edit.proposed)
            applied.append({"file_path": file_path, "status": "applied"})

        edit_history.save_snapshot(repo_id, body.request_id, snapshots)
        return {"applied": applied, "request_id": body.request_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Apply edits error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/repositories/{repo_id}/edits/undo")
async def undo_edits(repo_id: str, body: UndoEditsBody):
    """Restore files from the last apply snapshot for this request."""
    if repo_id in ("local", "none", "__none__"):
        raise HTTPException(
            status_code=400,
            detail="Local sessions undo edits on the client",
        )
    try:
        entry = edit_history.pop(repo_id, body.request_id)
        if not entry:
            raise HTTPException(status_code=404, detail="No undo snapshot for this request")

        undone = []
        for snap in entry.files:
            await repository_manager.write_file(repo_id, snap.file_path, snap.before)
            undone.append({"file_path": snap.file_path, "status": "undone"})

        return {"undone": undone, "request_id": body.request_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Undo edits error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

class CreateProjectBody(BaseModel):
    path: str
    name: Optional[str] = None

class CreateSessionBody(BaseModel):
    title: Optional[str] = "New Chat"
    model: Optional[str] = None

class UpdateSessionBody(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None

class SaveSettingsBody(BaseModel):
    default_model: Optional[str] = None
    active_project_id: Optional[str] = None
    active_session_id: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

@app.get("/api/projects")
async def list_all_projects():
    """List all known projects / repositories."""
    try:
        return await repository_manager.list_repositories()
    except Exception as e:
        logger.error(f"List projects error: {e}")
        return []

@app.post("/api/projects")
async def create_or_open_project(body: CreateProjectBody):
    """Create or open a project from local disk path."""
    try:
        return await repository_manager.open_local_repository(body.path)
    except Exception as e:
        logger.error(f"Open project error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and all its indexed files, history, tickets, and sessions."""
    try:
        return await repository_manager.cleanup_sql(project_id)
    except Exception as e:
        logger.error(f"Delete project error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/projects/{project_id}/sessions")
async def list_project_sessions(project_id: str):
    """List all chat sessions for a project."""
    try:
        pid = None if project_id in ("local", "none", "__none__") else project_id
        return await SessionService.list_project_sessions(pid)
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        return []

@app.post("/api/projects/{project_id}/sessions")
async def create_project_session(project_id: str, body: CreateSessionBody = CreateSessionBody()):
    """Create a new chat session for a project."""
    try:
        pid = None if project_id in ("local", "none", "__none__") else project_id
        session = await SessionService.get_or_create_session(
            project_id=pid,
            title=body.title or "New Chat",
            model=body.model
        )
        return {
            "id": session.id,
            "project_id": session.project_id,
            "title": session.title,
            "model": session.model,
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        }
    except Exception as e:
        logger.error(f"Create session error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get full persistent message history for a chat session."""
    try:
        return await SessionService.get_session_messages(session_id)
    except Exception as e:
        logger.error(f"Get session messages error: {e}")
        raise HTTPException(status_code=404, detail=str(e))

@app.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, body: UpdateSessionBody):
    """Update session title or model."""
    try:
        if body.title is not None:
            await SessionService.update_session_title(session_id, body.title)
        if body.model is not None:
            await SessionService.update_session_model(session_id, body.model)
        return {"status": "ok", "session_id": session_id}
    except Exception as e:
        logger.error(f"Update session error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session and all its messages."""
    try:
        deleted = await SessionService.delete_session(session_id)
        return {"status": "deleted" if deleted else "not_found", "session_id": session_id}
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/settings")
async def get_persisted_settings():
    """Get global persistent settings (default model, active project, active session)."""
    from services.llm_config import get_persisted_model
    active_proj = await SessionService.get_user_setting("active_project_id", "")
    active_sess = await SessionService.get_user_setting("active_session_id", "")
    model = get_persisted_model()
    return {
        "default_model": model,
        "active_project_id": active_proj,
        "active_session_id": active_sess,
    }

@app.post("/api/settings")
async def save_user_settings(body: SaveSettingsBody):
    """Save global persistent settings (model, active project, active session)."""
    from services.llm_config import save_persisted_model
    if body.default_model:
        save_persisted_model(body.default_model)
        await SessionService.set_user_setting("default_model", body.default_model)
    if body.active_project_id is not None:
        await SessionService.set_user_setting("active_project_id", body.active_project_id)
    if body.active_session_id is not None:
        await SessionService.set_user_setting("active_session_id", body.active_session_id)
    return {"status": "saved"}


# --- Worktree Management Routes ---
@app.get("/api/repositories/{repo_id}/worktrees")
async def list_worktrees(repo_id: str):
    """List all active Git worktrees for a repository."""
    try:
        repo_path = await repository_manager.get_repo_path(repo_id)
        return git_worktree_manager.list_worktrees(str(repo_path))
    except Exception as e:
        logger.error(f"List worktrees error: {e}")
        return []

@app.post("/api/repositories/{repo_id}/worktrees")
async def create_worktree(repo_id: str, body: CreateWorktreeBody):
    """Create a new isolated Git worktree on a dedicated branch."""
    try:
        repo_path = await repository_manager.get_repo_path(repo_id)
        wt = git_worktree_manager.create_worktree(
            str(repo_path),
            name=body.name,
            branch_name=body.branch,
            base_commit=body.base_commit
        )
        return wt
    except Exception as e:
        logger.error(f"Create worktree error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/repositories/{repo_id}/worktrees/{name}")
async def remove_worktree(repo_id: str, name: str, delete_branch: bool = False):
    """Remove a worktree and clean up."""
    try:
        repo_path = await repository_manager.get_repo_path(repo_id)
        success = git_worktree_manager.remove_worktree(str(repo_path), name, delete_branch=delete_branch)
        return {"status": "removed" if success else "failed"}
    except Exception as e:
        logger.error(f"Remove worktree error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/repositories/{repo_id}/worktrees/{name}/diff")
async def get_worktree_diff(repo_id: str, name: str, base_ref: Optional[str] = None):
    """Get the unified diff for changes inside the worktree."""
    try:
        repo_path = await repository_manager.get_repo_path(repo_id)
        wt_dir = git_worktree_manager.get_worktree_dir(str(repo_path), name)
        return git_worktree_manager.get_diff(str(wt_dir), base_ref=base_ref)
    except Exception as e:
        logger.error(f"Worktree diff error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/repositories/{repo_id}/worktrees/{name}/commit")
async def commit_worktree(repo_id: str, name: str, body: CommitWorktreeBody):
    """Commit changes inside the worktree with attributed authorship."""
    try:
        repo_path = await repository_manager.get_repo_path(repo_id)
        wt_dir = git_worktree_manager.get_worktree_dir(str(repo_path), name)
        res = git_worktree_manager.commit(
            str(wt_dir),
            message=body.message,
            author_name=body.author_name,
            author_email=body.author_email
        )
        if res.get("success"):
            await ledger_service.record_event(
                project_id=repo_id,
                actor_id=body.author_name,
                actor_type="agent" if "agent" in body.author_name.lower() else "human",
                worktree_path=str(wt_dir),
                event_type="commit",
                summary=f"Commit: {body.message}",
                github_references={"commit_sha": res.get("commit_hash")},
            )
        return res
    except Exception as e:
        logger.error(f"Worktree commit error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

# --- Change Ledger Routes ---
@app.get("/api/projects/{project_id}/ledger")
async def list_ledger_events(
    project_id: str,
    ticket_id: Optional[str] = None,
    event_type: Optional[str] = None,
    verification_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Fetch change ledger events for a project with optional filters."""
    try:
        return await ledger_service.list_events(
            project_id=project_id,
            ticket_id=ticket_id,
            event_type=event_type,
            verification_status=verification_status,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(f"List ledger events error: {e}")
        return []

@app.post("/api/projects/{project_id}/ledger")
async def record_ledger_event(project_id: str, body: RecordLedgerEventBody):
    """Record a structured engineering event in the append-only change ledger."""
    try:
        return await ledger_service.record_event(
            project_id=project_id,
            summary=body.summary,
            event_type=body.event_type,
            actor_id=body.actor_id,
            actor_type=body.actor_type,
            ticket_id=body.ticket_id,
            branch=body.branch,
            worktree_path=body.worktree_path,
            files_changed=body.files_changed,
            diff_stats=body.diff_stats,
            diff_patch=body.diff_patch,
            verification_status=body.verification_status,
            verification_details=body.verification_details
        )
    except Exception as e:
        logger.error(f"Record ledger event error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/projects/{project_id}/ledger/stats")
async def get_ledger_project_stats(project_id: str):
    """Get high-level activity metrics: total changes, verified changes, open tickets."""
    try:
        return await ledger_service.get_project_stats(project_id)
    except Exception as e:
        logger.error(f"Get ledger stats error: {e}")
        return {"total_changes": 0, "verified_changes": 0, "open_tickets": 0}

# --- Ticket Management Routes ---
@app.get("/api/projects/{project_id}/tickets")
async def list_project_tickets(project_id: str, status: Optional[str] = None):
    """List tickets for a project with their acceptance criteria."""
    try:
        return await ticket_service.list_tickets(project_id, status=status)
    except Exception as e:
        logger.error(f"List tickets error: {e}")
        return []

@app.post("/api/projects/{project_id}/tickets")
async def create_project_ticket(project_id: str, body: CreateTicketBody):
    """Create a new ticket with optional acceptance criteria."""
    try:
        return await ticket_service.create_ticket(
            project_id=project_id,
            title=body.title,
            description=body.description,
            priority=body.priority,
            assignee_type=body.assignee_type,
            assignee_id=body.assignee_id,
            criteria=body.criteria,
            github_issue_number=body.github_issue_number,
            github_issue_url=body.github_issue_url
        )
    except Exception as e:
        logger.error(f"Create ticket error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/tickets/{ticket_id}")
async def get_ticket_details(ticket_id: str):
    """Get full details of a ticket and its acceptance criteria."""
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.patch("/api/tickets/{ticket_id}")
async def update_ticket_details(ticket_id: str, body: UpdateTicketBody):
    """Update ticket status, assignee, priority, or branch."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    ticket = await ticket_service.update_ticket(ticket_id, updates)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket

@app.post("/api/tickets/{ticket_id}/worktree")
async def activate_ticket_worktree(ticket_id: str):
    """One-click create or activate an isolated worktree for this ticket."""
    ticket = await ticket_service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    repo_id = ticket["project_id"]
    repo_path = await repository_manager.get_repo_path(repo_id)
    
    wt_name = ticket["id"]
    branch_name = f"mesh/{wt_name}"
    
    wt = git_worktree_manager.create_worktree(
        str(repo_path),
        name=wt_name,
        branch_name=branch_name
    )
    
    # Update ticket with active worktree and branch
    await ticket_service.update_ticket(ticket_id, {
        "active_worktree": wt["path"],
        "active_branch": wt["branch"],
        "status": "in_progress" if ticket["status"] == "todo" else ticket["status"]
    })
    
    # Record to ledger
    await ledger_service.record_event(
        project_id=repo_id,
        ticket_id=ticket_id,
        actor_id="System",
        actor_type="system",
        branch=branch_name,
        worktree_path=wt["path"],
        event_type="edit",
        summary=f"Activated isolated worktree for ticket {ticket_id}",
    )
    
    return {
        "ticket_id": ticket_id,
        "worktree": wt
    }

@app.post("/api/tickets/{ticket_id}/criteria")
async def add_ticket_criterion(ticket_id: str, body: AddCriterionBody):
    """Add an executable acceptance criterion to a ticket."""
    return await ticket_service.add_criterion(
        ticket_id=ticket_id,
        description=body.description,
        criterion_type=body.criterion_type,
        verification_command=body.verification_command
    )

@app.patch("/api/criteria/{criterion_id}")
async def update_criterion_status(criterion_id: str, body: UpdateCriterionBody):
    """Update criterion satisfied state and evidence link."""
    success = await ticket_service.update_criterion(
        criterion_id=criterion_id,
        is_satisfied=body.is_satisfied,
        evidence_event_id=body.evidence_event_id
    )
    return {"status": "updated" if success else "not_found"}

@app.websocket("/ws/chat/{repo_id}")
async def websocket_chat(websocket: WebSocket, repo_id: str):
    """WebSocket endpoint for real-time chat with streaming responses"""
    ws_id = str(uuid.uuid4())[:8]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [UUID: {ws_id}] \033[92m[HEALTH: OK]\033[0m WS /ws/chat/{repo_id} -> \033[92mCONNECTED\033[0m", flush=True)
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_snippet = str(data.get("message") or "")[:40].replace("\n", " ")
            msg_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            api_key_val = data.get("api_key")
            key_preview = f"{api_key_val[:6]}... (len {len(api_key_val)})" if api_key_val else "None (using server env)"
            print(f"[{msg_ts}] [UUID: {ws_id}] \033[92m[HEALTH: OK]\033[0m WS /ws/chat/{repo_id} -> RECEIVED_MSG: \"{msg_snippet}\" | key: {key_preview} | model: {data.get('model') or 'default'}", flush=True)

            await websocket.send_json({
                "type": "planning",
                "content": "Loading repository context…",
            })

            # Local session (no uploaded repo) gets empty context
            if repo_id in ("local", "none", "__none__"):
                repo_context = {"files": [], "total_files": 0, "languages": []}
            else:
                try:
                    repo_context = await repository_manager.get_repository_context(repo_id)
                except Exception:
                    repo_context = {"files": [], "total_files": 0, "languages": []}
            
            session_id = data.get("session_id")
            user_msg = str(data.get("message") or "")
            model_used = data.get("model")

            # 1. Ensure persistent session exists
            project_id = None if repo_id in ("local", "none", "__none__") else repo_id
            session = await SessionService.get_or_create_session(
                session_id=session_id,
                project_id=project_id,
                model=model_used
            )
            session_id = session.id

            # Persist model choice
            if model_used:
                from services.llm_config import save_persisted_model
                save_persisted_model(model_used)
                await SessionService.set_user_setting("default_model", model_used)

            # 2. Persist user message
            await SessionService.add_chat_message(
                session_id=session_id,
                role="user",
                content=user_msg,
                msg_type="message"
            )

            # 3. Auto-generate title on first message if needed
            if session.title in ("New Chat", "", None):
                new_title = generate_title_from_text(user_msg)
                await SessionService.update_session_title(session_id, new_title)
                session.title = new_title
                await websocket.send_json({
                    "type": "session_updated",
                    "session_id": session_id,
                    "title": new_title
                })

            # 4. Fetch recent conversation history for planner
            conv_history = await SessionService.get_recent_history_for_planner(session_id, limit=8)
            if conv_history and conv_history[-1].get("content") == user_msg:
                conv_history.pop()

            accumulated_assistant_content = ""
            assistant_thought = ""
            assistant_plan = None
            assistant_edits = None
            assistant_logs = []

            # Process chat with agent
            async for chunk in agent_planner.process_user_request(
                message=user_msg,
                repo_id=repo_id,
                context=repo_context,
                selected_file=data.get("selected_file"),
                selected_code=data.get("selected_code"),
                conversation_history=conv_history,
                api_key=data.get("api_key"),
                model=model_used,
                user_system_prompt=data.get("system_prompt"),
                enable_planning=bool(data.get("enable_planning")),
                worktree_path=data.get("worktree_path"),
                ticket_id=data.get("ticket_id"),
            ):
                chunk_type = chunk.get("type")
                if chunk_type == "message" and chunk.get("content"):
                    accumulated_assistant_content += chunk.get("content", "")
                elif chunk_type == "thought" and chunk.get("content"):
                    assistant_thought = (assistant_thought + "\n" + chunk.get("content", "")).strip()
                elif chunk_type == "planning" and chunk.get("plan"):
                    assistant_plan = chunk.get("plan")
                elif chunk_type == "edit_proposal" and chunk.get("edits"):
                    assistant_edits = chunk.get("edits")
                elif chunk_type == "terminal_event" and chunk.get("data"):
                    assistant_logs.append(chunk.get("data"))

                chunk["session_id"] = session_id
                await websocket.send_json(chunk)

            # 5. Persist assistant turn to database
            if accumulated_assistant_content or assistant_plan or assistant_edits:
                await SessionService.add_chat_message(
                    session_id=session_id,
                    role="assistant",
                    content=accumulated_assistant_content,
                    thought=assistant_thought or None,
                    plan=assistant_plan,
                    proposed_edits=assistant_edits,
                    terminal_logs=assistant_logs if assistant_logs else None,
                    msg_type="message"
                )
                
    except WebSocketDisconnect:
        disc_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{disc_ts}] [UUID: {ws_id}] \033[92m[HEALTH: OK]\033[0m WS /ws/chat/{repo_id} -> \033[93mDISCONNECTED\033[0m", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        err_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{err_ts}] [UUID: {ws_id}] \033[91m[HEALTH: ERROR]\033[0m WS /ws/chat/{repo_id} -> \033[91mERROR\033[0m: {e}", flush=True)
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"error": str(e), "type": "error"})
        except Exception:
            pass
    finally:
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass

@app.websocket("/ws/completion/{repo_id}")
async def websocket_completion(websocket: WebSocket, repo_id: str):
    """WebSocket endpoint for code completion with streaming"""
    ws_id = str(uuid.uuid4())[:8]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [UUID: {ws_id}] \033[92m[HEALTH: OK]\033[0m WS /ws/completion/{repo_id} -> \033[92mCONNECTED\033[0m", flush=True)
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            
            if repo_id in ("local", "none", "__none__"):
                repo_context = {"files": [], "total_files": 0, "languages": []}
            else:
                try:
                    repo_context = await repository_manager.get_repository_context(repo_id)
                except Exception:
                    repo_context = {"files": [], "total_files": 0, "languages": []}
            
            # Stream completion
            async for chunk in code_completion_service.stream_completion(
                prompt=data.get("prompt"),
                file_path=data.get("file_path"),
                repo_context=repo_context,
                language=data.get("language", "javascript"),
                api_key=data.get("api_key"),
                model=data.get("model"),
                user_system_prompt=data.get("system_prompt"),
                suffix=data.get("suffix") or "",
            ):
                if isinstance(chunk, str):
                    await websocket.send_json(json.loads(chunk))
                else:
                    await websocket.send_json(chunk)
                
    except WebSocketDisconnect:
        disc_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{disc_ts}] [UUID: {ws_id}] \033[92m[HEALTH: OK]\033[0m WS /ws/completion/{repo_id} -> \033[93mDISCONNECTED\033[0m", flush=True)
    except Exception as e:
        err_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{err_ts}] [UUID: {ws_id}] \033[91m[HEALTH: ERROR]\033[0m WS /ws/completion/{repo_id} -> \033[91mERROR\033[0m: {e}", flush=True)
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json({"error": str(e), "type": "error"})
        except Exception:
            pass
    finally:
        try:
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass


# -------------------------------------------------------------
# Agentic & Environmental Endpoints: Terminal, Browser, Safety
# -------------------------------------------------------------

@app.websocket("/ws/terminal/{session_id}")
async def websocket_terminal(websocket: WebSocket, session_id: str):
    """Bidirectional streaming WebSocket for xterm.js terminal emulator."""
    await websocket.accept()
    session = terminal_manager.get_session(session_id)
    if not session:
        # Auto-create if not existing
        session = terminal_manager.create_session(session_id=session_id)

    loop = asyncio.get_running_loop()

    # Send full backlog on connection
    history = session.get_history()
    if history:
        await websocket.send_text(history)

    def on_output(data: str):
        try:
            asyncio.run_coroutine_threadsafe(websocket.send_text(data), loop)
        except Exception:
            pass

    session.add_listener(on_output)
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                payload = json.loads(msg)
                if payload.get("type") == "input":
                    session.write(payload.get("data", ""))
                elif payload.get("type") == "resize":
                    session.resize(payload.get("rows", 24), payload.get("cols", 80))
                elif payload.get("type") == "signal":
                    session.send_signal(payload.get("signal", "SIGINT"))
            except json.JSONDecodeError:
                # Raw keystrokes
                session.write(msg)
    except WebSocketDisconnect:
        session.remove_listener(on_output)
    except Exception as e:
        session.remove_listener(on_output)

@app.get("/api/terminal/sessions")
async def list_terminal_sessions():
    return {"sessions": terminal_manager.list_sessions()}

@app.post("/api/terminal/sessions")
async def create_terminal_session(body: Optional[Dict[str, Any]] = None):
    b = body or {}
    session = terminal_manager.create_session(
        cwd=b.get("cwd"),
        shell=b.get("shell"),
        rows=b.get("rows", 24),
        cols=b.get("cols", 80),
    )
    return {"session_id": session.session_id, "cwd": session.cwd}

@app.delete("/api/terminal/sessions/{session_id}")
async def close_terminal_session(session_id: str):
    terminal_manager.close_session(session_id)
    return {"status": "closed", "session_id": session_id}

@app.get("/api/processes")
async def list_processes():
    return {"processes": process_supervisor.list_processes()}

@app.get("/api/processes/{task_id}/logs")
async def get_process_logs(task_id: str, tail: int = 100):
    logs = process_supervisor.get_logs(task_id, tail_lines=tail)
    return {"task_id": task_id, "logs": logs}

@app.delete("/api/processes/{task_id}")
async def terminate_process(task_id: str):
    success = process_supervisor.terminate(task_id)
    return {"task_id": task_id, "terminated": success}

@app.get("/api/browser/state")
async def get_browser_state():
    return await browser_manager.get_state()

@app.post("/api/browser/navigate")
async def browser_navigate(body: Dict[str, str]):
    url = body.get("url", "")
    return await browser_manager.navigate(url)

@app.post("/api/browser/click")
async def browser_click(body: Dict[str, str]):
    ref = body.get("ref", "")
    return await browser_manager.click(ref)

@app.get("/api/browser/screenshot")
async def browser_screenshot():
    return await browser_manager.screenshot()

@app.get("/api/safety/pending")
async def list_pending_approvals():
    return {"pending": list(policy_engine.pending_approvals.values())}

@app.post("/api/safety/approve")
async def approve_safety_action(body: Dict[str, str]):
    action_id = body.get("action_id", "")
    scope = body.get("scope", "once")
    policy_engine.grant_approval(action_id, scope=scope)
    return {"status": "approved", "action_id": action_id, "scope": scope}

@app.post("/api/safety/reject")
async def reject_safety_action(body: Dict[str, str]):
    action_id = body.get("action_id", "")
    policy_engine.reject_approval(action_id)
    return {"status": "rejected", "action_id": action_id}

@app.get("/api/mcp/tools")
async def list_mcp_tools():
    return {"tools": mcp_client_manager.get_all_tools()}

# Serve compiled frontend (dist) if available
def _resolve_frontend_dist() -> Path:
    candidates = [
        Path(__file__).resolve().parent.parent / "frontend" / "dist",
        Path(__file__).resolve().parent / "frontend" / "dist",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Crystal" / "frontend" / "dist",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Crystal" / "app" / "resources" / "frontend" / "dist",
    ]
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"

frontend_dist = _resolve_frontend_dist()
if (frontend_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

if frontend_dist.exists():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/") or full_path == "health":
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend index.html not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
