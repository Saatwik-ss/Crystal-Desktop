import os
import shutil
import subprocess
import tempfile
import asyncio
import pytest
from pathlib import Path
from typing import Dict, Any, List

from database.db import init_db, get_db
from database.models import (
    Repository,
    RepositoryFile,
    IndexingStatus,
    CodeSnapshot,
    ChatSession,
    ChatMessage,
    UserSetting,
    Ticket,
    TicketAcceptanceCriteria,
    ChangeLedgerEvent,
)
from services.repository_manager import RepositoryManager
from services.tool_executor import ToolExecutor
from services.safety.policy_engine import PolicyEngine, RiskTier
from services.safety.git_checkpoints import GitCheckpointManager
from services.git.worktree_manager import GitWorktreeManager
from services.agent_planner import AgentPlanner
from services.chat_service import ChatService
from services.ticket_service import ticket_service
from services.ledger_service import ledger_service
from services.session_service import SessionService
from services.llm_config import (
    normalize_tool_args,
    merge_system_prompt,
    supports_tools,
    resolve_model,
)

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
def sample_repository():
    """Create a temporary initialized git repository with multi-file code."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir) / "test_sample_repo"
        repo_path.mkdir(parents=True, exist_ok=True)

        # Initialize git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_path), check=True)
        subprocess.run(["git", "config", "user.email", "tester@crystal.local"], cwd=str(repo_path), check=True)

        # File 1: src/calculator.py
        src_dir = repo_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        calc_file = src_dir / "calculator.py"
        calc_file.write_text(
            '"""Math functions."""\n\n'
            'def add(a: int, b: int) -> int:\n'
            '    return a + b\n\n'
            'def subtract(a: int, b: int) -> int:\n'
            '    return a - b\n',
            encoding="utf-8"
        )

        # File 2: src/utils.py
        utils_file = src_dir / "utils.py"
        utils_file.write_text(
            'def format_result(val: int) -> str:\n'
            '    return f"Result: {val}"\n',
            encoding="utf-8"
        )

        # File 3: tests/test_calculator.py
        tests_dir = repo_path / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        test_file = tests_dir / "test_calculator.py"
        test_file.write_text(
            'from src.calculator import add, subtract\n\n'
            'def test_add():\n'
            '    assert add(2, 3) == 5\n\n'
            'def test_subtract():\n'
            '    assert subtract(5, 3) == 2\n',
            encoding="utf-8"
        )

        # File 4: README.md
        readme_file = repo_path / "README.md"
        readme_file.write_text("# Test Sample Repository\nA sample repository for pipeline testing.\n", encoding="utf-8")

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial test commit"], cwd=str(repo_path), check=True)

        yield str(repo_path)


@pytest.mark.anyio
async def test_repo_indexing_and_file_inspection(sample_repository):
    """Test full repository indexing, file listing, file reading, and context building."""
    await init_db()
    repo_mgr = RepositoryManager()

    # 1. Open and index repository
    repo_data = await repo_mgr.open_local_repository(sample_repository)
    repo_id = repo_data["id"]
    assert repo_id is not None
    assert repo_data["name"] == "test_sample_repo"

    # Index repository directly
    await repo_mgr.index_repository(repo_id)

    status = await repo_mgr.get_repository_status(repo_id)
    assert status["status"] == "completed"
    assert status["total_files"] >= 4

    # 2. List files
    files = await repo_mgr.list_files(repo_id)
    file_paths = [f["path"] for f in files]
    assert any("src/calculator.py" in p for p in file_paths)
    assert any("src/utils.py" in p for p in file_paths)
    assert any("tests/test_calculator.py" in p for p in file_paths)
    assert any("README.md" in p for p in file_paths)

    # 3. Read file contents and verify
    calc_content = await repo_mgr.read_file(repo_id, "src/calculator.py")
    assert "def add(a: int, b: int) -> int:" in calc_content
    assert "def subtract(a: int, b: int) -> int:" in calc_content

    # 4. Repository context for LLM
    context = await repo_mgr.get_repository_context(repo_id)
    assert context["total_files"] >= 4
    assert "python" in [l.lower() for l in context["languages"]]


@pytest.mark.anyio
async def test_tool_selection_and_query_disambiguation(sample_repository):
    """Test that the planner accurately identifies which queries need which tools."""
    await init_db()
    repo_mgr = RepositoryManager()
    repo_data = await repo_mgr.open_local_repository(sample_repository)
    repo_id = repo_data["id"]
    context = await repo_mgr.get_repository_context(repo_id)

    policy = PolicyEngine(mode="balanced")
    checkpoints = GitCheckpointManager()
    worktree = GitWorktreeManager()
    executor = ToolExecutor(
        repo_mgr,
        ast_service=None,
        search_service=None,
        policy_engine=policy,
        git_checkpoints=checkpoints,
        git_worktree_manager=worktree
    )
    planner = AgentPlanner(executor, ChatService())

    # A. Simple question -> Should use direct chat prompt, no tool directives
    direct_prompt = planner._build_direct_chat_system_prompt(context)
    assert "Do NOT attempt to call tools" in direct_prompt
    assert "Answer questions and provide solutions directly in chat" in direct_prompt

    # B. Repository query -> Uses direct repo tools
    direct_tools = planner._build_chat_system_prompt(context)
    assert "apply_patch" in direct_tools
    assert "propose_edit" in direct_tools

    # C. Full Agent loop with multi-step planning
    agent_prompt = planner._build_agent_system_prompt(context)
    assert "create_plan" in agent_prompt
    assert "update_todo" in agent_prompt
    assert "run_terminal" in agent_prompt

    # D. Single file edit execution via ToolExecutor
    executor.begin_session("test-req-1", repo_id=repo_id, soft_apply=True)
    patch_res = await executor.execute_tool(
        "apply_patch",
        repo_id,
        file_path="src/calculator.py",
        old_string="def subtract(a: int, b: int) -> int:\n    return a - b",
        new_string="def subtract(a: int, b: int) -> int:\n    return a - b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b",
        rationale="Add multiply function to calculator"
    )
    assert patch_res["status"] == "success"
    assert "def multiply" in patch_res["result"]["proposed"]

    # E. Multi-file edit coordination (editing second file in same session)
    test_patch_res = await executor.execute_tool(
        "apply_patch",
        repo_id,
        file_path="tests/test_calculator.py",
        old_string="def test_subtract():\n    assert subtract(5, 3) == 2",
        new_string="def test_subtract():\n    assert subtract(5, 3) == 2\n\ndef test_multiply():\n    from src.calculator import multiply\n    assert multiply(3, 4) == 12",
        rationale="Add unit test for multiply"
    )
    assert test_patch_res["status"] == "success"
    assert "def test_multiply" in test_patch_res["result"]["proposed"]

    # F. Verify both modified files are reflected in session buffer
    curr_calc = await executor.execute_tool("read_file", repo_id, file_path="src/calculator.py")
    assert "def multiply" in curr_calc["result"]
    curr_test = await executor.execute_tool("read_file", repo_id, file_path="tests/test_calculator.py")
    assert "def test_multiply" in curr_test["result"]

    executor.end_session()


@pytest.mark.anyio
async def test_defensive_string_and_array_handling():
    """Verify that array commands or paths never cause 'list' object has no attribute 'strip'."""
    # 1. normalize_tool_args with array commands
    norm1 = normalize_tool_args("run_terminal", {"cmd": ["bash", "-lc", "pytest -q"], "timeout": 5000})
    assert norm1["command"] == "pytest -q"

    norm2 = normalize_tool_args("run_terminal", {"command": ["npm", "test"]})
    assert norm2["command"] == "npm test"

    norm3 = normalize_tool_args("run_terminal", {"cmd": "pytest -q"})
    assert norm3["command"] == "pytest -q"

    # 2. normalize_tool_args with array file paths and content
    norm4 = normalize_tool_args("propose_edit", {
        "path": ["src/calculator.py"],
        "content": ["def foo():", "    return 42"]
    })
    assert norm4["file_path"] == "src/calculator.py"
    assert norm4["new_content"] == "def foo():\n    return 42"

    # 3. PolicyEngine evaluates array commands safely
    pe = PolicyEngine(mode="balanced")
    tier, needs_appr, reason = pe.evaluate("terminal_command", {"command": ["bash", "-lc", "pytest -q"]})
    assert tier == RiskTier.SAFE
    assert needs_appr is False

    # 4. Strict mode with array command
    pe_strict = PolicyEngine(mode="strict")
    tier, needs_appr, reason = pe_strict.evaluate("terminal_command", {"command": ["pytest"]})
    assert needs_appr is True

    # 5. ToolExecutor._execute_terminal with array command
    repomgr = RepositoryManager()
    checkpoints = GitCheckpointManager()
    worktree = GitWorktreeManager()
    executor = ToolExecutor(
        repomgr,
        None,
        None,
        policy_engine=pe,
        git_checkpoints=checkpoints,
        git_worktree_manager=worktree
    )
    res = await executor._execute_terminal("local", ["bash", "-lc", "pytest --version"])
    assert res.get("status") in ("success", "error")


@pytest.mark.anyio
async def test_jira_and_ticketing_pipeline(sample_repository):
    """Test ticket creation, criteria evaluation, worktree isolation, and change ledger."""
    await init_db()
    repo_mgr = RepositoryManager()
    repo_data = await repo_mgr.open_local_repository(sample_repository)
    project_id = repo_data["id"]

    # 1. Create Ticket
    ticket = await ticket_service.create_ticket(
        project_id=project_id,
        title="Add matrix operations to calculator",
        description="Implement dot product and 2D matrix multiplication",
        priority="high",
        criteria=[
            {"description": "matrix_dot_product handles 1D vectors"},
            {"description": "matrix_multiply handles 2x2 matrices"},
        ],
    )
    ticket_id = ticket["id"]
    assert ticket_id is not None
    assert ticket["title"] == "Add matrix operations to calculator"
    assert ticket["priority"] == "high"

    # 2. Retrieve Ticket & Criteria
    ticket_detail = await ticket_service.get_ticket(ticket_id)
    assert ticket_detail is not None
    assert ticket_detail["id"] == ticket_id
    assert len(ticket_detail["criteria"]) == 2

    # 3. Spawn Worktree for Ticket
    repo_path = await repo_mgr.get_repo_path(project_id)
    wt_manager = GitWorktreeManager()
    wt = wt_manager.create_worktree(
        str(repo_path),
        name=ticket_id,
        branch_name=f"mesh/{ticket_id}"
    )
    assert Path(wt["path"]).exists()

    # 4. Record Change Ledger Event linked to ticket
    event = await ledger_service.record_event(
        project_id=project_id,
        actor_id="Agent-Crystal",
        event_type="edit",
        summary="Added matrix functions to src/calculator.py",
        ticket_id=ticket_id,
        files_changed=["src/calculator.py"],
        diff_stats={"insertions": 15, "deletions": 0, "files": 1},
        verification_status="passed",
    )
    assert event["id"] is not None
    assert event["ticket_id"] == ticket_id

    # 5. Retrieve Ledger Events & Stats
    events = await ledger_service.list_events(project_id, ticket_id=ticket_id)
    assert len(events) >= 1
    assert events[0]["actor_id"] == "Agent-Crystal"

    stats = await ledger_service.get_project_stats(project_id)
    assert stats["total_changes"] >= 1
    assert stats["verified_changes"] >= 1

    # 6. Update Acceptance Criteria Status
    first_crit_id = ticket_detail["criteria"][0]["id"]
    crit_update = await ticket_service.update_criterion(
        criterion_id=first_crit_id,
        is_satisfied=True,
        evidence_event_id=event["id"]
    )
    assert crit_update is True


@pytest.mark.anyio
async def test_prompt_styles_and_configurations():
    """Test model support, system prompt merging, and configurations."""
    # 1. System prompt merging
    base = "You are a coding agent."
    custom = "Always format responses in bullet points."
    merged = merge_system_prompt(base, custom)
    assert base in merged
    assert custom in merged

    # 2. Model resolution
    assert resolve_model(None) == "llama-3.3-70b-versatile"
    assert resolve_model("openai/gpt-oss-120b") == "openai/gpt-oss-120b"
    assert resolve_model("gemini-2.5-flash") == "gemini-2.5-flash"

    # 3. Tool support checking
    assert supports_tools("llama-3.3-70b-versatile") is True
    assert supports_tools("openai/gpt-oss-120b") is True
    assert supports_tools("gemini-2.5-flash") is True
    assert supports_tools("whisper-large-v3") is False


@pytest.mark.anyio
async def test_delete_indexed_data_and_purge_history(sample_repository):
    """Test that deleteRepository / deleteProject cleanly wipes indexed data, tickets, sessions, and files."""
    await init_db()
    repo_mgr = RepositoryManager()
    repo_data = await repo_mgr.open_local_repository(sample_repository)
    project_id = repo_data["id"]

    # 1. Add session, message, ticket, and ledger event
    db = await get_db()
    session = ChatSession(id=f"sess-{project_id}", project_id=project_id, title="Test Chat")
    db.add(session)
    msg = ChatMessage(session_id=session.id, role="user", content="Hello test")
    db.add(msg)
    tkt = Ticket(id=f"tkt-{project_id}", project_id=project_id, title="Sample Ticket")
    db.add(tkt)
    crit = TicketAcceptanceCriteria(id=f"crit-{project_id}", ticket_id=tkt.id, description="Pass test")
    db.add(crit)
    ledger = ChangeLedgerEvent(id=f"ledg-{project_id}", project_id=project_id, actor_id="agent", event_type="edit", summary="test")
    db.add(ledger)
    await db.commit()
    await db.close()

    # Set active project setting
    await SessionService.set_user_setting("active_project_id", project_id)

    # Verify rows exist before cleanup
    db = await get_db()
    assert (await db.get(Repository, project_id)) is not None
    assert (await db.get(ChatSession, session.id)) is not None
    assert (await db.get(Ticket, tkt.id)) is not None
    await db.close()

    # 2. Execute cleanup_sql for this repository
    res = await repo_mgr.cleanup_sql(project_id)
    assert res["repositories"] == 1
    assert res["sessions"] >= 1
    assert res["messages"] >= 1
    assert res["tickets"] >= 1
    assert res["ticket_criteria"] >= 1
    assert res["ledger_events"] >= 1
    assert res.get("active_project_reset") is True

    # 3. Verify database is completely free of this project's records
    db = await get_db()
    assert (await db.get(Repository, project_id)) is None
    assert (await db.get(ChatSession, session.id)) is None
    assert (await db.get(Ticket, tkt.id)) is None
    assert (await db.get(TicketAcceptanceCriteria, crit.id)) is None
    assert (await db.get(ChangeLedgerEvent, ledger.id)) is None
    assert (await db.get(UserSetting, "active_project_id")) is None
    await db.close()
