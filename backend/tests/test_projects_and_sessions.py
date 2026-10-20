import pytest
import asyncio
import uuid
from pathlib import Path
from database.db import init_db, get_db
from services.session_service import SessionService, generate_title_from_text
from services.llm_config import get_persisted_model, save_persisted_model, resolve_model
from database.models import Repository

__test__ = True


def test_session_lifecycle_and_messages(tmp_path):
    async def _run():
        await init_db()

        # 1. Create a dummy project in DB with unique ID
        db = await get_db()
        project_id = f"test-proj-{uuid.uuid4()}"
        proj = Repository(
            id=project_id,
            name="TestProject",
            path=str(tmp_path),
        )
        db.add(proj)
        await db.commit()
        await db.close()

        # 2. Create multiple sessions for this project
        s1 = await SessionService.get_or_create_session(
            project_id=project_id,
            title="Debugging API Unauthorized Error",
            model="llama-3.3-70b-versatile"
        )
        assert s1.id is not None
        assert s1.title == "Debugging API Unauthorized Error"

        s2 = await SessionService.get_or_create_session(
            project_id=project_id,
            title="Comprehensive Exam Study Guide",
            model="gemini-2.5-flash"
        )
        assert s2.id is not None

        # 3. List sessions for this project
        sessions = await SessionService.list_project_sessions(project_id)
        assert len(sessions) >= 2
        titles = [s["title"] for s in sessions]
        assert "Debugging API Unauthorized Error" in titles
        assert "Comprehensive Exam Study Guide" in titles

        # 4. Add messages to session 1
        await SessionService.add_chat_message(
            session_id=s1.id,
            role="user",
            content="How do I fix 401 Unauthorized?",
            msg_type="message"
        )
        await SessionService.add_chat_message(
            session_id=s1.id,
            role="assistant",
            content="You need to pass the Bearer token in the Authorization header.",
            msg_type="message"
        )

        # 5. Retrieve session 1 messages
        data = await SessionService.get_session_messages(s1.id)
        assert data["session"]["id"] == s1.id
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

        # 6. Test planner context history retrieval
        history = await SessionService.get_recent_history_for_planner(s1.id, limit=5)
        assert len(history) == 2
        assert history[0]["content"] == "How do I fix 401 Unauthorized?"

        # 7. Test delete session
        deleted = await SessionService.delete_session(s2.id)
        assert deleted is True
        remaining = await SessionService.list_project_sessions(project_id)
        assert s2.id not in [s["id"] for s in remaining]

    asyncio.run(_run())


def test_title_generation():
    title = generate_title_from_text("Please fix the bug in api_client.py where 401 is thrown")
    assert "Please" in title
    assert len(title) <= 45

    assert generate_title_from_text("") == "New Chat"


def test_model_persistence():
    try:
        save_persisted_model("gemini-2.5-flash")
        assert get_persisted_model() == "gemini-2.5-flash"
        assert resolve_model(None) == "gemini-2.5-flash"

        # Save another model
        save_persisted_model("openai/gpt-oss-120b")
        assert get_persisted_model() == "openai/gpt-oss-120b"
        assert resolve_model("") == "openai/gpt-oss-120b"
    finally:
        # Reset back to default so other test suites aren't affected
        save_persisted_model("llama-3.3-70b-versatile")
