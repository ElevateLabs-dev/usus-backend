from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # core
    PROJECT_NAME: str = "Usus Backend"
    ENVIRONMENT: str = "local"
    SECRET_KEY: str

    # infrastructure
    DATABASE_URL: str
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Admin dashboard credentials
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str

    # AI Providers (Optional locally so the app doesn't crash if you leave them blank at first)
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # AWS Storage (Optional locally)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    AWS_S3_BUCKET_NAME: Optional[str] = None

    # This tells Pydantic to read from the .env file in the root directory
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Create a single instance of the settings to be imported and used across the app
settings = Settings()
