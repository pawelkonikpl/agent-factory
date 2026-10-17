import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.database import API_DIR
from app.main import create_app
from app.services.encryption import EncryptionService
from tests.conftest import resolve_test_database_url

ENCRYPTION_KEY = EncryptionService.generate_key()


def test_guard_refuses_a_database_without_test_in_its_name() -> None:
    settings = Settings(
        test_database_url="postgresql+asyncpg://emailsender:emailsender@localhost:5432/emailsender",
        encryption_key=ENCRYPTION_KEY,
    )

    with pytest.raises(RuntimeError):
        resolve_test_database_url(settings)


def test_guard_derives_the_test_database_from_the_app_database() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://emailsender:emailsender@db.test:5433/emailsender",
        test_database_url=None,
        encryption_key=ENCRYPTION_KEY,
    )

    assert resolve_test_database_url(settings) == (
        "postgresql+asyncpg://emailsender:emailsender@db.test:5433/emailsender_test"
    )


async def test_lifespan_migrates_the_database_to_head(
    database_url: str, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    settings = Settings(database_url=database_url, encryption_key=ENCRYPTION_KEY)
    app = create_app(settings, session_factory=session_factory)

    async with app.router.lifespan_context(app):
        pass

    head = ScriptDirectory.from_config(Config(API_DIR / "alembic.ini")).get_current_head()
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            versions = await connection.scalars(text("SELECT version_num FROM alembic_version"))
            stored = versions.all()
    finally:
        await engine.dispose()
    assert stored == ([] if head is None else [head])


async def test_committed_work_stays_inside_the_test_transaction(
    database_url: str, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await session.execute(text("CREATE TABLE isolation_probe (id int PRIMARY KEY)"))
        await session.execute(text("INSERT INTO isolation_probe (id) VALUES (1)"))
        await session.commit()
        assert await session.scalar(text("SELECT count(*) FROM isolation_probe")) == 1

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            table = await connection.scalar(text("SELECT to_regclass('public.isolation_probe')"))
    finally:
        await engine.dispose()
    assert table is None
