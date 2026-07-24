from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ModelInfo(BaseModel):
    key: str
    display_name: str


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


class ErrorResponse(BaseModel):
    error: str
    message: str
