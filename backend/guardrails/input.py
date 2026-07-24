from config.models import is_valid_model
from config.settings import settings
from exceptions import GuardrailViolationError, UnsupportedModelError


def validate_chat_request(message: str, model: str) -> None:
    _validate_message(message)
    _validate_model(model)


def _validate_message(message: str) -> None:
    if not message:
        raise GuardrailViolationError("Message cannot be empty.")

    if not message.strip():
        raise GuardrailViolationError("Message cannot be whitespace only.")

    if len(message) > settings.max_message_length:
        raise GuardrailViolationError(
            f"Message exceeds the maximum length of {settings.max_message_length} characters."
        )


def _validate_model(model: str) -> None:
    if not is_valid_model(model):
        raise UnsupportedModelError(f"Model '{model}' is not supported.")
