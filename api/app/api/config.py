from fastapi import APIRouter

from app.dependencies import EmailSenderFactoryDep, PrincipalDep, SmtpConfigServiceDep
from app.errors import BusinessRuleError
from app.schemas.base import MessageSchema
from app.schemas.smtp_config import (
    SmtpConfigResponseSchema,
    SmtpConfigUpdateSchema,
    SmtpTestRequestSchema,
    SmtpTestResultSchema,
)

router = APIRouter(prefix="/config", tags=["Configuration"])

TEST_SUBJECT = "Email Sender — test połączenia SMTP"
TEST_BODY = (
    "<p>To jest wiadomość testowa z Email Sender.</p>"
    "<p>Jeśli ją widzisz, ustawienia SMTP działają.</p>"
)


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


@router.post("/smtp/test", response_model=SmtpTestResultSchema)
async def send_test_email(
    payload: SmtpTestRequestSchema,
    principal: PrincipalDep,
    service: SmtpConfigServiceDep,
    sender_factory: EmailSenderFactoryDep,
) -> SmtpTestResultSchema:
    config = await service.get_smtp_config_for_sending(principal.subject)
    if config is None:
        raise BusinessRuleError(
            "SMTP configuration not found. Please configure SMTP settings first."
        )
    result = await sender_factory(config).send(payload.recipient, TEST_SUBJECT, TEST_BODY)
    if not result.success:
        raise BusinessRuleError(result.error)
    return SmtpTestResultSchema(success=True, message=f"Test email sent to {payload.recipient}")
