from __future__ import annotations

import logging
import os

from celine.sdk.settings.models import OidcSettings
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
    jwt_header_name: str = "x-auth-request-access-token"
    oidc: OidcSettings = OidcSettings(
        audience=os.getenv("CELINE_OIDC_AUDIENCE", "oauth2_proxy"),
        client_id=os.getenv("CELINE_OIDC_CLIENT_ID", "oauth2_proxy"),
        client_secret=os.getenv("CELINE_OIDC_CLIENT_SECRET", ""),
    )


settings = Settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(levelname)-5.5s [%(name)s] %(message)s",
)
