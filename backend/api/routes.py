import json
from collections.abc import AsyncIterator

from clients.openrouter import openrouter_client
from config.models import MODELS, get_model_config
from exceptions import ChatbotError, SessionNotFoundError
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from guardrails.input import validate_chat_request
from guardrails.output import validate_response
from guardrails.system_prompt import SYSTEM_PROMPT
from schemas.chat import ChatRequest, NewSessionResponse
from schemas.response import HealthResponse, ModelInfo, ModelsResponse
from sessions.manager import session_manager

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", service="AI Chatbot API", version="1.0.0")


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    models = [
        ModelInfo(key=key, display_name=cfg["display_name"])
        for key, cfg in MODELS.items()
    ]
    return ModelsResponse(models=models)


@router.post("/session/new", response_model=NewSessionResponse)
async def new_session() -> NewSessionResponse:
    session_id = session_manager.create_session()
    return NewSessionResponse(session_id=session_id)


@router.delete("/session/{session_id}")
async def clear_session(session_id: str) -> dict:
    session_manager.clear_session(session_id)
    return {"message": "Session cleared."}


@router.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    validate_chat_request(request.message, request.model)

    if not session_manager.session_exists(request.session_id):
        raise SessionNotFoundError(f"Session '{request.session_id}' does not exist.")

    session_manager.add_user_message(request.session_id, request.message)

    model_config = get_model_config(request.model)
    provider_messages = _build_provider_messages(request.session_id)

    return StreamingResponse(
        _stream_and_persist(request.session_id, provider_messages, model_config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


def _build_provider_messages(session_id: str) -> list[dict[str, str]]:
    history = session_manager.get_history(session_id)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        *({"role": m.role, "content": m.content} for m in history),
    ]


async def _stream_and_persist(
    session_id: str,
    provider_messages: list[dict[str, str]],
    model_config: dict,
) -> AsyncIterator[str]:
    chunks: list[str] = []

    try:
        async for chunk in openrouter_client.stream_chat_completion(
            messages=provider_messages,
            model=model_config["model"],
            temperature=model_config["temperature"],
            max_tokens=model_config["max_tokens"],
        ):
            chunks.append(chunk)
            yield _sse_event(chunk)

        full_text = "".join(chunks)
        validate_response(full_text)
        session_manager.add_assistant_message(session_id, full_text)

    except ChatbotError as exc:
        yield _sse_error(exc.error_code, exc.message)
        return

    yield _sse_done()


def _sse_event(text: str) -> str:
    return f"data: {text.replace(chr(10), chr(92) + 'n')}\n\n"


def _sse_done() -> str:
    return "event: done\ndata: [DONE]\n\n"


def _sse_error(error_code: str, message: str) -> str:
    payload = json.dumps({"error": error_code, "message": message})
    return f"event: error\ndata: {payload}\n\n"
