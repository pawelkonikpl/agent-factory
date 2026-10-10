from fastapi import APIRouter, status

from app.dependencies import NoteServiceDep, PrincipalDep
from app.repositories.note_repository import Note
from app.schemas import NoteCreate, NoteResponse

router = APIRouter(prefix="/notes", tags=["notes"])


@router.get("", response_model=list[NoteResponse])
async def list_notes(principal: PrincipalDep, service: NoteServiceDep) -> list[Note]:
    return await service.list_notes(principal)


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate, principal: PrincipalDep, service: NoteServiceDep
) -> Note:
    return await service.create_note(principal, payload.text)
