from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Session returned by POST /session/new")
    model: str = Field(..., description="Key from GET /models, e.g. 'gemini-flash'")
    message: str = Field(..., description="The user's message")


class NewSessionResponse(BaseModel):
    session_id: str


class ChatMessage(BaseModel):
    role: str
    content: str
