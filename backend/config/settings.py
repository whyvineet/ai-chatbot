import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    app_referer: str = os.getenv("APP_REFERER", "http://localhost:8000")
    app_title: str = os.getenv("APP_TITLE", "AI Chatbot API")

    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    max_message_length: int = int(os.getenv("MAX_MESSAGE_LENGTH", "4000"))
    max_history_messages: int = int(os.getenv("MAX_HISTORY_MESSAGES", "20"))

    cors_origins: list[str] = os.getenv("CORS_ORIGINS", "*").split(",")


settings = Settings()
