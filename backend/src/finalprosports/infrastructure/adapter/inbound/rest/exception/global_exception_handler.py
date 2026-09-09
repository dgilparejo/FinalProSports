from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from finalprosports.application.exception.catalog.food_already_exists_error import FoodAlreadyExistsError
from finalprosports.application.exception.client.client_code_reserved_error import ClientCodeReservedError
from finalprosports.application.exception.client.client_not_found_error import ClientNotFoundError
from finalprosports.application.exception.proposal.goal_not_servable_error import GoalNotServableError
from finalprosports.application.exception.proposal.no_similar_cases_error import NoSimilarCasesError
from finalprosports.domain.composition.exception.unsatisfiable_restriction_error import UnsatisfiableRestrictionError
from finalprosports.infrastructure.adapter.inbound.rest.exception.api_error_response import ApiErrorResponse
from finalprosports.infrastructure.config.security import AuthenticationError, AuthorizationError


def register_exception_handlers(app: FastAPI) -> None:
    # 401 and 403 are DIFFERENT situations and answer differently: 401 = there is no usable token
    # (absent, malformed, expired, bad signature, wrong issuer, wrong audience); 403 = the token is
    # valid and the caller is simply not allowed (no `entrenador` role, subject not provisioned).
    # Collapsing them into one code would be an API design bug, and it hides which of the two failed.
    @app.exception_handler(AuthenticationError)
    async def _unauthenticated(_: Request, exc: AuthenticationError):
        return JSONResponse(status_code=401, content=ApiErrorResponse("unauthenticated", str(exc)).to_dict(),
                            headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(AuthorizationError)
    async def _forbidden(_: Request, exc: AuthorizationError):
        return JSONResponse(status_code=403, content=ApiErrorResponse("forbidden", str(exc)).to_dict())

    @app.exception_handler(ClientNotFoundError)
    async def _client_not_found(_: Request, exc: ClientNotFoundError):
        return JSONResponse(status_code=404, content=ApiErrorResponse("client_not_found", str(exc)).to_dict())

    @app.exception_handler(ClientCodeReservedError)
    async def _reserved(_: Request, exc: ClientCodeReservedError):
        return JSONResponse(status_code=409, content=ApiErrorResponse("client_code_reserved", str(exc)).to_dict())

    @app.exception_handler(FoodAlreadyExistsError)
    async def _food_exists(_: Request, exc: FoodAlreadyExistsError):
        return JSONResponse(status_code=409, content=ApiErrorResponse("food_already_exists", str(exc)).to_dict())

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        return JSONResponse(status_code=422, content=ApiErrorResponse("invalid_value", str(exc)).to_dict())

    @app.exception_handler(NoSimilarCasesError)
    async def _no_cases(_: Request, exc: NoSimilarCasesError):
        return JSONResponse(status_code=422, content=ApiErrorResponse("no_similar_cases", str(exc)).to_dict())

    @app.exception_handler(GoalNotServableError)
    async def _goal_not_servable(_: Request, exc: GoalNotServableError):
        # 422, like the other "the request is fine but the case base cannot answer it" cases. The goal travels in
        # the payload so the interface can name it instead of showing an empty diet the professional has to notice.
        return JSONResponse(status_code=422, content={**ApiErrorResponse("goal_not_servable", str(exc)).to_dict(),
                                                      "goal": exc.goal, "cases_retrieved": exc.cases})

    @app.exception_handler(UnsatisfiableRestrictionError)
    async def _unsatisfiable(_: Request, exc: UnsatisfiableRestrictionError):
        return JSONResponse(status_code=422, content=ApiErrorResponse("unsatisfiable_restriction", str(exc)).to_dict())
