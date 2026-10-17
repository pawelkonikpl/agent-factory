from fastapi import APIRouter

from app.dependencies import PrincipalDep, SmtpConfigServiceDep
from app.schemas.base import MessageSchema
from app.schemas.smtp_config import SmtpConfigResponseSchema, SmtpConfigUpdateSchema

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("/smtp", response_model=SmtpConfigResponseSchema)
async def get_smtp_config(
    principal: PrincipalDep, service: SmtpConfigServiceDep
) -> SmtpConfigResponseSchema:
    return await service.get_smtp_config(principal.subject)


@router.put("/smtp", response_model=MessageSchema)
async def update_smtp_config(
    payload: SmtpConfigUpdateSchema, principal: PrincipalDep, service: SmtpConfigServiceDep
) -> MessageSchema:
    await service.update_smtp_config(principal.subject, payload)
    return MessageSchema(message="Configuration updated successfully")
