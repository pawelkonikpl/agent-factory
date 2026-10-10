"""Login, session lookup and logout."""

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.config import Settings
from app.errors import (
    InvalidIdTokenError,
    LoginError,
    LoginErrorCode,
    ProviderError,
    TokenEndpointError,
)
from app.models import LoginTransaction, TokenSet, UserProfile, UserSession
from app.services.crypto import (
    code_challenge_s256,
    constant_time_equals,
    generate_code_verifier,
    random_token,
)
from app.services.oidc_client import OidcClient, TokenResponse
from app.session_repository import SessionRepository
from app.stores import Clock, TtlStore

logger = logging.getLogger(__name__)

DEFAULT_RETURN_TO = "/"


@dataclass(frozen=True)
class CallbackParams:
    """Query parameters of the authorization response."""

    code: str | None
    state: str | None
    iss: str | None
    error: str | None


def sanitize_return_to(value: str | None) -> str:
    """Accept only a path on the app's own origin, so login is never an open redirector."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return DEFAULT_RETURN_TO
    # Browsers drop tabs and newlines and treat "\" like "/", so "/\t/evil.example"
    # or "/\\evil.example" would become a link to another host.
    if "\\" in value or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value):
        return DEFAULT_RETURN_TO
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return DEFAULT_RETURN_TO
    return value


class AuthService:
    def __init__(
        self,
        settings: Settings,
        oidc: OidcClient,
        logins: TtlStore[LoginTransaction],
        sessions: SessionRepository,
        clock: Clock,
    ) -> None:
        self._settings = settings
        self._oidc = oidc
        self._logins = logins
        self._sessions = sessions
        self._clock = clock

    async def start_login(self, return_to: str | None) -> tuple[str, str]:
        """Create a login transaction. Returns (login_id, authorization_url)."""
        transaction = LoginTransaction(
            state=random_token(),
            nonce=random_token(),
            code_verifier=generate_code_verifier(),
            return_to=sanitize_return_to(return_to),
        )
        authorization_url = await self._oidc.authorization_url(
            state=transaction.state,
            nonce=transaction.nonce,
            code_challenge=code_challenge_s256(transaction.code_verifier),
        )
        login_id = random_token()
        await self._logins.set(login_id, transaction, self._settings.login_timeout_seconds)
        return login_id, authorization_url

    async def complete_login(
        self, login_id: str | None, params: CallbackParams
    ) -> tuple[UserSession, str]:
        """Finish the authorization code flow. Returns (new session, path to return to)."""
        # pop: a login transaction can be completed at most once.
        transaction = await self._logins.pop(login_id) if login_id else None
        if transaction is None:
            raise LoginError(LoginErrorCode.LOGIN_EXPIRED, "No pending login for this browser")
        if params.state is None or not constant_time_equals(params.state, transaction.state):
            raise LoginError(LoginErrorCode.STATE_MISMATCH, "state does not match the login")
        if not await self._oidc.is_expected_issuer(params.iss):
            raise LoginError(LoginErrorCode.ISSUER_MISMATCH, f"Unexpected iss {params.iss!r}")
        if params.error is not None:
            code = (
                LoginErrorCode.ACCESS_DENIED
                if params.error == "access_denied"
                else LoginErrorCode.AUTHORIZATION_FAILED
            )
            raise LoginError(code, f"Authorization server returned error {params.error!r}")
        if not params.code:
            raise LoginError(LoginErrorCode.AUTHORIZATION_FAILED, "Response has no code")

        try:
            tokens = await self._oidc.exchange_code(params.code, transaction.code_verifier)
        except TokenEndpointError as exc:
            raise LoginError(LoginErrorCode.AUTHORIZATION_FAILED, str(exc)) from exc
        if tokens.id_token is None:
            raise LoginError(LoginErrorCode.INVALID_ID_TOKEN, "Token response has no ID token")
        try:
            claims = await self._oidc.validate_id_token(tokens.id_token, nonce=transaction.nonce)
        except InvalidIdTokenError as exc:
            raise LoginError(LoginErrorCode.INVALID_ID_TOKEN, str(exc)) from exc

        now = self._clock()
        session = UserSession(
            # Always a fresh id, so an id planted before login is worthless (session fixation).
            session_id=random_token(),
            user=UserProfile.from_claims(claims),
            tokens=token_set_from_response(tokens, now=now, id_token=tokens.id_token),
            created_at=now,
        )
        await self._sessions.save(session)
        return session, transaction.return_to

    async def get_session(self, session_id: str | None) -> UserSession | None:
        if not session_id:
            return None
        return await self._sessions.get(session_id)

    async def discard_session(self, session_id: str | None) -> None:
        """Forget a session locally, e.g. the previous one when the user logs in again."""
        if session_id:
            await self._sessions.delete(session_id)

    async def logout(self, session_id: str | None) -> str | None:
        """End the session and revoke its refresh token. Returns the IdP logout URL."""
        session = await self._sessions.pop(session_id) if session_id else None
        if session is None:
            return None
        if session.tokens.refresh_token is not None:
            try:
                await self._oidc.revoke_refresh_token(session.tokens.refresh_token)
            except ProviderError:
                # Logout must still succeed locally; the token expires on its own.
                logger.warning("Refresh token revocation failed for %s", session.user.subject)
        return await self._oidc.end_session_url(session.tokens.id_token)


def token_set_from_response(tokens: TokenResponse, *, now: float, id_token: str) -> TokenSet:
    return TokenSet(
        access_token=tokens.access_token,
        access_token_expires_at=now + tokens.expires_in,
        refresh_token=tokens.refresh_token,
        id_token=id_token,
    )
