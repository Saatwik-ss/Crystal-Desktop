import uuid
import logging
from typing import Dict, Optional, List
from services.terminal.pty_session import PTYSession

logger = logging.getLogger(__name__)

class TerminalManager:
    """
    Manages multiple interactive terminal sessions and WebSocket streams.
    """

    def __init__(self):
        self.sessions: Dict[str, PTYSession] = {}

    def create_session(
        self,
        session_id: Optional[str] = None,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
        rows: int = 24,
        cols: int = 80,
    ) -> PTYSession:
        sid = session_id or str(uuid.uuid4())[:8]
        if sid in self.sessions:
            self.sessions[sid].kill()

        session = PTYSession(
            session_id=sid,
            cwd=cwd,
            shell=shell,
            rows=rows,
            cols=cols,
        )
        self.sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        return self.sessions.get(session_id)

    def list_sessions(self) -> List[Dict[str, str]]:
        return [
            {
                "id": sid,
                "is_alive": session.is_alive(),
                "cwd": session.cwd,
            }
            for sid, session in self.sessions.items()
        ]

    def close_session(self, session_id: str):
        session = self.sessions.pop(session_id, None)
        if session:
            session.kill()

    def close_all(self):
        for sid, session in list(self.sessions.items()):
            try:
                session.kill()
            except Exception:
                pass
        self.sessions.clear()
