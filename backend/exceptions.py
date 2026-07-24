from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class ChatbotError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidRequestError(ChatbotError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "invalid_request"


class UnsupportedModelError(ChatbotError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "unsupported_model"


class SessionNotFoundError(ChatbotError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "session_not_found"


class ProviderTimeoutError(ChatbotError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_code = "provider_timeout"


class ProviderRateLimitError(ChatbotError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "provider_rate_limited"


class ProviderUnavailableError(ChatbotError):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "provider_unavailable"


class GuardrailViolationError(ChatbotError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "guardrail_violation"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ChatbotError)
    async def chatbot_error_handler(request: Request, exc: ChatbotError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code, "message": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "message": "Something went wrong. Please try again.",
            },
        )
