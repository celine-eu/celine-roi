"""Guards for the domain/API boundary.

Two of the three boundaries described in `.agents/knowledge/the-three-boundaries.md`
are invisible in the type system and fail quietly rather than loudly. Nothing enforced
them before this file:

1. Domain objects are frozen dataclasses carrying numpy arrays and are never serialized
   directly — `from_domain()` is the conversion. Add a field to a dataclass and the
   response silently does not carry it.
2. Only a subset of configuration is overridable per request. Tax rates and depreciation
   schedules are server policy: a caller who could set their own tax rate could produce
   any answer they liked and have it look authoritative.

Both tests are written so that a *deliberate* widening is a one-line edit here, and an
*accidental* one is a failure. That is the whole point — neither is meant to be hard to
change, only impossible to do by accident.
"""

from __future__ import annotations

import json
from dataclasses import fields as dataclass_fields

import pytest

from celine.roi.api.schemas import (
    ConfigOverrides,
    EnergyResultResponse,
    FinanceResultResponse,
    IncentiveResultResponse,
    ProductionDataResponse,
    ScenarioResultResponse,
    ValidationReportResponse,
)
from celine.roi.main import run_scenario
from celine.roi.models import (
    EnergyResult,
    FinanceResult,
    IncentiveResult,
    ProductionData,
    ValidationReport,
)

# domain dataclass -> (response schema, fields deliberately not exposed)
#
# An entry in the third column is a decision, not an oversight. Adding a field to a
# domain dataclass fails this test until someone either exposes it in the schema or
# states here why it stays internal.
_BOUNDARY = [
    (
        ProductionData,
        ProductionDataResponse,
        # 8760 floats per response, for a figure the API already reports monthly.
        {"hourly_production_kwh"},
    ),
    (EnergyResult, EnergyResultResponse, set()),
    (IncentiveResult, IncentiveResultResponse, set()),
    (FinanceResult, FinanceResultResponse, set()),
    (ValidationReport, ValidationReportResponse, set()),
]


# @verifies REQ-0201
class TestDomainFieldsReachTheResponse:

    @pytest.mark.parametrize(
        ("domain", "schema", "not_exposed"),
        _BOUNDARY,
        ids=[d.__name__ for d, _, _ in _BOUNDARY],
    )
    def test_every_domain_field_is_exposed_or_declared_internal(
        self, domain: type, schema: type, not_exposed: set[str]
    ) -> None:
        domain_names = {f.name for f in dataclass_fields(domain)}
        schema_names = set(schema.model_fields)

        missing = domain_names - schema_names - not_exposed
        assert not missing, (
            f"{domain.__name__} has field(s) {sorted(missing)} that "
            f"{schema.__name__} does not carry. Either add them to the schema and its "
            f"from_domain(), or add them to the 'not exposed' set in this test with a "
            f"reason. Nothing else enforces this pair."
        )

    @pytest.mark.parametrize(
        ("domain", "schema", "not_exposed"),
        _BOUNDARY,
        ids=[d.__name__ for d, _, _ in _BOUNDARY],
    )
    def test_the_not_exposed_list_does_not_go_stale(
        self, domain: type, schema: type, not_exposed: set[str]
    ) -> None:
        """A name listed as internal must still be a field of the dataclass."""
        domain_names = {f.name for f in dataclass_fields(domain)}
        stale = not_exposed - domain_names
        assert not stale, (
            f"{sorted(stale)} is listed as deliberately not exposed but is no longer a "
            f"field of {domain.__name__}. Remove it from this test."
        )


# @verifies REQ-0202
class TestNoNumpyCrossesTheBoundary:

    async def test_scenario_response_is_plain_json(self, reference_input, config) -> None:
        """The whole response must survive `json.dumps` with no custom encoder.

        numpy scalars are the failure this catches: they pass Pydantic's float
        validation, reach the client, and are read as something unexpected.
        """
        result = await run_scenario(reference_input, config)
        response = ScenarioResultResponse.from_domain(result)

        encoded = json.dumps(response.model_dump())
        assert json.loads(encoded)["summary"]["npv_eur"] == pytest.approx(
            result.finance.npv
        )

    async def test_arrays_become_lists(self, reference_input, config) -> None:
        result = await run_scenario(reference_input, config)
        response = ScenarioResultResponse.from_domain(result)

        assert isinstance(response.production.monthly_production_kwh, list)
        assert isinstance(response.finance.cashflows, list)
        assert all(
            type(v) is float for v in response.production.monthly_production_kwh
        ), "numpy scalars survived the conversion"


# @verifies REQ-0203
class TestOverridableConfigIsAClosedSet:

    # The exact set a caller may override. Widening it is a policy decision, so it is
    # written out rather than derived — the diff is the argument.
    EXPECTED_OVERRIDABLE = {
        "wacc",
        "retail_price",
        "sharing_ratio",
        "energy_inflation",
        "rid_tariff",
        "cer_tip",
        "cer_cacv",
        "load_profile",
        "detrazione_enabled",
        "detrazione_rate",
        "detrazione_years",
        "detrazione_include_iva",
        "cer_virtual_consumption_rate",
        "forced_tasso_autoconsumo",
    }

    def test_exact_overridable_set(self) -> None:
        actual = set(ConfigOverrides.model_fields)
        assert actual == self.EXPECTED_OVERRIDABLE, (
            "ConfigOverrides changed. Adding a field here lets a caller set that value "
            "per request; check it is not server policy before updating this test.\n"
            f"  added:   {sorted(actual - self.EXPECTED_OVERRIDABLE)}\n"
            f"  removed: {sorted(self.EXPECTED_OVERRIDABLE - actual)}"
        )

    @pytest.mark.parametrize(
        "server_policy_key",
        [
            "ires_rate",
            "irap_rate",
            "iva_rate",
            "ammortamento_rate",
            "useful_life",
            "degradation_rate",
        ],
    )
    def test_server_policy_is_not_overridable(self, server_policy_key: str) -> None:
        """Tax rates, depreciation and system lifetime are not caller input."""
        assert server_policy_key not in ConfigOverrides.model_fields

    def test_unknown_override_keys_are_rejected(self) -> None:
        """A caller cannot smuggle a policy value through an undeclared field."""
        overrides = ConfigOverrides(ires_rate=0.0)  # type: ignore[call-arg]
        assert "ires_rate" not in overrides.model_dump(exclude_none=True)


# @verifies REQ-0204
class TestOverridesDoNotMutateServerConfig:

    def test_base_config_is_untouched(self, config) -> None:
        from celine.roi.api.deps import apply_config_overrides

        before = dict(config)
        effective = apply_config_overrides(config, ConfigOverrides(wacc=0.123))

        assert effective["wacc"] == 0.123
        assert config == before, "apply_config_overrides mutated the shared server config"
