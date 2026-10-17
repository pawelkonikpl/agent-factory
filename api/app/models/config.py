"""Per-user settings (D5), one row per user and key. user_sub is Principal.subject (D12)."""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Config(IdMixin, TimestampMixin, Base):
    __tablename__ = "configs"
    __table_args__ = (UniqueConstraint("user_sub", "config_key", name="uq_user_config_key"),)

    user_sub: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    config_key: Mapped[str] = mapped_column(String(255), nullable=False)
    config_value_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_encrypted: Mapped[bool] = mapped_column(nullable=False, default=True)
