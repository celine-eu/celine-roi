"""POST /api/v1/compare — compare multiple scenarios side-by-side."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, model_validator

from celine.roi.api.deps import ConfigDep, apply_config_overrides, client_ip
from celine.roi.api.routes._converters import to_system_input
from celine.roi.api.routes._persist import persist_estimate
from celine.roi.api.schemas import (
    ConfigOverrides,
    ErrorResponse,
    ScenarioResultResponse,
    SystemInputRequest,
)
from celine.roi.scenarios.comparator import compare_scenarios

logger = logging.getLogger(__name__)

# Each scenario is a full pipeline run, and possibly a PVGIS fetch (REQ-1305).
MAX_SCENARIOS = 6
MAX_SCENARIO_NAME = 100

# What a scenario may vary: what a request could set, and nothing else (REQ-1308).
# `optimize_profile` is the one config switch the comparison adds.
_SYSTEM_KEYS = frozenset(SystemInputRequest.model_fields)
_CONFIG_KEYS = frozenset(ConfigOverrides.model_fields) | {"optimize_profile"}

router = APIRouter()


def _first_error(exc: ValidationError) -> str:
    err = exc.errors()[0]
    return f"{' → '.join(str(loc) for loc in err['loc'])}: {err['msg']}"


class CompareRequest(BaseModel):
    system: SystemInputRequest
    scenarios: dict[str, dict] = Field(
        min_length=1,
        max_length=MAX_SCENARIOS,
        description=(
            f"Named scenarios with override dicts, at most {MAX_SCENARIOS}. "
            "First is base case."
        ),
    )
    config_overrides: ConfigOverrides = Field(default_factory=ConfigOverrides)

    @model_validator(mode="after")
    def overrides_are_request_fields(self) -> CompareRequest:
        """Validate each scenario as if it were a request of its own (REQ-1308).

        A scenario override used to reach the comparator unchecked: any loaded config
        key (tax rates included), any system field without the schema's bounds.
        """
        base = self.system.model_dump()
        checked: dict[str, dict] = {}
        for name, overrides in self.scenarios.items():
            if len(name) > MAX_SCENARIO_NAME:
                raise ValueError(f"scenario name longer than {MAX_SCENARIO_NAME} characters")
            unknown = sorted(set(overrides) - _SYSTEM_KEYS - _CONFIG_KEYS)
            if unknown:
                shown = ", ".join(key[:40] for key in unknown[:5])
                raise ValueError(f"scenario {name!r}: override not allowed: {shown}")
            system_part = {k: v for k, v in overrides.items() if k in _SYSTEM_KEYS}
            config_part = {
                k: v
                for k, v in overrides.items()
                if k not in _SYSTEM_KEYS and k != "optimize_profile"
            }
            try:
                varied = SystemInputRequest.model_validate({**base, **system_part})
                config = ConfigOverrides.model_validate(config_part)
            except ValidationError as exc:
                raise ValueError(f"scenario {name!r}: {_first_error(exc)}") from None
            domain = to_system_input(varied)
            scenario = {k: getattr(domain, k) for k in system_part}
            scenario.update(config.model_dump(exclude_unset=True))
            if "optimize_profile" in overrides:
                if not isinstance(overrides["optimize_profile"], bool):
                    raise ValueError(f"scenario {name!r}: optimize_profile must be a boolean")
                scenario["optimize_profile"] = overrides["optimize_profile"]
            checked[name] = scenario
        self.scenarios = checked
        return self


class CompareResponse(BaseModel):
    scenarios: dict[str, ScenarioResultResponse]
    summary_table: str = Field(description="Markdown comparison table")


@router.post(
    "/compare",
    response_model=CompareResponse,
    responses={
        400: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
    summary="Compare multiple scenarios",
    description=(
        "Run N named scenarios with different parameter overrides "
        "and return a side-by-side comparison table."
    ),
)
async def compare_endpoint(
    request: CompareRequest,
    config: ConfigDep,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> CompareResponse:
    effective_config = apply_config_overrides(config, request.config_overrides)
    system_input = to_system_input(request.system)
    request_body = request.model_dump(mode="json")
    caller = client_ip(http_request)

    t0 = time.monotonic()
    try:
        result = await compare_scenarios(system_input, effective_config, request.scenarios)
    except ConnectionError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        background_tasks.add_task(
            persist_estimate,
            endpoint="compare",
            status="error",
            request_body=request_body,
            response_body=None,
            duration_ms=duration_ms,
            client_ip=caller,
            error_message=str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc))
    except ValueError as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        background_tasks.add_task(
            persist_estimate,
            endpoint="compare",
            status="error",
            request_body=request_body,
            response_body=None,
            duration_ms=duration_ms,
            client_ip=caller,
            error_message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc))

    duration_ms = int((time.monotonic() - t0) * 1000)
    response_obj = CompareResponse(
        scenarios={
            name: ScenarioResultResponse.from_domain(sr) for name, sr in result.scenarios.items()
        },
        summary_table=result.summary_table,
    )
    background_tasks.add_task(
        persist_estimate,
        endpoint="compare",
        status="success",
        request_body=request_body,
        response_body=response_obj.model_dump(mode="json"),
        duration_ms=duration_ms,
        client_ip=caller,
    )

    return response_obj
