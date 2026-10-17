"""Async SQLAlchemy engine and sessions, and the Alembic upgrade run at startup."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

API_DIR = Path(__file__).resolve().parent.parent


def create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # No expiry on commit: lazy loading after a commit would raise MissingGreenlet.
    return async_sessionmaker(engine, expire_on_commit=False)


def run_migrations(url: str) -> None:
    """Upgrade the database at url to the newest revision, from any working directory.

    Synchronous: the async env.py calls asyncio.run, so call this outside a running loop
    (asyncio.to_thread in the lifespan).
    """
    config = Config(API_DIR / "alembic.ini")
    config.set_main_option("script_location", str(API_DIR / "migrations"))
    # The config is an interpolating ConfigParser: escape "%" in the URL.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")
