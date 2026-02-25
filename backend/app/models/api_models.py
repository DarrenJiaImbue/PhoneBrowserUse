from pydantic import BaseModel


class SessionCreateRequest(BaseModel):
    url: str = "https://www.google.com"
    profile_id: str | None = None


class SessionCreateResponse(BaseModel):
    code: str
    phone_number: str
    url: str


class SessionStatusResponse(BaseModel):
    code: str
    state: str


class VapiFunction(BaseModel):
    name: str
    arguments: dict = {}


class VapiToolCall(BaseModel):
    """Represents a single tool call from VAPI."""
    id: str
    type: str = "function"
    function: VapiFunction


class VapiWebhookRequest(BaseModel):
    """Incoming VAPI webhook payload."""
    message: dict
