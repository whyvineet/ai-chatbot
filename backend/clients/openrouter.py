import json
from collections.abc import AsyncIterator

import httpx
from config.settings import settings
from exceptions import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

CHAT_COMPLETIONS_URL = f"{settings.openrouter_base_url}/chat/completions"
_RETRYABLE_STATUS_CODES = {500, 502, 503, 504}


class OpenRouterClient:
    def __init__(self) -> None:
        self._headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.app_referer,
            "X-Title": settings.app_title,
        }

    async def stream_chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        last_error: Exception | None = None
        for attempt in range(2):
            yielded_any = False
            try:
                async for chunk in self._stream_once(payload):
                    yielded_any = True
                    yield chunk
                return
            except _TransientProviderError as exc:
                last_error = exc
                if yielded_any:
                    raise ProviderUnavailableError(
                        "The connection to the AI provider was interrupted."
                    ) from exc
                continue

        raise ProviderUnavailableError(
            "The AI provider is temporarily unavailable. Please try again."
        ) from last_error

    async def _stream_once(self, payload: dict) -> AsyncIterator[str]:
        timeout = httpx.Timeout(settings.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:  # noqa: SIM117
                async with client.stream(
                    "POST", CHAT_COMPLETIONS_URL, headers=self._headers, json=payload
                ) as response:
                    await self._raise_for_status(response)

                    async for line in response.aiter_lines():
                        chunk = self._parse_sse_line(line)
                        if chunk is not None:
                            yield chunk

        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                "The AI provider took too long to respond."
            ) from exc
        except httpx.TransportError as exc:
            raise _TransientProviderError(str(exc)) from exc

    async def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise ProviderRateLimitError("Rate limit exceeded. Please slow down.")

        if response.status_code in _RETRYABLE_STATUS_CODES:
            raise _TransientProviderError(f"Upstream returned {response.status_code}")

        if response.status_code >= 400:
            body = await response.aread()
            raise ProviderUnavailableError(
                f"Provider error ({response.status_code}): {body.decode(errors='ignore')[:200]}"
            )

    @staticmethod
    def _parse_sse_line(line: str) -> str | None:
        if not line.startswith("data: "):
            return None

        data = line[len("data: "):].strip()
        if data == "[DONE]":
            return None

        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            return None

        delta = event.get("choices", [{}])[0].get("delta", {})
        return delta.get("content")


class _TransientProviderError(Exception):
    """Internal signal used to trigger the single retry."""


openrouter_client = OpenRouterClient()
