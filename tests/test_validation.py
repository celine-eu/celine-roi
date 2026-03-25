"""Tests for model validation checks."""

import pytest

from celine_roi.engines.energy import compute_energy
from celine_roi.engines.finance import compute_finance
from celine_roi.engines.incentives import compute_incentives
from celine_roi.models import (
    ProductionData,
    SystemInput,
)
from celine_roi.validation.warnings import validate_model


@pytest.fixture()
def full_pipeline(reference_input, reference_production, config):
    """Run full pipeline and return all results."""
    energy = compute_energy(reference_input, reference_production, config)
    incentives = compute_incentives(reference_input, energy, config)
    finance = compute_finance(reference_input, incentives, config)
    return energy, incentives, finance


class TestValidateModelPasses:
    """Reference case should pass all checks."""

    def test_no_fails(self, reference_input, full_pipeline, config) -> None:
        energy, incentives, finance = full_pipeline
        report = validate_model(reference_input, energy, incentives, finance, config)
        assert len(report.fails) == 0, f"Unexpected FAILs: {report.fails}"

    def test_has_passes(self, reference_input, full_pipeline, config) -> None:
        energy, incentives, finance = full_pipeline
        report = validate_model(reference_input, energy, incentives, finance, config)
        assert len(report.passes) > 0


class TestValidateModelRegulatory:
    """Regulatory FAIL checks."""

    def test_ssp_regime_fails(self, config) -> None:
        si = SystemInput(
            kwp=45.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=45000.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="SSP", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=49500.0,
        )
        from celine_roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS
        monthly = 49500.0 * SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=49500.0,
            source="synthetic"
        )
        energy = compute_energy(si, pd, config)
        incentives = compute_incentives(si, energy, config)
        finance = compute_finance(si, incentives, config)
        report = validate_model(si, energy, incentives, finance, config)
        fail_names = [f[0] for f in report.fails]
        assert "ssp_abolished" in fail_names

    def test_zero_capex_fails(self, reference_production, config) -> None:
        si = SystemInput(
            kwp=45.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=0.0, annual_consumption_kwh=40000.0, user_type="commercial",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=49500.0,
        )
        energy = compute_energy(si, reference_production, config)
        incentives = compute_incentives(si, energy, config)
        finance = compute_finance(si, incentives, config)
        report = validate_model(si, energy, incentives, finance, config)
        fail_names = [f[0] for f in report.fails]
        assert "capex_invalid" in fail_names

    def test_zero_discount_rate_fails(self, reference_input, full_pipeline) -> None:
        energy, incentives, finance = full_pipeline
        bad_config = {"wacc": 0.0, "sharing_ratio": 0.55, "useful_life": 25,
                      "om_per_kwp": 12, "insurance_rate": 0.0035,
                      "inverter_replacement_year": 12,
                      "degradation": 0.0045, "cer_duration_years": 20}
        report = validate_model(reference_input, energy, incentives, finance, bad_config)
        fail_names = [f[0] for f in report.fails]
        assert "zero_discount_rate" in fail_names


class TestValidateModelWarnings:
    """Parameter WARN checks."""

    def test_low_degradation_warns(self, reference_input, full_pipeline) -> None:
        energy, incentives, finance = full_pipeline
        config_low_deg = {"degradation": 0.001, "wacc": 0.055, "sharing_ratio": 0.55,
                          "useful_life": 25, "om_per_kwp": 12, "insurance_rate": 0.0035,
                          "inverter_replacement_year": 12,
                          "cer_duration_years": 20}
        report = validate_model(reference_input, energy, incentives, finance, config_low_deg)
        warn_names = [w[0] for w in report.warns]
        assert "low_degradation" in warn_names


class TestValidateModelInvariants:
    """Invariant checks."""

    def test_energy_balance_passes(self, reference_input, full_pipeline, config) -> None:
        energy, incentives, finance = full_pipeline
        report = validate_model(reference_input, energy, incentives, finance, config)
        pass_names = [p[0] for p in report.passes]
        assert "energy_balance" in pass_names

    def test_depreciation_cap_passes(self, reference_input, full_pipeline, config) -> None:
        energy, incentives, finance = full_pipeline
        report = validate_model(reference_input, energy, incentives, finance, config)
        pass_names = [p[0] for p in report.passes]
        assert "depreciation_cap" in pass_names
