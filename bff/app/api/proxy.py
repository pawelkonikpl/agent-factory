"""/api/* is forwarded to the resource server with the session's access token."""

from fastapi import APIRouter, Depends, Request, Response

from app.dependencies import (
    ApiProxyDep,
    CurrentSessionDep,
    TokenServiceDep,
    require_csrf_protection,
)

router = APIRouter(prefix="/api", tags=["api-proxy"])

PROXIED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


@router.api_route(
    "/{path:path}",
    methods=PROXIED_METHODS,
    response_class=Response,
    dependencies=[Depends(require_csrf_protection)],
)
async def proxy_to_api(
    path: str,
    request: Request,
    session: CurrentSessionDep,
    tokens: TokenServiceDep,
    proxy: ApiProxyDep,
) -> Response:
    access_token = await tokens.access_token_for(session)
    upstream = await proxy.forward(
        method=request.method,
        path=path,
        query=request.url.query,
        headers=request.headers,
        body=await request.body(),
        access_token=access_token,
    )
    return Response(
        content=upstream.content, status_code=upstream.status_code, headers=upstream.headers
    )
