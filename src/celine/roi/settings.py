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
    # The proxies whose X-Forwarded-For uvicorn trusts. uvicorn reads the same
    # variable itself; it is declared here so the posture check can refuse "*"
    # outside dev (REQ-1301).
    forwarded_allow_ips: str = "127.0.0.1"

    # The calculators are public: these bound what one anonymous caller can cost
    # the service (REQ-13xx). Per process and per client address.
    rate_limit_calculators_per_minute: int = 30
    rate_limit_feedback_per_minute: int = 5
    max_body_bytes_calculators: int = 64 * 1024
    max_body_bytes_feedback: int = 4 * 1024 * 1024
    estimates_max_writes_per_minute: int = 60
    client_ip_retention_days: int = 30
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
