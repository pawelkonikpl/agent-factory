"""Categories are global (D5): every user sees and edits the same ones."""

from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin


class Category(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "categories"
    # Unique among non-deleted categories only, so a deleted name can be reused (W-02).
    __table_args__ = (
        Index(
            "uq_categories_name_not_deleted",
            "name",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False)
