from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Query, status

from app.dependencies import (
    CampaignSenderDep,
    CampaignServiceDep,
    EmailMaxConcurrentDep,
    PrincipalDep,
)
from app.schemas.base import Page, PageParamsDep
from app.schemas.campaigns import CampaignCreateSchema, CampaignSchema, CampaignUpdateSchema

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


@router.get("/", response_model=Page[CampaignSchema])
async def list_campaigns(
    page: PageParamsDep,
    principal: PrincipalDep,
    service: CampaignServiceDep,
    search: str | None = None,
) -> Page[CampaignSchema]:
    return await service.get_all(page.skip, page.limit, search)


@router.post("/", response_model=CampaignSchema, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreateSchema, principal: PrincipalDep, service: CampaignServiceDep
) -> CampaignSchema:
    return service.to_schema(await service.create(payload))


@router.get("/{campaign_id}", response_model=CampaignSchema)
async def get_campaign(
    campaign_id: int, principal: PrincipalDep, service: CampaignServiceDep
) -> CampaignSchema:
    return service.to_schema(await service.get_by_id(campaign_id))


@router.put("/{campaign_id}", response_model=CampaignSchema)
async def update_campaign(
    campaign_id: int,
    payload: CampaignUpdateSchema,
    principal: PrincipalDep,
    service: CampaignServiceDep,
) -> CampaignSchema:
    return service.to_schema(await service.update(campaign_id, payload))


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: int, principal: PrincipalDep, service: CampaignServiceDep
) -> None:
    await service.delete(campaign_id)


@router.post(
    "/{campaign_id}/recipients",
    response_model=CampaignSchema,
    status_code=status.HTTP_201_CREATED,
)
async def add_campaign_recipients(
    campaign_id: int,
    # Body(): the request body is the bare array of client IDs, not an object.
    client_ids: Annotated[list[int], Body()],
    principal: PrincipalDep,
    service: CampaignServiceDep,
) -> CampaignSchema:
    return service.to_schema(await service.add_recipients(campaign_id, client_ids))


@router.post(
    "/{campaign_id}/send", response_model=CampaignSchema, status_code=status.HTTP_202_ACCEPTED
)
async def send_campaign(
    campaign_id: int,
    principal: PrincipalDep,
    sender: CampaignSenderDep,
    service: CampaignServiceDep,
    default_max_concurrent: EmailMaxConcurrentDep,
    background_tasks: BackgroundTasks,
    max_concurrent: int | None = Query(None, ge=1, le=50),
) -> CampaignSchema:
    # The checks and the move to sending happen here; the sends run after the response.
    campaign, smtp_config = await sender.start(campaign_id, principal.subject)
    if max_concurrent is None:
        max_concurrent = default_max_concurrent
    background_tasks.add_task(sender.run, campaign_id, smtp_config, max_concurrent)
    return service.to_schema(campaign)
