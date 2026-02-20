from pydantic import BaseModel


class CookieData(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    secure: bool = False
    httpOnly: bool = False
    sameSite: str = "Lax"
    expires: float = -1


class SessionCreateRequest(BaseModel):
    url: str = "https://www.google.com"
    cookies: list[CookieData] = []


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
