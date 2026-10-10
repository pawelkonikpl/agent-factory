"""Notes belong to the user in the access token's "sub" claim."""

import uuid
from datetime import UTC, datetime

from app.repositories.note_repository import Note, NoteRepository
from app.services.token_verifier import Principal


class NoteService:
    def __init__(self, notes: NoteRepository) -> None:
        self._notes = notes

    async def list_notes(self, principal: Principal) -> list[Note]:
        notes = await self._notes.list_for_owner(principal.subject)
        return sorted(notes, key=lambda note: note.created_at, reverse=True)

    async def create_note(self, principal: Principal, text: str) -> Note:
        note = Note(
            id=str(uuid.uuid4()),
            owner=principal.subject,
            text=text,
            created_at=datetime.now(UTC),
        )
        await self._notes.add(note)
        return note
