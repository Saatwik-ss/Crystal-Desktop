import uuid
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy import select, desc
from database.db import get_db
from database.models import Ticket, TicketAcceptanceCriteria

logger = logging.getLogger(__name__)

class TicketService:
    """
    Manages in-editor tickets, ownership, acceptance criteria,
    and automatic status transitions driven by ledger evidence.
    """

    async def create_ticket(
        self,
        project_id: str,
        title: str,
        description: str = "",
        priority: str = "medium",
        assignee_type: str = "unassigned",
        assignee_id: Optional[str] = None,
        criteria: Optional[List[Dict[str, Any]]] = None,
        github_issue_number: Optional[int] = None,
        github_issue_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        ticket_id = f"tkt_{uuid.uuid4().hex[:8]}"
        created_at = datetime.utcnow()

        db = await get_db()
        try:
            ticket = Ticket(
                id=ticket_id,
                project_id=project_id,
                title=title,
                description=description,
                status="todo",
                priority=priority,
                assignee_type=assignee_type,
                assignee_id=assignee_id,
                github_issue_number=github_issue_number,
                github_issue_url=github_issue_url,
                created_at=created_at,
                updated_at=created_at,
            )
            db.add(ticket)

            criteria_objs = []
            if criteria:
                for c in criteria:
                    crit_id = f"crt_{uuid.uuid4().hex[:8]}"
                    crit_obj = TicketAcceptanceCriteria(
                        id=crit_id,
                        ticket_id=ticket_id,
                        description=c.get("description", ""),
                        criterion_type=c.get("criterion_type", "automated_test"),
                        verification_command=c.get("verification_command"),
                        is_satisfied=False,
                        updated_at=created_at,
                    )
                    db.add(crit_obj)
                    criteria_objs.append({
                        "id": crit_id,
                        "description": crit_obj.description,
                        "criterion_type": crit_obj.criterion_type,
                        "verification_command": crit_obj.verification_command,
                        "is_satisfied": False,
                    })

            await db.commit()
            logger.info(f"[TicketService] Created ticket {ticket_id}: {title}")

            return {
                "id": ticket_id,
                "project_id": project_id,
                "title": title,
                "description": description,
                "status": "todo",
                "priority": priority,
                "assignee_type": assignee_type,
                "assignee_id": assignee_id,
                "github_issue_number": github_issue_number,
                "github_issue_url": github_issue_url,
                "criteria": criteria_objs,
                "created_at": created_at.isoformat(),
                "updated_at": created_at.isoformat(),
            }
        finally:
            await db.close()

    async def list_tickets(
        self,
        project_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        db = await get_db()
        try:
            stmt = select(Ticket).where(Ticket.project_id == project_id)
            if status:
                stmt = stmt.where(Ticket.status == status)
            stmt = stmt.order_by(desc(Ticket.updated_at))
            res = await db.execute(stmt)
            tickets = res.scalars().all()

            out = []
            for t in tickets:
                crit_stmt = select(TicketAcceptanceCriteria).where(TicketAcceptanceCriteria.ticket_id == t.id)
                crit_res = await db.execute(crit_stmt)
                criteria = [
                    {
                        "id": c.id,
                        "description": c.description,
                        "criterion_type": c.criterion_type,
                        "verification_command": c.verification_command,
                        "is_satisfied": c.is_satisfied,
                        "evidence_event_id": c.evidence_event_id,
                    }
                    for c in crit_res.scalars().all()
                ]

                out.append({
                    "id": t.id,
                    "project_id": t.project_id,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "priority": t.priority,
                    "assignee_type": t.assignee_type,
                    "assignee_id": t.assignee_id,
                    "reviewer_id": t.reviewer_id,
                    "active_branch": t.active_branch,
                    "active_worktree": t.active_worktree,
                    "github_issue_number": t.github_issue_number,
                    "github_issue_url": t.github_issue_url,
                    "criteria": criteria,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None,
                })
            return out
        finally:
            await db.close()

    async def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        db = await get_db()
        try:
            ticket = await db.get(Ticket, ticket_id)
            if not ticket:
                return None

            crit_stmt = select(TicketAcceptanceCriteria).where(TicketAcceptanceCriteria.ticket_id == ticket.id)
            crit_res = await db.execute(crit_stmt)
            criteria = [
                {
                    "id": c.id,
                    "description": c.description,
                    "criterion_type": c.criterion_type,
                    "verification_command": c.verification_command,
                    "is_satisfied": c.is_satisfied,
                    "evidence_event_id": c.evidence_event_id,
                }
                for c in crit_res.scalars().all()
            ]

            return {
                "id": ticket.id,
                "project_id": ticket.project_id,
                "title": ticket.title,
                "description": ticket.description,
                "status": ticket.status,
                "priority": ticket.priority,
                "assignee_type": ticket.assignee_type,
                "assignee_id": ticket.assignee_id,
                "reviewer_id": ticket.reviewer_id,
                "active_branch": ticket.active_branch,
                "active_worktree": ticket.active_worktree,
                "github_issue_number": ticket.github_issue_number,
                "github_issue_url": ticket.github_issue_url,
                "criteria": criteria,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            }
        finally:
            await db.close()

    async def update_ticket(self, ticket_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        db = await get_db()
        try:
            ticket = await db.get(Ticket, ticket_id)
            if not ticket:
                return None

            for field in [
                "title", "description", "status", "priority",
                "assignee_type", "assignee_id", "reviewer_id",
                "active_branch", "active_worktree", "github_issue_number", "github_issue_url"
            ]:
                if field in updates:
                    setattr(ticket, field, updates[field])

            ticket.updated_at = datetime.utcnow()
            await db.commit()
            return await self.get_ticket(ticket_id)
        finally:
            await db.close()

    async def add_criterion(
        self,
        ticket_id: str,
        description: str,
        criterion_type: str = "automated_test",
        verification_command: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = await get_db()
        try:
            crit_id = f"crt_{uuid.uuid4().hex[:8]}"
            crit = TicketAcceptanceCriteria(
                id=crit_id,
                ticket_id=ticket_id,
                description=description,
                criterion_type=criterion_type,
                verification_command=verification_command,
                is_satisfied=False,
                updated_at=datetime.utcnow(),
            )
            db.add(crit)
            await db.commit()
            return {
                "id": crit_id,
                "ticket_id": ticket_id,
                "description": description,
                "criterion_type": criterion_type,
                "verification_command": verification_command,
                "is_satisfied": False,
            }
        finally:
            await db.close()

    async def update_criterion(
        self,
        criterion_id: str,
        is_satisfied: bool,
        evidence_event_id: Optional[str] = None,
    ) -> bool:
        db = await get_db()
        try:
            crit = await db.get(TicketAcceptanceCriteria, criterion_id)
            if not crit:
                return False
            crit.is_satisfied = is_satisfied
            if evidence_event_id:
                crit.evidence_event_id = evidence_event_id
            crit.updated_at = datetime.utcnow()
            await db.commit()
            return True
        finally:
            await db.close()

ticket_service = TicketService()
