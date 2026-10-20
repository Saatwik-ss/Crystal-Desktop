import os
import subprocess
import tempfile
import pytest
from pathlib import Path
from database.db import init_db, get_db
from database.models import Repository
from services.git.worktree_manager import GitWorktreeManager
from services.ledger_service import ledger_service
from services.ticket_service import ticket_service

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
def temp_project():
    """Create a temporary git repository registered as a Repository in DB."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_path = Path(tmp_dir) / "mesh_repo"
        repo_path.mkdir(parents=True, exist_ok=True)

        # git init
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Saatwik"], cwd=str(repo_path), check=True)
        subprocess.run(["git", "config", "user.email", "saatwik@crystal.local"], cwd=str(repo_path), check=True)

        readme = repo_path / "README.md"
        readme.write_text("# CrystalMesh Project\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True)

        yield str(repo_path)

@pytest.mark.anyio
async def test_ticket_ledger_and_worktree_pipeline(temp_project):
    await init_db()

    project_id = "test-mesh-proj-01"

    # Register in DB
    db = await get_db()
    try:
        repo = Repository(id=project_id, name="MeshRepo", path=temp_project)
        db.add(repo)
        await db.commit()
    finally:
        await db.close()

    try:
        # 1. Create Ticket with acceptance criteria
        ticket = await ticket_service.create_ticket(
            project_id=project_id,
            title="Fix API 500 on token expiration",
            description="Reproduce, patch, and verify token handling in middleware",
            priority="high",
            assignee_type="agent",
            assignee_id="Agent-01",
            criteria=[
                {
                    "description": "Reproduce token expiration failure",
                    "criterion_type": "repro_check",
                },
                {
                    "description": "Pass regression suite",
                    "criterion_type": "automated_test",
                    "verification_command": "pytest tests/test_auth.py",
                }
            ]
        )
        assert ticket["id"].startswith("tkt_")
        assert len(ticket["criteria"]) == 2
        assert ticket["status"] == "todo"

        # 2. Activate isolated Git worktree for ticket
        wt_mgr = GitWorktreeManager()
        wt = wt_mgr.create_worktree(temp_project, name=ticket["id"])
        assert wt["name"] == ticket["id"]
        assert wt["branch"] == f"mesh/{ticket['id']}"
        wt_path = Path(wt["path"])
        assert wt_path.exists()

        # Update ticket active worktree
        updated_ticket = await ticket_service.update_ticket(ticket["id"], {
            "active_worktree": wt["path"],
            "active_branch": wt["branch"],
            "status": "in_progress",
        })
        assert updated_ticket["status"] == "in_progress"
        assert updated_ticket["active_branch"] == wt["branch"]

        # 3. Simulate Agent editing in worktree
        auth_file = wt_path / "auth.py"
        auth_file.write_text("def verify_token(token):\n    return True\n", encoding="utf-8")

        diff = wt_mgr.get_diff(str(wt_path))
        assert diff["additions"] == 2
        assert diff["files_count"] == 1

        # 4. Record event in Change Ledger
        event = await ledger_service.record_event(
            project_id=project_id,
            ticket_id=ticket["id"],
            actor_type="agent",
            actor_id="Agent-01",
            branch=wt["branch"],
            worktree_path=str(wt_path),
            event_type="edit",
            summary="Implemented token expiration fallback in auth.py",
            files_changed=["auth.py"],
            diff_stats={"additions": diff["additions"], "deletions": diff["deletions"]},
            diff_patch=diff["diff_patch"],
            verification_status="passed",
            verification_details={"exit_code": 0, "tests_passed": 4},
        )
        assert event["id"].startswith("evt_")
        assert event["verification_status"] == "passed"

        # 5. Commit in worktree
        commit_res = wt_mgr.commit(str(wt_path), "Fix: token expiration fallback", author_name="Agent-01")
        assert commit_res["success"] is True

        # 6. Verify Acceptance Criteria
        crit_id = ticket["criteria"][1]["id"]
        success = await ticket_service.update_criterion(crit_id, is_satisfied=True, evidence_event_id=event["id"])
        assert success is True

        # 7. Check Project Stats
        stats = await ledger_service.get_project_stats(project_id)
        assert stats["total_changes"] >= 1
        assert stats["verified_changes"] >= 1
        assert stats["open_tickets"] >= 1

        # 8. List Events with filters
        events = await ledger_service.list_events(project_id, ticket_id=ticket["id"])
        assert len(events) >= 1
        assert events[0]["actor_id"] == "Agent-01"

    finally:
        # Cleanup
        db = await get_db()
        try:
            from database.models import ChangeLedgerEvent, TicketAcceptanceCriteria, Ticket
            from sqlalchemy import delete
            await db.execute(delete(ChangeLedgerEvent).where(ChangeLedgerEvent.project_id == project_id))
            await db.execute(delete(TicketAcceptanceCriteria).where(TicketAcceptanceCriteria.ticket_id == ticket["id"]))
            await db.execute(delete(Ticket).where(Ticket.project_id == project_id))
            await db.execute(delete(Repository).where(Repository.id == project_id))
            await db.commit()
        finally:
            await db.close()
