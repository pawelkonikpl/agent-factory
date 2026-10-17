import httpx
import pytest
from fastapi import APIRouter, FastAPI

from app.dependencies import PrincipalDep
from app.errors import BusinessRuleError, ConflictError, DomainError, NotFoundError
from app.schemas.base import PageParamsDep
from tests.conftest import BearerFactory

# Test-only routes: no production route uses the pagination parameters or raises domain errors yet.
router = APIRouter(prefix="/test")


@router.get("/page")
async def read_page_params(params: PageParamsDep) -> dict[str, int]:
    return {"skip": params.skip, "limit": params.limit}


@router.get("/not-found")
async def raise_not_found() -> None:
    raise NotFoundError("Thing 1 not found")


@router.get("/conflict")
async def raise_conflict() -> None:
    raise ConflictError("Thing 1 already exists")


@router.get("/business-rule")
async def raise_business_rule() -> None:
    raise BusinessRuleError("Thing 1 cannot change now")


@router.get("/domain")
async def raise_domain() -> None:
    raise DomainError("Thing 1 was rejected")


@router.get("/protected")
async def raise_not_found_for_principal(principal: PrincipalDep) -> None:
    raise NotFoundError("Thing 1 not found")


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.include_router(router)
    return app


async def test_page_params_default_to_skip_0_and_limit_100(client: httpx.AsyncClient) -> None:
    response = await client.get("/test/page")

    assert response.status_code == 200
    assert response.json() == {"skip": 0, "limit": 100}


async def test_page_params_pass_skip_and_limit_through(client: httpx.AsyncClient) -> None:
    response = await client.get("/test/page", params={"skip": 5, "limit": 1000})

    assert response.status_code == 200
    assert response.json() == {"skip": 5, "limit": 1000}


@pytest.mark.parametrize("query", ["skip=-1", "limit=0", "limit=1001"])
async def test_page_params_out_of_range_answer_422(client: httpx.AsyncClient, query: str) -> None:
    response = await client.get(f"/test/page?{query}")

    assert response.status_code == 422


async def test_not_found_error_answers_404_with_its_message(client: httpx.AsyncClient) -> None:
    response = await client.get("/test/not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": "Thing 1 not found"}


@pytest.mark.parametrize(
    ("path", "message"),
    [
        pytest.param("/test/conflict", "Thing 1 already exists", id="conflict"),
        pytest.param("/test/business-rule", "Thing 1 cannot change now", id="business rule"),
        pytest.param("/test/domain", "Thing 1 was rejected", id="bare domain error"),
    ],
)
async def test_other_domain_errors_answer_400_with_their_message(
    client: httpx.AsyncClient, path: str, message: str
) -> None:
    response = await client.get(path)

    assert response.status_code == 400
    assert response.json() == {"detail": message}


async def test_missing_token_still_answers_401_before_the_domain_error(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/test/protected")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing access token"}
    assert response.headers["www-authenticate"] == 'Bearer realm="demo-api"'


async def test_valid_token_reaches_the_domain_error(
    client: httpx.AsyncClient, bearer: BearerFactory
) -> None:
    response = await client.get("/test/protected", headers=bearer())

    assert response.status_code == 404
    assert response.json() == {"detail": "Thing 1 not found"}
