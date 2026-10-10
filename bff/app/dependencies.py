"""Wiring of services and FastAPI dependency providers."""

from dataclasses import dataclass
from typing import Annotated, cast

import httpx
from fastapi import Depends, Request

from app.config import Settings
from app.errors import NotAuthenticatedError
from app.models import LoginTransaction, UserSession
from app.security import check_csrf
from app.services.api_proxy import ApiProxy
from app.services.auth_service import AuthService
from app.services.oidc_client import OidcClient
from app.services.token_service import TokenService
from app.session_repository import SessionRepository
from app.stores import Clock, InMemoryTtlStore


@dataclass(frozen=True)
class Container:
    settings: Settings
    auth: AuthService
    tokens: TokenService
    proxy: ApiProxy


def build_container(settings: Settings, http: httpx.AsyncClient, clock: Clock) -> Container:
    oidc = OidcClient(settings, http)
    sessions = SessionRepository(InMemoryTtlStore[UserSession](clock), settings, clock)
    logins = InMemoryTtlStore[LoginTransaction](clock)
    return Container(
        settings=settings,
        auth=AuthService(settings, oidc, logins, sessions, clock),
        tokens=TokenService(settings, oidc, sessions, clock),
        proxy=ApiProxy(http, settings.api_base_url),
    )


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings(container: ContainerDep) -> Settings:
    return container.settings


def get_auth_service(container: ContainerDep) -> AuthService:
    return container.auth


def get_token_service(container: ContainerDep) -> TokenService:
    return container.tokens


def get_api_proxy(container: ContainerDep) -> ApiProxy:
    return container.proxy


SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]
ApiProxyDep = Annotated[ApiProxy, Depends(get_api_proxy)]


def require_csrf_protection(request: Request, settings: SettingsDep) -> None:
    check_csrf(request, settings)


def get_session_id(request: Request, settings: SettingsDep) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


SessionIdDep = Annotated[str | None, Depends(get_session_id)]


async def get_current_session(session_id: SessionIdDep, auth: AuthServiceDep) -> UserSession:
    session = await auth.get_session(session_id)
    if session is None:
        raise NotAuthenticatedError("No active session")
    return session


CurrentSessionDep = Annotated[UserSession, Depends(get_current_session)]
