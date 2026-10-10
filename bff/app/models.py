"""Server-side state kept by the BFF. None of it is ever sent to the browser."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LoginTransaction:
    """Secrets of one authorization request, bound to the browser by the login cookie."""

    state: str
    nonce: str
    code_verifier: str
    return_to: str


@dataclass(frozen=True)
class UserProfile:
    subject: str
    name: str | None
    email: str | None

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> "UserProfile":
        name = claims.get("name") or claims.get("preferred_username")
        email = claims.get("email")
        return cls(
            subject=str(claims["sub"]),
            name=str(name) if name else None,
            email=str(email) if email else None,
        )


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    access_token_expires_at: float
    refresh_token: str | None
    id_token: str


@dataclass(frozen=True)
class UserSession:
    session_id: str
    user: UserProfile
    tokens: TokenSet
    created_at: float
