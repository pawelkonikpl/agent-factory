from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.config import Config
from app.repositories.config_repository import ConfigRepository
from app.schemas.smtp_config import SmtpConfigResponseSchema, SmtpConfigUpdateSchema
from app.services.encryption import EncryptionService
from app.services.smtp_config_service import SmtpConfigService, parse_bool


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def encryption() -> EncryptionService:
    return EncryptionService(EncryptionService.generate_key())


@pytest.fixture
def service(session: AsyncSession, encryption: EncryptionService) -> SmtpConfigService:
    return SmtpConfigService(ConfigRepository(session, encryption))


async def save(service: SmtpConfigService, user_sub: str, **fields: Any) -> None:
    await service.update_smtp_config(user_sub, SmtpConfigUpdateSchema.model_validate(fields))


async def test_saved_settings_are_read_back(service: SmtpConfigService) -> None:
    await save(
        service,
        "alice",
        smtp_server="smtp.example.com",
        smtp_port=465,
        smtp_user="mailer",
        smtp_password="secret",
        smtp_use_tls=False,
    )

    assert await service.get_smtp_config("alice") == SmtpConfigResponseSchema(
        smtp_server="smtp.example.com", smtp_port=465, smtp_user="mailer", smtp_use_tls=False
    )


async def test_password_is_stored_encrypted(
    service: SmtpConfigService, session: AsyncSession, encryption: EncryptionService
) -> None:
    await save(service, "alice", smtp_password="secret")

    row = await session.scalar(
        select(Config).where(Config.user_sub == "alice", Config.config_key == "smtp_password")
    )

    assert row is not None
    assert row.is_encrypted
    assert row.config_value_encrypted != "secret"
    assert encryption.decrypt(row.config_value_encrypted) == "secret"


async def test_read_settings_never_carry_the_password(service: SmtpConfigService) -> None:
    await save(service, "alice", smtp_server="smtp.example.com", smtp_password="secret")

    response = await service.get_smtp_config("alice")

    assert "secret" not in response.model_dump_json()
    assert set(SmtpConfigResponseSchema.model_fields) == {
        "smtp_server",
        "smtp_port",
        "smtp_user",
        "smtp_use_tls",
    }


async def test_partial_update_keeps_the_other_keys(service: SmtpConfigService) -> None:
    await save(service, "alice", smtp_server="smtp.example.com", smtp_port=465, smtp_user="mailer")

    await save(service, "alice", smtp_port=2525, smtp_user=None)

    assert await service.get_smtp_config("alice") == SmtpConfigResponseSchema(
        smtp_server="smtp.example.com", smtp_port=2525, smtp_user="mailer", smtp_use_tls=None
    )


async def test_users_have_separate_settings(service: SmtpConfigService) -> None:
    await save(service, "alice", smtp_server="smtp.alice.test", smtp_port=465)
    await save(service, "bob", smtp_server="smtp.bob.test")

    alice = await service.get_smtp_config("alice")
    bob = await service.get_smtp_config("bob")

    assert (alice.smtp_server, alice.smtp_port) == ("smtp.alice.test", 465)
    assert (bob.smtp_server, bob.smtp_port) == ("smtp.bob.test", None)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("True", True),
        ("true", True),
        ("1", True),
        ("YES", True),
        ("False", False),
        ("0", False),
        ("", False),
    ],
)
def test_parse_bool(value: str, expected: bool) -> None:
    assert parse_bool(value) is expected


async def test_settings_for_sending_need_a_server_and_default_port_and_tls(
    service: SmtpConfigService,
) -> None:
    await save(service, "alice", smtp_password="secret")
    assert await service.get_smtp_config_for_sending("alice") is None

    await save(service, "alice", smtp_server="smtp.example.com")
    sending = await service.get_smtp_config_for_sending("alice")

    assert sending is not None
    assert sending.smtp_server == "smtp.example.com"
    assert sending.smtp_port == 587
    assert sending.smtp_use_tls is True
    assert sending.smtp_user is None
    assert sending.smtp_password == "secret"
    assert "secret" not in repr(sending)
