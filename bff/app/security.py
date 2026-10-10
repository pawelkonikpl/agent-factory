"""Cookie settings and CSRF protection for the browser-facing endpoints."""

from fastapi import Request, Response

from app.config import Settings
from app.errors import CsrfError

CSRF_HEADER_NAME = "X-CSRF"
CSRF_HEADER_VALUE = "1"


def check_csrf(request: Request, settings: Settings) -> None:
    """Reject requests that another site could have made the browser send.

    A page on another origin can only add a custom header after a CORS preflight, and
    the BFF answers no preflight, so the header proves the SPA sent the request
    (RFC 10017, CORS-based CSRF defense). Origin and Sec-Fetch-Site are checked as
    defense in depth when the browser sends them.
    """
    if request.headers.get(CSRF_HEADER_NAME) != CSRF_HEADER_VALUE:
        raise CsrfError(f"Missing {CSRF_HEADER_NAME} header")
    origin = request.headers.get("origin")
    if origin is not None and origin != settings.app_origin:
        raise CsrfError(f"Unexpected Origin {origin!r}")
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site != "same-origin":
        raise CsrfError(f"Unexpected Sec-Fetch-Site {fetch_site!r}")


def set_session_cookie(response: Response, settings: Settings, session_id: str) -> None:
    # SameSite=Strict: the browser never attaches the session to cross-site requests.
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        max_age=settings.session_absolute_timeout_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def set_login_cookie(response: Response, settings: Settings, login_id: str) -> None:
    # SameSite=Lax, not Strict: the callback is a top-level navigation coming from the
    # authorization server's site, and Strict cookies are left out of such requests.
    response.set_cookie(
        settings.login_cookie_name,
        login_id,
        max_age=settings.login_timeout_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_login_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.login_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
