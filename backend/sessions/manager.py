import uuid

from config.settings import settings
from exceptions import SessionNotFoundError
from schemas.chat import ChatMessage


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, list[ChatMessage]] = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []
        return session_id

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def _require_session(self, session_id: str) -> list[ChatMessage]:
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session '{session_id}' does not exist.")
        return self._sessions[session_id]

    def get_history(self, session_id: str) -> list[ChatMessage]:
        return self._require_session(session_id)

    def add_user_message(self, session_id: str, content: str) -> None:
        history = self._require_session(session_id)
        history.append(ChatMessage(role="user", content=content))
        self._trim(session_id)

    def add_assistant_message(self, session_id: str, content: str) -> None:
        history = self._require_session(session_id)
        history.append(ChatMessage(role="assistant", content=content))
        self._trim(session_id)

    def clear_session(self, session_id: str) -> None:
        self._require_session(session_id)
        self._sessions[session_id] = []

    def _trim(self, session_id: str) -> None:
        limit = settings.max_history_messages
        if len(self._sessions[session_id]) > limit:
            self._sessions[session_id] = self._sessions[session_id][-limit:]


session_manager = SessionManager()
