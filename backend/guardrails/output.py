from exceptions import ProviderUnavailableError


def validate_response(full_text: str) -> None:
    if not full_text or not full_text.strip():
        raise ProviderUnavailableError(
            "The model returned an empty response. Please try again."
        )

    if _looks_malformed(full_text):
        raise ProviderUnavailableError(
            "The model returned an unexpected response. Please try again."
        )


def _looks_malformed(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("{") and '"error"' in stripped
