from fastapi import APIRouter

from app.dependencies import EmailServiceDep, PrincipalDep
from app.schemas.base import DbInt, MessageSchema, Page, PageParamsDep
from app.schemas.emails import EmailFiltersDep, EmailSchema, EmailStatsSchema, EmailUpdateSchema

router = APIRouter(prefix="/emails", tags=["Emails"])

# The fixed paths come first: registered after /{email_id}, /stats/ would answer 422.


@router.get("/", response_model=Page[EmailSchema])
async def list_emails(
    filters: EmailFiltersDep,
    page: PageParamsDep,
    principal: PrincipalDep,
    service: EmailServiceDep,
) -> Page[EmailSchema]:
    return await service.get_all(filters, page.skip, page.limit)


@router.get("/stats/", response_model=EmailStatsSchema)
async def get_email_stats(
    principal: PrincipalDep, service: EmailServiceDep, campaign_id: DbInt | None = None
) -> EmailStatsSchema:
    return await service.get_stats(campaign_id)


@router.get("/failed/", response_model=list[EmailSchema])
async def list_failed_emails(
    principal: PrincipalDep, service: EmailServiceDep, campaign_id: DbInt | None = None
) -> list[EmailSchema]:
    return await service.get_failed(campaign_id)


@router.get("/campaign/{campaign_id}", response_model=list[EmailSchema])
async def list_campaign_emails(
    campaign_id: DbInt, page: PageParamsDep, principal: PrincipalDep, service: EmailServiceDep
) -> list[EmailSchema]:
    return await service.get_by_campaign(campaign_id, page.skip, page.limit)


@router.get("/client/{client_id}", response_model=list[EmailSchema])
async def list_client_emails(
    client_id: DbInt, page: PageParamsDep, principal: PrincipalDep, service: EmailServiceDep
) -> list[EmailSchema]:
    return await service.get_by_client(client_id, page.skip, page.limit)


@router.get("/{email_id}", response_model=EmailSchema)
async def get_email(
    email_id: DbInt, principal: PrincipalDep, service: EmailServiceDep
) -> EmailSchema:
    return service.to_schema(await service.get_by_id(email_id))


@router.put("/{email_id}", response_model=EmailSchema)
async def update_email(
    email_id: DbInt,
    payload: EmailUpdateSchema,
    principal: PrincipalDep,
    service: EmailServiceDep,
) -> EmailSchema:
    return service.to_schema(await service.update(email_id, payload))


@router.post("/{email_id}/mark-opened", response_model=EmailSchema)
async def mark_email_opened(
    email_id: DbInt, principal: PrincipalDep, service: EmailServiceDep
) -> EmailSchema:
    return service.to_schema(await service.mark_opened(email_id))


@router.post("/{email_id}/mark-clicked", response_model=EmailSchema)
async def mark_email_clicked(
    email_id: DbInt, principal: PrincipalDep, service: EmailServiceDep
) -> EmailSchema:
    return service.to_schema(await service.mark_clicked(email_id))


@router.delete("/{email_id}", response_model=MessageSchema)
async def delete_email(
    email_id: DbInt, principal: PrincipalDep, service: EmailServiceDep
) -> MessageSchema:
    await service.delete(email_id)
    return MessageSchema(message="Email deleted successfully")
