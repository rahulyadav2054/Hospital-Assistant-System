"""In-memory conversation history, keyed by (user_id, session_id) so one user can never read another's history."""
import threading
from collections import defaultdict

MAX_MESSAGES = 8

_lock = threading.Lock()
_store: dict[tuple[int, str], list[dict]] = defaultdict(list)


def get(user_id: int, session_id: str) -> list[dict]:
    with _lock:
        return list(_store[(user_id, session_id)][-MAX_MESSAGES:])


def append(user_id: int, session_id: str, question: str, answer: str) -> None:
    with _lock:
        h = _store[(user_id, session_id)]
        h.append({"role": "user", "content": question})
        h.append({"role": "assistant", "content": answer})
        del h[:-MAX_MESSAGES]


def clear() -> None:
    with _lock:
        _store.clear()
