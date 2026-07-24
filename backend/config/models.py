from typing import TypedDict


class ModelConfig(TypedDict):
    display_name: str
    model: str
    temperature: float
    max_tokens: int


MODELS: dict[str, ModelConfig] = {
    "gemini-2.5-flash": {
        "display_name": "Gemini Flash 2.5",
        "model": "google/gemini-2.5-flash",
        "temperature": 0.7,
        "max_tokens": 2048,
    },
    "gpt-4o": {
        "display_name": "GPT-4o",
        "model": "openai/gpt-4o",
        "temperature": 0.7,
        "max_tokens": 2048,
    },
    "llama-3.1-8b": {
        "display_name": "Llama 3.1 8B",
        "model": "meta-llama/llama-3.1-8b-instruct",
        "temperature": 0.7,
        "max_tokens": 2048,
    },
    "qwen3.5-flash-02-23": {
        "display_name": "Qwen 3.5 Flash",
        "model": "qwen/qwen3.5-flash-02-23",
        "temperature": 0.7,
        "max_tokens": 2048,
    },
}


def is_valid_model(model_key: str) -> bool:
    return model_key in MODELS


def get_model_config(model_key: str) -> ModelConfig:
    return MODELS[model_key]
