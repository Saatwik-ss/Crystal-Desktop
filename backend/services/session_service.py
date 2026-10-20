import uuid
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select, delete, func, desc
from database.db import get_db
from database.models import ChatSession, ChatMessage, UserSetting, Repository

logger = logging.getLogger(__name__)


def generate_title_from_text(text: str, max_words: int = 6) -> str:
    """Generate a clean, concise chat title from the first user prompt."""
    if not text:
        return "New Chat"
    clean = text.strip().replace("\n", " ")
    # Strip markdown / backticks
    clean = clean.replace("`", "").replace("#", "").replace("*", "")
    words = clean.split()
    if not words:
        return "New Chat"
    title = " ".join(words[:max_words])
    if len(title) > 42:
        title = title[:42].rstrip() + "..."
    # Capitalize first letter
    return title[:1].upper() + title[1:]


class SessionService:
    """Manages persistent chat sessions, message histories, and user settings."""

    @staticmethod
    async def get_or_create_session(
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        title: Optional[str] = None,
        model: Optional[str] = None,
    ) -> ChatSession:
        db = await get_db()
        try:
            if session_id:
                session = await db.get(ChatSession, session_id)
                if session:
                    if model and session.model != model:
                        session.model = model
                        session.updated_at = datetime.utcnow()
                        await db.commit()
                    return session

            new_id = session_id or str(uuid.uuid4())
            session = ChatSession(
                id=new_id,
                project_id=project_id,
                title=title or "New Chat",
                model=model,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(session)
            await db.commit()
            return session
        finally:
            await db.close()

    @staticmethod
    async def list_project_sessions(project_id: Optional[str]) -> List[Dict[str, Any]]:
        db = await get_db()
        try:
            stmt = (
                select(ChatSession)
                .where(ChatSession.project_id == project_id)
                .order_by(desc(ChatSession.updated_at))
            )
            result = await db.execute(stmt)
            sessions = result.scalars().all()

            out = []
            for s in sessions:
                # Get last message snippet
                last_msg_stmt = (
                    select(ChatMessage.content)
                    .where(ChatMessage.session_id == s.id)
                    .order_by(desc(ChatMessage.timestamp))
                    .limit(1)
                )
                last_msg_res = await db.execute(last_msg_stmt)
                last_msg = last_msg_res.scalar_one_or_none() or ""
                snippet = (last_msg[:60] + "...") if len(last_msg) > 60 else last_msg

                out.append({
                    "id": s.id,
                    "project_id": s.project_id,
                    "title": s.title,
                    "model": s.model,
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                    "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                    "last_message": snippet,
                })
            return out
        finally:
            await db.close()

    @staticmethod
    async def get_session_messages(session_id: str) -> Dict[str, Any]:
        db = await get_db()
        try:
            session = await db.get(ChatSession, session_id)
            if not session:
                return {"session": None, "messages": []}

            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.timestamp.asc(), ChatMessage.id.asc())
            )
            res = await db.execute(stmt)
            rows = res.scalars().all()

            messages = []
            for r in rows:
                item: Dict[str, Any] = {
                    "id": str(r.id),
                    "role": r.role,
                    "content": r.content,
                    "type": r.type,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                }
                if r.thought:
                    item["thought"] = r.thought
                if r.plan:
                    item["plan"] = r.plan
                if r.tool_calls:
                    item["tool_calls"] = r.tool_calls
                if r.terminal_logs:
                    item["terminal_logs"] = r.terminal_logs
                if r.proposed_edits:
                    item["proposed_edits"] = r.proposed_edits
                messages.append(item)

            return {
                "session": {
                    "id": session.id,
                    "project_id": session.project_id,
                    "title": session.title,
                    "model": session.model,
                    "created_at": session.created_at.isoformat() if session.created_at else "",
                    "updated_at": session.updated_at.isoformat() if session.updated_at else "",
                },
                "messages": messages,
            }
        finally:
            await db.close()

    @staticmethod
    async def add_chat_message(
        session_id: str,
        role: str,
        content: str,
        thought: Optional[str] = None,
        plan: Optional[Any] = None,
        tool_calls: Optional[Any] = None,
        terminal_logs: Optional[Any] = None,
        proposed_edits: Optional[Any] = None,
        msg_type: str = "message",
    ) -> ChatMessage:
        db = await get_db()
        try:
            msg = ChatMessage(
                session_id=session_id,
                role=role,
                content=content or "",
                thought=thought,
                plan=plan,
                tool_calls=tool_calls,
                terminal_logs=terminal_logs,
                proposed_edits=proposed_edits,
                type=msg_type,
                timestamp=datetime.utcnow(),
            )
            db.add(msg)

            # Touch session updated_at
            session = await db.get(ChatSession, session_id)
            if session:
                session.updated_at = datetime.utcnow()

            await db.commit()
            return msg
        finally:
            await db.close()

    @staticmethod
    async def update_session_title(session_id: str, title: str) -> None:
        db = await get_db()
        try:
            session = await db.get(ChatSession, session_id)
            if session:
                session.title = title
                session.updated_at = datetime.utcnow()
                await db.commit()
        finally:
            await db.close()

    @staticmethod
    async def update_session_model(session_id: str, model: str) -> None:
        db = await get_db()
        try:
            session = await db.get(ChatSession, session_id)
            if session:
                session.model = model
                session.updated_at = datetime.utcnow()
                await db.commit()
        finally:
            await db.close()

    @staticmethod
    async def delete_session(session_id: str) -> bool:
        db = await get_db()
        try:
            # Delete messages first
            await db.execute(delete(ChatMessage).where(ChatMessage.session_id == session_id))
            # Delete session
            res = await db.execute(delete(ChatSession).where(ChatSession.id == session_id))
            await db.commit()
            return res.rowcount > 0
        finally:
            await db.close()

    @staticmethod
    async def get_recent_history_for_planner(session_id: str, limit: int = 10) -> List[Dict[str, str]]:
        """Fetch clean recent conversation history for feeding LLM context."""
        db = await get_db()
        try:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(desc(ChatMessage.timestamp))
                .limit(limit)
            )
            res = await db.execute(stmt)
            rows = list(reversed(res.scalars().all()))

            history = []
            for r in rows:
                if r.role in ("user", "assistant") and r.content:
                    history.append({"role": r.role, "content": r.content})
            return history
        finally:
            await db.close()

    @staticmethod
    async def get_user_setting(key: str, default: Optional[str] = None) -> Optional[str]:
        db = await get_db()
        try:
            row = await db.get(UserSetting, key)
            if row:
                return row.value
            return default
        finally:
            await db.close()

    @staticmethod
    async def set_user_setting(key: str, value: str) -> None:
        db = await get_db()
        try:
            row = await db.get(UserSetting, key)
            if row:
                row.value = value
                row.updated_at = datetime.utcnow()
            else:
                db.add(UserSetting(key=key, value=value, updated_at=datetime.utcnow()))
            await db.commit()
        finally:
            await db.close()
