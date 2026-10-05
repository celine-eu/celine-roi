"""Startup posture check: development defaults are refused outside ``CELINE_ENV=dev``.

The service ships zero-config development defaults — a `DATABASE_URL` carrying
the local stack's password and the SDK's local Keycloak as issuer. Each is safe
only because something refuses it when the environment does not say it is
development; this module is that something (REQ-1201).

The rule is `celine.sdk.posture`'s, shared by every service: only
`CELINE_ENV=dev` (or `ENVIRONMENT=dev`) relaxes, and unset is hardened. In dev
each violation is logged as one warning; anywhere else startup raises
`InsecureConfiguration` naming all of them at once.

`DATABASE_URL=""` — persistence disabled (REQ-0401) — carries no password and
is accepted everywhere.
"""

from __future__ import annotations

from celine.sdk.posture import PostureGuard

from celine.roi.settings import Settings

SERVICE = "celine-roi"


def posture_guard(settings: Settings, env: str | None = None) -> PostureGuard:
    """Register every development-only setting of the service on one guard.

    ``env`` overrides the environment signal, for tests; ``None`` reads
    ``CELINE_ENV`` then ``ENVIRONMENT``.
    """
    guard = PostureGuard(SERVICE, env=env)
    guard.forbid_dev_database_url("DATABASE_URL", settings.database_url)
    guard.require_explicit_oidc(settings.oidc)
    if "*" in {ip.strip() for ip in settings.forwarded_allow_ips.split(",")}:
        guard.add(
            "FORWARDED_ALLOW_IPS",
            "trusts X-Forwarded-For from every peer, so a caller picks its own address",
            "set it to the ingress's address range (REQ-1301)",
        )
    return guard


def enforce_posture(settings: Settings, env: str | None = None) -> None:
    """Warn in dev; raise `InsecureConfiguration` anywhere else."""
    posture_guard(settings, env=env).enforce()
