"""Per-user SMTP settings. The password is stored encrypted and never returned by an endpoint."""

from dataclasses import dataclass, field

from app.repositories.config_repository import ConfigRepository
from app.schemas.smtp_config import SmtpConfigResponseSchema, SmtpConfigUpdateSchema

DEFAULT_SMTP_PORT = 587


def parse_bool(value: str) -> bool:
    return value.lower() in {"true", "1", "yes"}


@dataclass(frozen=True)
class SmtpConfig:
    """What sending needs, with the decrypted password."""

    smtp_server: str
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None = field(repr=False)
    smtp_use_tls: bool


class SmtpConfigService:
    def __init__(self, configs: ConfigRepository) -> None:
        self._configs = configs

    async def get_smtp_config(self, user_sub: str) -> SmtpConfigResponseSchema:
        stored = await self._configs.get_smtp_config(user_sub)
        return SmtpConfigResponseSchema(
            smtp_server=stored.smtp_server,
            smtp_port=None if stored.smtp_port is None else int(stored.smtp_port),
            smtp_user=stored.smtp_user,
            smtp_use_tls=None if stored.smtp_use_tls is None else parse_bool(stored.smtp_use_tls),
        )

    async def update_smtp_config(self, user_sub: str, payload: SmtpConfigUpdateSchema) -> None:
        await self._configs.upsert_smtp_config(user_sub, payload)

    async def get_smtp_config_for_sending(self, user_sub: str) -> SmtpConfig | None:
        """None until a server is saved; the port defaults to 587 and TLS to on."""
        stored = await self._configs.get_smtp_config_with_password(user_sub)
        if stored.smtp_server is None:
            return None
        return SmtpConfig(
            smtp_server=stored.smtp_server,
            smtp_port=DEFAULT_SMTP_PORT if stored.smtp_port is None else int(stored.smtp_port),
            smtp_user=stored.smtp_user,
            smtp_password=stored.smtp_password,
            smtp_use_tls=True if stored.smtp_use_tls is None else parse_bool(stored.smtp_use_tls),
        )
