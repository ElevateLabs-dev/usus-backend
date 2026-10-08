# from pydantic_settings import BaseSettings, SettingsConfigDict
# from typing import Optional


# class Settings(BaseSettings):
#     # core
#     PROJECT_NAME: str = "Usus Backend"
#     ENVIRONMENT: str = "local"
#     SECRET_KEY: str

#     # infrastructure
#     DATABASE_URL: str
#     CELERY_BROKER_URL: str
#     CELERY_RESULT_BACKEND: str

#     # Admin dashboard credentials
#     ADMIN_USERNAME: str = "admin"
#     ADMIN_PASSWORD: str

#     # AI Providers (Optional locally so the app doesn't crash if you leave them blank at first)
#     OPENAI_API_KEY: Optional[str] = None
#     ANTHROPIC_API_KEY: Optional[str] = None

#     # AWS Storage (Optional locally)
#     AWS_ACCESS_KEY_ID: Optional[str] = None
#     AWS_SECRET_ACCESS_KEY: Optional[str] = None
#     AWS_REGION: Optional[str] = None
#     AWS_S3_BUCKET_NAME: Optional[str] = None

#     # This tells Pydantic to read from the .env file in the root directory
#     model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# # Create a single instance of the settings to be imported and used across the app
# settings = Settings()


# ====================================

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

    # AI Providers
    # Which LLM backs the simulation + evaluation engines: "openai" or "anthropic"
    LLM_PROVIDER: str = "openai"
    # Seconds before an LLM call is abandoned, so a slow model can't hang a request
    LLM_TIMEOUT_SECONDS: float = 60.0

    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"

    # AWS Storage
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    AWS_S3_BUCKET_NAME: Optional[str] = None

    # This tells Pydantic to read from the .env file in the root directory
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()