"""In-memory notes. A real API would use a database; the owner filter would stay."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Note:
    id: str
    owner: str
    text: str
    created_at: datetime


class NoteRepository:
    def __init__(self) -> None:
        self._notes: defaultdict[str, list[Note]] = defaultdict(list)

    async def list_for_owner(self, owner: str) -> list[Note]:
        return list(self._notes[owner])

    async def add(self, note: Note) -> None:
        self._notes[note.owner].append(note)
