from __future__ import annotations

import logging

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = Field(default="INFO")

    database_url: str = Field(
        default="postgresql://postgres:securepassword123@host.docker.internal:15432/roi",
    )
    database_pool_min: int = 1
    database_pool_max: int = 5


settings = Settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(levelname)-5.5s [%(name)s] %(message)s",
)
