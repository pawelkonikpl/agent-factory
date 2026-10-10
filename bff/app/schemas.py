"""JSON returned to the SPA. It never contains tokens."""

from pydantic import BaseModel


class UserResponse(BaseModel):
    sub: str
    name: str | None
    email: str | None


class SessionResponse(BaseModel):
    authenticated: bool
    user: UserResponse | None


class LogoutResponse(BaseModel):
    logout_url: str
