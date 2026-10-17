"""Wiring of services and FastAPI dependency providers."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated, cast

import httpx
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.config import Settings
from app.errors import InvalidTokenError
from app.repositories.campaign_repository import CampaignRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.client_repository import ClientRepository
from app.repositories.config_repository import ConfigRepository
from app.repositories.email_repository import EmailRepository
from app.repositories.note_repository import NoteRepository
from app.services.campaign_service import CampaignService
from app.services.category_service import CategoryService
from app.services.client_service import ClientService
from app.services.email_service import EmailService
from app.services.encryption import EncryptionService
from app.services.note_service import NoteService
from app.services.smtp_config_service import SmtpConfigService
from app.services.smtp_sender import EmailSenderFactory
from app.services.token_verifier import AccessTokenVerifier, Principal


@dataclass(frozen=True)
class Container:
    verifier: AccessTokenVerifier
    notes: NoteService
    sessions: async_sessionmaker[AsyncSession]
    encryption: EncryptionService
    email_sender_factory: EmailSenderFactory


def build_container(
    settings: Settings,
    http: httpx.AsyncClient,
    clock: Clock,
    sessions: async_sessionmaker[AsyncSession],
    email_sender_factory: EmailSenderFactory,
) -> Container:
    return Container(
        verifier=AccessTokenVerifier(settings, http, clock),
        notes=NoteService(NoteRepository()),
        sessions=sessions,
        encryption=EncryptionService(settings.encryption_key.get_secret_value()),
        email_sender_factory=email_sender_factory,
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


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    # One session per request, closed when the response is done.
    async with container.sessions() as session:
        yield session


PrincipalDep = Annotated[Principal, Depends(get_principal)]
NoteServiceDep = Annotated[NoteService, Depends(get_note_service)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_category_service(session: SessionDep) -> CategoryService:
    return CategoryService(CategoryRepository(session))


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]


def get_client_service(session: SessionDep) -> ClientService:
    return ClientService(ClientRepository(session))


ClientServiceDep = Annotated[ClientService, Depends(get_client_service)]


def get_campaign_service(session: SessionDep) -> CampaignService:
    return CampaignService(CampaignRepository(session))


CampaignServiceDep = Annotated[CampaignService, Depends(get_campaign_service)]


def get_email_service(session: SessionDep, container: ContainerDep) -> EmailService:
    return EmailService(
        EmailRepository(session),
        SmtpConfigService(ConfigRepository(session, container.encryption)),
        container.email_sender_factory,
    )


EmailServiceDep = Annotated[EmailService, Depends(get_email_service)]


def get_smtp_config_service(session: SessionDep, container: ContainerDep) -> SmtpConfigService:
    return SmtpConfigService(ConfigRepository(session, container.encryption))


SmtpConfigServiceDep = Annotated[SmtpConfigService, Depends(get_smtp_config_service)]


def get_email_sender_factory(container: ContainerDep) -> EmailSenderFactory:
    return container.email_sender_factory


EmailSenderFactoryDep = Annotated[EmailSenderFactory, Depends(get_email_sender_factory)]
