from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRY_MINUTES: int = 60
    JWT_REFRESH_EXPIRY_DAYS: int = 30

    DATABASE_URL: str

    FERNET_KEY: str

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/gmail/callback"

    PUBSUB_TOPIC: str = ""
    PUBSUB_SUBSCRIPTION: str = ""

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    SPLITWISE_CONSUMER_KEY: str = ""
    SPLITWISE_CONSUMER_SECRET: str = ""
    SPLITWISE_REDIRECT_URI: str = "http://localhost:8000/splitwise/callback"

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_URL: str = ""

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
