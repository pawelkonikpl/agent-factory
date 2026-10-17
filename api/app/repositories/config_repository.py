"""Per-user settings in PostgreSQL. Every query is filtered by the user's subject."""

from dataclasses import dataclass, field
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.config import Config
from app.schemas.smtp_config import SmtpConfigUpdateSchema
from app.services.encryption import EncryptionService


@dataclass(frozen=True)
class StoredSmtpConfig:
    """The stored SMTP values as text, None when not saved."""

    smtp_server: str | None = None
    smtp_port: str | None = None
    smtp_user: str | None = None
    smtp_use_tls: str | None = None
    smtp_password: str | None = field(default=None, repr=False)


class ConfigRepository:
    SMTP_KEYS: ClassVar[list[str]] = ["smtp_server", "smtp_port", "smtp_user", "smtp_use_tls"]
    SMTP_ENCRYPTED_KEYS: ClassVar[set[str]] = {"smtp_password"}

    def __init__(self, session: AsyncSession, encryption: EncryptionService) -> None:
        self._session = session
        self._encryption = encryption

    async def get_smtp_config(self, user_sub: str) -> StoredSmtpConfig:
        """The user's SMTP values without the password."""
        rows = await self._rows(user_sub, self.SMTP_KEYS)
        return StoredSmtpConfig(**{row.config_key: row.config_value_encrypted for row in rows})

    async def get_smtp_config_with_password(self, user_sub: str) -> StoredSmtpConfig:
        """The user's SMTP values with the password decrypted."""
        rows = await self._rows(user_sub, [*self.SMTP_KEYS, *self.SMTP_ENCRYPTED_KEYS])
        values = {
            row.config_key: (
                self._encryption.decrypt(row.config_value_encrypted)
                if row.is_encrypted
                else row.config_value_encrypted
            )
            for row in rows
        }
        return StoredSmtpConfig(**values)

    async def upsert_smtp_config(self, user_sub: str, payload: SmtpConfigUpdateSchema) -> None:
        """Write every field that is not None; keys not in the payload stay as they are."""
        for key in [*self.SMTP_KEYS, *self.SMTP_ENCRYPTED_KEYS]:
            value = getattr(payload, key)
            if value is None:
                continue
            encrypted = key in self.SMTP_ENCRYPTED_KEYS
            stored = self._encryption.encrypt(str(value)) if encrypted else str(value)
            # ON CONFLICT: two concurrent first saves update the same row instead of failing.
            statement = insert(Config).values(
                user_sub=user_sub,
                config_key=key,
                config_value_encrypted=stored,
                is_encrypted=encrypted,
            )
            statement = statement.on_conflict_do_update(
                constraint="uq_user_config_key",
                set_={
                    "config_value_encrypted": statement.excluded.config_value_encrypted,
                    "is_encrypted": statement.excluded.is_encrypted,
                    "updated_at": utc_now(),
                },
            )
            await self._session.execute(statement)
        await self._session.commit()

    async def _rows(self, user_sub: str, keys: list[str]) -> list[Config]:
        query = select(Config).where(Config.user_sub == user_sub, Config.config_key.in_(keys))
        rows = await self._session.scalars(query)
        return list(rows)
