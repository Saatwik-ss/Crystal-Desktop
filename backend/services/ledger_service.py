import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy import select, desc, func
from database.db import get_db
from database.models import ChangeLedgerEvent, Ticket

logger = logging.getLogger(__name__)

class LedgerService:
    """
    Manages the append-only Change Ledger. Every meaningful action, edit,
    test verification, and review is recorded and queryable.
    """

    async def record_event(
        self,
        project_id: str,
        summary: str,
        event_type: str = "edit",
        actor_id: str = "Crystal Agent",
        actor_type: str = "agent",
        ticket_id: Optional[str] = None,
        branch: Optional[str] = None,
        worktree_path: Optional[str] = None,
        files_changed: Optional[List[str]] = None,
        diff_stats: Optional[Dict[str, Any]] = None,
        diff_patch: Optional[str] = None,
        verification_status: str = "not_run",
        verification_details: Optional[Dict[str, Any]] = None,
        causal_metadata: Optional[Dict[str, Any]] = None,
        github_references: Optional[Dict[str, Any]] = None,
        cost_metrics: Optional[Dict[str, Any]] = None,
        parent_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an immutable engineering event into the change ledger."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow()

        db = await get_db()
        try:
            event = ChangeLedgerEvent(
                id=event_id,
                project_id=project_id,
                ticket_id=ticket_id,
                actor_type=actor_type,
                actor_id=actor_id,
                branch=branch,
                worktree_path=worktree_path,
                event_type=event_type,
                summary=summary,
                files_changed=files_changed or [],
                diff_stats=diff_stats or {},
                diff_patch=diff_patch,
                verification_status=verification_status,
                verification_details=verification_details or {},
                causal_metadata=causal_metadata or {},
                github_references=github_references or {},
                cost_metrics=cost_metrics or {},
                parent_event_id=parent_event_id,
                created_at=created_at,
            )
            db.add(event)
            await db.commit()

            logger.info(f"[ChangeLedger] Recorded {event_type} event {event_id} ({summary})")
            return {
                "id": event_id,
                "project_id": project_id,
                "ticket_id": ticket_id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "branch": branch,
                "worktree_path": worktree_path,
                "event_type": event_type,
                "summary": summary,
                "files_changed": files_changed or [],
                "diff_stats": diff_stats or {},
                "diff_patch": diff_patch,
                "verification_status": verification_status,
                "verification_details": verification_details or {},
                "causal_metadata": causal_metadata or {},
                "github_references": github_references or {},
                "cost_metrics": cost_metrics or {},
                "parent_event_id": parent_event_id,
                "created_at": created_at.isoformat(),
            }
        finally:
            await db.close()

    async def list_events(
        self,
        project_id: str,
        ticket_id: Optional[str] = None,
        event_type: Optional[str] = None,
        verification_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List change ledger events with optional filters."""
        db = await get_db()
        try:
            stmt = select(ChangeLedgerEvent).where(ChangeLedgerEvent.project_id == project_id)
            if ticket_id:
                stmt = stmt.where(ChangeLedgerEvent.ticket_id == ticket_id)
            if event_type:
                stmt = stmt.where(ChangeLedgerEvent.event_type == event_type)
            if verification_status:
                stmt = stmt.where(ChangeLedgerEvent.verification_status == verification_status)

            stmt = stmt.order_by(desc(ChangeLedgerEvent.created_at)).offset(offset).limit(limit)
            res = await db.execute(stmt)
            events = res.scalars().all()

            return [
                {
                    "id": e.id,
                    "project_id": e.project_id,
                    "ticket_id": e.ticket_id,
                    "actor_type": e.actor_type,
                    "actor_id": e.actor_id,
                    "branch": e.branch,
                    "worktree_path": e.worktree_path,
                    "event_type": e.event_type,
                    "summary": e.summary,
                    "files_changed": e.files_changed or [],
                    "diff_stats": e.diff_stats or {},
                    "diff_patch": e.diff_patch,
                    "verification_status": e.verification_status,
                    "verification_details": e.verification_details or {},
                    "causal_metadata": e.causal_metadata or {},
                    "github_references": e.github_references or {},
                    "cost_metrics": e.cost_metrics or {},
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
        finally:
            await db.close()

    async def get_project_stats(self, project_id: str) -> Dict[str, Any]:
        """Aggregate summary metrics for the project dashboard."""
        db = await get_db()
        try:
            # 1. Total changes count
            stmt_total = select(func.count(ChangeLedgerEvent.id)).where(ChangeLedgerEvent.project_id == project_id)
            res_total = await db.execute(stmt_total)
            total_changes = res_total.scalar() or 0

            # 2. Verified count
            stmt_verified = (
                select(func.count(ChangeLedgerEvent.id))
                .where(ChangeLedgerEvent.project_id == project_id)
                .where(ChangeLedgerEvent.verification_status == "passed")
            )
            res_verified = await db.execute(stmt_verified)
            verified_changes = res_verified.scalar() or 0

            # 3. Open tickets count
            stmt_tickets = (
                select(func.count(Ticket.id))
                .where(Ticket.project_id == project_id)
                .where(Ticket.status.in_(["todo", "in_progress", "in_verification", "in_review"]))
            )
            res_tickets = await db.execute(stmt_tickets)
            open_tickets = res_tickets.scalar() or 0

            return {
                "total_changes": total_changes,
                "verified_changes": verified_changes,
                "open_tickets": open_tickets,
            }
        finally:
            await db.close()

ledger_service = LedgerService()
