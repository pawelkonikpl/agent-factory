"""Session and OAuth endpoints used by the SPA and the authorization server."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.dependencies import AuthServiceDep, SessionIdDep, SettingsDep, require_csrf_protection
from app.schemas import LogoutResponse, SessionResponse, UserResponse
from app.security import (
    clear_login_cookie,
    clear_session_cookie,
    set_login_cookie,
    set_session_cookie,
)
from app.services.auth_service import CallbackParams

router = APIRouter(prefix="/bff", tags=["session"])

NO_STORE = "no-store"


@router.get("/login", status_code=status.HTTP_302_FOUND, response_class=RedirectResponse)
async def login(
    auth: AuthServiceDep,
    settings: SettingsDep,
    return_to: Annotated[str | None, Query(alias="returnTo")] = None,
) -> RedirectResponse:
    """The SPA navigates here (a full page load, not fetch) to start the login."""
    login_id, authorization_url = await auth.start_login(return_to)
    response = RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)
    set_login_cookie(response, settings, login_id)
    return response


@router.get("/callback", status_code=status.HTTP_303_SEE_OTHER, response_class=RedirectResponse)
async def callback(
    request: Request,
    auth: AuthServiceDep,
    settings: SettingsDep,
    previous_session_id: SessionIdDep,
    code: str | None = None,
    state: str | None = None,
    iss: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Redirect endpoint registered at the authorization server."""
    session, return_to = await auth.complete_login(
        request.cookies.get(settings.login_cookie_name),
        CallbackParams(code=code, state=state, iss=iss, error=error),
    )
    await auth.discard_session(previous_session_id)
    # A clean URL without code and state, so they stay out of history and Referer headers.
    response = RedirectResponse(return_to, status_code=status.HTTP_303_SEE_OTHER)
    clear_login_cookie(response, settings)
    set_session_cookie(response, settings, session.session_id)
    return response


@router.get(
    "/session",
    response_model=SessionResponse,
    dependencies=[Depends(require_csrf_protection)],
)
async def read_session(
    response: Response, auth: AuthServiceDep, session_id: SessionIdDep
) -> SessionResponse:
    """Tells the SPA whether the user is logged in and who they are."""
    response.headers["Cache-Control"] = NO_STORE
    session = await auth.get_session(session_id)
    if session is None:
        return SessionResponse(authenticated=False, user=None)
    user = UserResponse(sub=session.user.subject, name=session.user.name, email=session.user.email)
    return SessionResponse(authenticated=True, user=user)


@router.post(
    "/logout",
    response_model=LogoutResponse,
    dependencies=[Depends(require_csrf_protection)],
)
async def logout(
    response: Response, auth: AuthServiceDep, settings: SettingsDep, session_id: SessionIdDep
) -> LogoutResponse:
    """Ends the BFF session and returns where the browser should go to log out at the IdP."""
    logout_url = await auth.logout(session_id)
    response.headers["Cache-Control"] = NO_STORE
    clear_session_cookie(response, settings)
    return LogoutResponse(logout_url=logout_url or settings.post_logout_redirect_uri)
