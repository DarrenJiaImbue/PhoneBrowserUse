from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    browser_use_api_key: str = ""
    vapi_phone_number: str = "+1234567890"

    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "*"

    code_expiry_minutes: int = 10
    session_timeout_minutes: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
