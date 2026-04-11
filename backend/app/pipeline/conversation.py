import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class Session:
    session_id: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConversationManager:
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def _get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        session = self._get_or_create(session_id)
        session.messages.append({"role": role, "content": content})

    def get_history(self, session_id: str, max_turns: int = 10) -> List[Dict[str, str]]:
        session = self._get_or_create(session_id)
        return session.messages[-(max_turns * 2):]

    def clear(self, session_id: str) -> None:
        if session_id in self._sessions:
            del self._sessions[session_id]

    def format_history(self, session_id: str, max_turns: int = 5) -> str:
        """Format recent conversation history as a string for prompt inclusion."""
        history = self.get_history(session_id, max_turns)
        if not history:
            return ""
        lines = []
        for msg in history:
            role = msg["role"].capitalize()
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
