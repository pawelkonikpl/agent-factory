"""Wiring of services and FastAPI dependency providers."""

from dataclasses import dataclass
from typing import Annotated, cast

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clock import Clock
from app.config import Settings
from app.errors import InvalidTokenError
from app.repositories.note_repository import NoteRepository
from app.services.note_service import NoteService
from app.services.token_verifier import AccessTokenVerifier, Principal


@dataclass(frozen=True)
class Container:
    verifier: AccessTokenVerifier
    notes: NoteService


def build_container(settings: Settings, http: httpx.AsyncClient, clock: Clock) -> Container:
    return Container(
        verifier=AccessTokenVerifier(settings, http, clock),
        notes=NoteService(NoteRepository()),
    )


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    container: ContainerDep,
) -> Principal:
    if credentials is None:
        raise InvalidTokenError("Missing bearer token", token_present=False)
    return await container.verifier.verify(credentials.credentials)


def get_note_service(container: ContainerDep) -> NoteService:
    return container.notes


PrincipalDep = Annotated[Principal, Depends(get_principal)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
