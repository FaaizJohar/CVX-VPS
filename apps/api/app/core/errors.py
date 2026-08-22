from typing import Any

from fastapi import Request
from fastapi.responses import ORJSONResponse


class CVXError(Exception):
    """Base error carrying a stable machine-readable code."""

    status_code = 500
    code = "internal_error"
    message = "An internal error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_response(self, request_id: str | None = None) -> ORJSONResponse:
        body: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.message,
            }
        }
        if self.details:
            body["error"]["details"] = self.details
        if request_id:
            body["error"]["request_id"] = request_id
        return ORJSONResponse(status_code=self.status_code, content=body)


class AuthenticationError(CVXError):
    status_code = 401
    code = "unauthenticated"
    message = "Authentication required."


class InvalidCredentialsError(CVXError):
    status_code = 401
    code = "invalid_credentials"
    message = "Invalid email or password."


class AuthorizationError(CVXError):
    status_code = 403
    code = "forbidden"
    message = "You do not have permission to perform this action."


class NotFoundError(CVXError):
    status_code = 404
    code = "not_found"
    message = "Resource not found."


class ConflictError(CVXError):
    status_code = 409
    code = "conflict"
    message = "Resource already exists."


class ValidationError(CVXError):
    status_code = 422
    code = "validation_error"
    message = "Validation failed."


class RateLimitError(CVXError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests."


class NodeUnavailableError(CVXError):
    status_code = 503
    code = "node_unavailable"
    message = "Node is not reachable."


class ProviderError(CVXError):
    status_code = 502
    code = "provider_error"
    message = "Infrastructure provider operation failed."


async def cvx_error_handler(request: Request, exc: CVXError) -> ORJSONResponse:
    return exc.to_response(request_id=getattr(request.state, "request_id", None))
