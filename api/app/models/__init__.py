"""ORM models. Import every model module here, so Alembic sees all tables."""

from app.models.base import Base
from app.models.campaign import Campaign, CampaignRecipient, CampaignStatus, RecipientStatus
from app.models.category import Category
from app.models.client import Client, client_category
from app.models.config import Config

__all__ = [
    "Base",
    "Campaign",
    "CampaignRecipient",
    "CampaignStatus",
    "Category",
    "Client",
    "Config",
    "RecipientStatus",
    "client_category",
]
