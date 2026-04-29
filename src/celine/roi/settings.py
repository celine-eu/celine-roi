from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql://postgres:securepassword123@host.docker.internal:15432/celine_roi",
    )
    database_pool_min: int = 1
    database_pool_max: int = 5


settings = Settings()
