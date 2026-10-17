"""Clients are global (D5), like categories. A client links to any number of categories."""

from sqlalchemy import Column, ForeignKey, Index, String, Table, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin
from app.models.category import Category

client_category = Table(
    "client_category",
    Base.metadata,
    Column("client_id", ForeignKey("clients.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Client(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "clients"
    # Unique among non-deleted clients only, so a deleted client's email can be reused (W-02).
    __table_args__ = (
        Index(
            "uq_clients_primary_email_not_deleted",
            "primary_email",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    company_name: Mapped[str] = mapped_column(String(128), nullable=False)
    primary_email: Mapped[str] = mapped_column(String(256), nullable=False)
    additional_emails: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Loaded with the client in one extra query per page, in a stable order.
    categories: Mapped[list[Category]] = relationship(
        secondary=client_category, lazy="selectin", order_by=Category.id
    )
