from __future__ import annotations

from typing import Any


class ApiError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500
    retryable = False

    def __init__(self, message: str, *, detail: Any = None, retryable: bool | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail
        if retryable is not None:
            self.retryable = retryable

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"code": self.code, "message": self.message, "retryable": self.retryable}
        if self.detail is not None:
            d["detail"] = self.detail
        return d


class AuthError(ApiError):
    code = "AUTH_ERROR"
    status_code = 401


class PermissionError_(ApiError):
    code = "PERMISSION_ERROR"
    status_code = 403


class NotFoundError(ApiError):
    code = "MODEL_NOT_FOUND"
    status_code = 404


class ValidationError_(ApiError):
    code = "VALIDATION_ERROR"
    status_code = 422


class ProviderError(ApiError):
    code = "PROVIDER_ERROR"
    status_code = 502
    retryable = True


class ModelNotFoundError(ApiError):
    code = "MODEL_NOT_FOUND"
    status_code = 404


class ModelOverloadedError(ApiError):
    code = "MODEL_OVERLOADED"
    status_code = 529
    retryable = True


class RateLimitError(ApiError):
    code = "RATE_LIMIT"
    status_code = 429
    retryable = True


class ContextOverflowError(ApiError):
    code = "CONTEXT_OVERFLOW"
    status_code = 400


class CapabilityUnsupportedError(ApiError):
    code = "CAPABILITY_UNSUPPORTED"
    status_code = 400


class ToolError_(ApiError):
    code = "TOOL_ERROR"
    status_code = 500


class ToolTimeoutError(ApiError):
    code = "TOOL_TIMEOUT"
    status_code = 504
    retryable = True


class SearchError(ApiError):
    code = "SEARCH_ERROR"
    status_code = 502
    retryable = True


class FetchError(ApiError):
    code = "FETCH_ERROR"
    status_code = 502
    retryable = False


ERROR_BY_STATUS = {
    401: AuthError,
    403: PermissionError_,
    404: NotFoundError,
    429: RateLimitError,
}
