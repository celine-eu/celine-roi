"""The startup posture check (REQ-1201).

Only `CELINE_ENV=dev` relaxes it; unset and every other value are hardened. The
suite itself runs with `CELINE_ENV=dev` (conftest), so each test here states the
signal it is about.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from celine.sdk.posture import InsecureConfiguration
from celine.sdk.settings.models import OidcSettings

from celine.roi.api.app import create_app
from celine.roi.posture import enforce_posture, posture_guard
from celine.roi.settings import Settings

DEV_DATABASE_URL = "postgresql://postgres:securepassword123@host.docker.internal:15432/roi"
REAL_DATABASE_URL = "postgresql://roi:Xk3-generated-9fQ@db:5432/roi"

HARDENED = ["", "staging", "prod", "Dev-typo"]


def explicit_oidc() -> OidcSettings:
    return OidcSettings(
        base_url="https://auth.example.org/realms/example",
        jwks_uri="https://auth.example.org/realms/example/protocol/openid-connect/certs",
        audience="oauth2_proxy",
    )


def deployed_settings(**overrides) -> Settings:
    """A configuration a deployment would pass: nothing left at a dev default."""
    values = {"_env_file": None, "database_url": REAL_DATABASE_URL, "oidc": explicit_oidc()}
    values.update(overrides)
    return Settings(**values)


@pytest.fixture(autouse=True)
def no_oidc_environment(monkeypatch):
    """An exported CELINE_OIDC_* would count as stated and hide the default."""
    for name in ("BASE_URL", "JWKS_URI"):
        monkeypatch.delenv(f"CELINE_OIDC_{name}", raising=False)


@pytest.fixture
def no_env_signal(monkeypatch):
    monkeypatch.delenv("CELINE_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)


class TestOnlyDevAcceptsDevelopmentDefaults:
    """@verifies REQ-1201"""

    @pytest.mark.parametrize("env", HARDENED)
    def test_hardened_starts_with_real_values(self, env) -> None:
        assert posture_guard(deployed_settings(), env=env).violations == []
        enforce_posture(deployed_settings(), env=env)

    @pytest.mark.parametrize("env", HARDENED)
    def test_hardened_refuses_the_dev_database_password(self, env) -> None:
        with pytest.raises(InsecureConfiguration, match="DATABASE_URL"):
            enforce_posture(deployed_settings(database_url=DEV_DATABASE_URL), env=env)

    @pytest.mark.parametrize("env", HARDENED)
    def test_hardened_refuses_the_sdk_keycloak_default(self, env) -> None:
        implicit = OidcSettings(audience="oauth2_proxy")
        with pytest.raises(InsecureConfiguration) as exc:
            enforce_posture(deployed_settings(oidc=implicit), env=env)
        assert "CELINE_OIDC_BASE_URL" in str(exc.value)
        assert "CELINE_OIDC_JWKS_URI" in str(exc.value)

    def test_persistence_disabled_is_not_a_violation(self) -> None:
        enforce_posture(deployed_settings(database_url=""), env="staging")

    def test_dev_accepts_every_default(self) -> None:
        defaults = Settings(_env_file=None, oidc=OidcSettings(audience="oauth2_proxy"))
        # Patched rather than read through caplog, which depends on how other
        # tests left logging configured.
        with patch("celine.sdk.posture.log") as log:
            enforce_posture(defaults, env="dev")
        assert "DATABASE_URL" in log.warning.call_args.args[-1]

    def test_an_unset_signal_is_hardened(self, no_env_signal, monkeypatch) -> None:
        from celine.roi.settings import settings

        monkeypatch.setattr(settings, "database_url", DEV_DATABASE_URL)
        with pytest.raises(InsecureConfiguration, match="DATABASE_URL"):
            create_app()

    def test_staging_refuses_through_the_app_factory(self, monkeypatch) -> None:
        from celine.roi.settings import settings

        monkeypatch.setenv("CELINE_ENV", "staging")
        monkeypatch.setattr(settings, "database_url", DEV_DATABASE_URL)
        with pytest.raises(InsecureConfiguration):
            create_app()

    def test_dev_builds_the_app(self, monkeypatch) -> None:
        from celine.roi.settings import settings

        monkeypatch.setenv("CELINE_ENV", "dev")
        monkeypatch.setattr(settings, "database_url", DEV_DATABASE_URL)
        assert create_app().title == "CELINE ROI API"
