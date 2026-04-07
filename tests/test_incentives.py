"""Tests for incentive engine.

Reference values from design spec (year 1, after LID):
- Production after LID: 48,757.50 kWh
- Autoconsumo: 35,256.58 kWh → Risparmio: 8,814.14 EUR
- Immissione: 13,500.92 kWh → RID: 945.06 EUR
- Condivisa: 7,425.51 kWh → CER TIP: 668.30 EUR, Cacv: 63.12 EUR
- Ammortamento: 2,025.00 EUR → Tax shield: 486.00 EUR
- IRES+IRAP: 467.74 EUR
"""

import pytest

from celine.roi.engines.energy import compute_energy
from celine.roi.engines.incentives import compute_incentives
from celine.roi.models import IncentiveResult, ProductionData, SystemInput


@pytest.fixture()
def energy_result(
    reference_input: SystemInput, reference_production: ProductionData, config: dict
):
    """Pre-computed energy result for reference case."""
    return compute_energy(reference_input, reference_production, config)


class TestComputeIncentivesYear1:
    """Year 1 values against hand-calculated reference."""

    def test_returns_incentive_result(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert isinstance(result, IncentiveResult)

    def test_arrays_length_equals_useful_life(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert len(result.years) == config["useful_life"]

    def test_production_degraded_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        expected = 49500.0 * (1 - 0.015)
        assert result.production_degraded[0] == pytest.approx(expected, rel=1e-3)

    def test_risparmio_autoconsumo_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.risparmio_autoconsumo[0] == pytest.approx(8814.14, rel=1e-2)

    def test_rid_revenue_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.rid_revenue[0] == pytest.approx(945.06, rel=1e-2)

    def test_cer_tip_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.cer_tip[0] == pytest.approx(668.30, rel=1e-2)

    def test_cer_cacv_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.cer_cacv[0] == pytest.approx(63.12, rel=1e-2)

    def test_ammortamento_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento[0] == pytest.approx(2025.0, rel=1e-3)

    def test_tax_shield_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.tax_shield[0] == pytest.approx(486.0, rel=1e-3)

    def test_ires_irap_year1(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ires_irap[0] == pytest.approx(467.74, rel=1e-2)


class TestComputeIncentivesCER20Year:
    """CER incentive terminates after year 20."""

    def test_cer_tip_zero_after_year20(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.cer_tip[20:] == 0.0)

    def test_cer_cacv_zero_after_year20(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.cer_cacv[20:] == 0.0)

    def test_cer_tip_not_inflated(self, reference_input, energy_result, config) -> None:
        """CER TIP must be FIXED nominal — its ratio to cer_cacv must fall over time.

        Both cer_tip and cer_cacv share the same condivisa base each year.
        cer_tip uses a fixed tariff; cer_cacv is escalated by energy_inflation.
        Therefore cer_tip / cer_cacv must equal cer_tip_tariff / (cer_cacv_tariff * (1+inf)^(y-1)).
        If cer_tip were incorrectly inflated, the ratio would be constant instead of falling.
        """
        result = compute_incentives(reference_input, energy_result, config)
        cer_tip_tariff = config["cer_tip"]
        cer_cacv_tariff = config["cer_cacv"]
        inf = config["energy_inflation"]

        ratio_y1 = result.cer_tip[0] / result.cer_cacv[0]
        ratio_y10 = result.cer_tip[9] / result.cer_cacv[9]

        expected_y1 = cer_tip_tariff / (cer_cacv_tariff * (1 + inf) ** 0)
        expected_y10 = cer_tip_tariff / (cer_cacv_tariff * (1 + inf) ** 9)

        assert ratio_y1 == pytest.approx(expected_y1, rel=1e-4)
        assert ratio_y10 == pytest.approx(expected_y10, rel=1e-4)
        # Fixed-nominal means the ratio strictly decreases as cacv escalates
        assert ratio_y10 < ratio_y1


class TestComputeIncentivesDepreciation:
    """Depreciation schedule validation."""

    def test_depreciation_sums_to_capex(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento.sum() == pytest.approx(45000.0, rel=1e-3)

    def test_depreciation_zero_after_full(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.ammortamento[12:] == 0.0)

    def test_year2_depreciation_full_rate(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento[1] == pytest.approx(4050.0, rel=1e-3)


class TestComputeIncentivesDegradation:
    """Production degradation over system lifetime."""

    def test_production_decreases_over_time(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        assert result.production_degraded[-1] < result.production_degraded[0]

    def test_degradation_formula_year2(self, reference_input, energy_result, config) -> None:
        result = compute_incentives(reference_input, energy_result, config)
        expected = 49500.0 * (1 - 0.015) * (1 - 0.0045) ** 1
        assert result.production_degraded[1] == pytest.approx(expected, rel=1e-4)

    def test_autoconsumo_not_taxed(self, reference_input, energy_result, config) -> None:
        """IRES+IRAP must be computed on RID+CER only, never on risparmio."""
        result = compute_incentives(reference_input, energy_result, config)
        taxable_y1 = result.rid_revenue[0] + result.cer_tip[0] + result.cer_cacv[0]
        tax_rate = config["ires"] + config["irap"]
        expected_tax = taxable_y1 * tax_rate
        assert result.ires_irap[0] == pytest.approx(expected_tax, rel=1e-3)


class TestDetrazioneIrpef:
    """Tests for residential IRPEF tax deduction (Bonus Ristrutturazione)."""

    @pytest.fixture()
    def residential_input(self) -> SystemInput:
        """Small residential system eligible for detrazione."""
        return SystemInput(
            kwp=6.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=8400.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=True,
        )

    @pytest.fixture()
    def residential_energy(self, residential_input: SystemInput, config: dict):
        from celine.roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=7200.0 * SOLAR_MONTHLY_FRACTIONS,
            annual_production_kwh=7200.0,
            source="synthetic",
        )
        return compute_energy(residential_input, pd, config)

    def test_detrazione_primary_residence(
        self, residential_input, residential_energy, config,
    ) -> None:
        """Primary residence: 50% of CAPEX+IVA / 10 years."""
        result = compute_incentives(residential_input, residential_energy, config)
        iva_rate = config.get("iva_impianto", 0.10)
        expected = 8400.0 * (1.0 + iva_rate) * 0.50 / 10  # 462 EUR/year
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_detrazione_10_years_only(
        self, residential_input, residential_energy, config,
    ) -> None:
        """Detrazione runs for 10 years, then zero."""
        result = compute_incentives(residential_input, residential_energy, config)
        assert all(result.detrazione_irpef[:10] > 0)
        assert all(result.detrazione_irpef[10:] == 0.0)

    def test_detrazione_non_primary(self, residential_energy, config) -> None:
        """Non-primary residence: 36% rate instead of 50%, IVA-inclusive base."""
        si = SystemInput(
            kwp=6.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=8400.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=False,
        )
        result = compute_incentives(si, residential_energy, config)
        iva_rate = config.get("iva_impianto", 0.10)
        expected = 8400.0 * (1.0 + iva_rate) * 0.36 / 10  # 332.64 EUR/year
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_detrazione_cap_at_96000(self, residential_energy, config) -> None:
        """CAPEX above 96k capped at 96k for deduction base."""
        si = SystemInput(
            kwp=18.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=120000.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=True,
        )
        result = compute_incentives(si, residential_energy, config)
        expected = 96000.0 * 0.50 / 10  # 4800 EUR/year
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_no_detrazione_for_commercial(
        self, reference_input, energy_result, config,
    ) -> None:
        """Commercial user_type: no detrazione, has depreciation."""
        result = compute_incentives(reference_input, energy_result, config)
        assert all(result.detrazione_irpef == 0.0)
        assert result.ammortamento[0] > 0  # Business has depreciation

    def test_no_detrazione_over_20kwp(self, residential_energy, config) -> None:
        """Residential >20 kWp: not eligible for detrazione."""
        si = SystemInput(
            kwp=25.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=30000.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=True,
        )
        result = compute_incentives(si, residential_energy, config)
        assert all(result.detrazione_irpef == 0.0)

    def test_detrazione_disabled_override(
        self, residential_input, residential_energy, config,
    ) -> None:
        """detrazione_enabled=False disables deduction."""
        cfg = {**config, "detrazione_enabled": False}
        result = compute_incentives(residential_input, residential_energy, cfg)
        assert all(result.detrazione_irpef == 0.0)


class TestDepreciationGating:
    """Depreciation/tax_shield disabled for residential users."""

    def test_residential_no_depreciation(self, config) -> None:
        """Residential user_type should have zero ammortamento and tax_shield."""
        si = SystemInput(
            kwp=6.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=8400.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=True,
        )
        from celine.roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=7200.0 * SOLAR_MONTHLY_FRACTIONS,
            annual_production_kwh=7200.0,
            source="synthetic",
        )
        energy = compute_energy(si, pd, config)
        result = compute_incentives(si, energy, config)
        assert all(result.ammortamento == 0.0)
        assert all(result.tax_shield == 0.0)

    def test_commercial_has_depreciation(self, reference_input, energy_result, config) -> None:
        """Commercial user_type should still have depreciation (existing behavior)."""
        result = compute_incentives(reference_input, energy_result, config)
        assert result.ammortamento[0] > 0
        assert result.tax_shield[0] > 0


class TestDetrazioneConfigurable:
    """Tests for configurable detrazione rate and IVA inclusion."""

    @pytest.fixture()
    def residential_input(self) -> SystemInput:
        """Small residential system for detrazione tests."""
        return SystemInput(
            kwp=6.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=8400.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=True,
        )

    @pytest.fixture()
    def residential_energy(self, residential_input: SystemInput, config: dict):
        from celine.roi.pvgis_client import SOLAR_MONTHLY_FRACTIONS
        pd = ProductionData(
            monthly_production_kwh=7200.0 * SOLAR_MONTHLY_FRACTIONS,
            annual_production_kwh=7200.0,
            source="synthetic",
        )
        return compute_energy(residential_input, pd, config)

    def test_detrazione_rate_override(
        self, residential_input, residential_energy, config,
    ) -> None:
        """With detrazione_rate=0.40 in config, rate should be 40% regardless of abitazione_principale."""
        config_override = {**config, "detrazione_rate": 0.40}
        result = compute_incentives(residential_input, residential_energy, config_override)

        iva_rate = config.get("iva_impianto", 0.10)
        expected = 8400.0 * (1.0 + iva_rate) * 0.40 / 10
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_detrazione_rate_override_non_primary(
        self, residential_energy, config,
    ) -> None:
        """detrazione_rate should override even for non-primary residence."""
        si = SystemInput(
            kwp=6.0, latitude=45.9, longitude=11.3, tilt=30.0, azimuth=0.0,
            capex=8400.0, annual_consumption_kwh=3500.0, user_type="residential",
            regime="RID_CER", equity_fraction=1.0, loan_rate=0.0,
            loan_duration_years=0, annual_production_kwh=7200.0,
            abitazione_principale=False,
        )

        config_override = {**config, "detrazione_rate": 0.40}
        result = compute_incentives(si, residential_energy, config_override)

        iva_rate = config.get("iva_impianto", 0.10)
        expected = 8400.0 * (1.0 + iva_rate) * 0.40 / 10
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_detrazione_iva_excluded(
        self, residential_input, residential_energy, config,
    ) -> None:
        """With detrazione_include_iva=False, base should be CAPEX only (no IVA)."""
        config_no_iva = {**config, "detrazione_include_iva": False}
        result = compute_incentives(residential_input, residential_energy, config_no_iva)

        expected = 8400.0 * 0.50 / 10  # 420 EUR/year (no IVA multiplier)
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_detrazione_iva_included(
        self, residential_input, residential_energy, config,
    ) -> None:
        """With detrazione_include_iva=True (default), base should be CAPEX * (1 + IVA)."""
        config_with_iva = {**config, "detrazione_include_iva": True}
        result = compute_incentives(residential_input, residential_energy, config_with_iva)

        iva_rate = config.get("iva_impianto", 0.10)
        expected = 8400.0 * (1.0 + iva_rate) * 0.50 / 10  # 462 EUR/year
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)

    def test_detrazione_iva_excluded_with_rate_override(
        self, residential_input, residential_energy, config,
    ) -> None:
        """IVA exclusion should work together with rate override."""
        config_custom = {
            **config,
            "detrazione_include_iva": False,
            "detrazione_rate": 0.40,
        }
        result = compute_incentives(residential_input, residential_energy, config_custom)

        expected = 8400.0 * 0.40 / 10  # 336 EUR/year (no IVA, custom rate)
        assert result.detrazione_irpef[0] == pytest.approx(expected, rel=1e-3)


class TestCerVirtualRateMultiYear:
    """Verify cer_virtual_consumption_rate is applied in all 25 years."""

    def test_cer_virtual_rate_reduces_all_years(
        self, reference_input, energy_result, config,
    ) -> None:
        """CER TIP should be halved in ALL years when virtual rate is 0.5."""
        result_full = compute_incentives(reference_input, energy_result, config)

        config_half = {**config, "cer_virtual_consumption_rate": 0.5}
        result_half = compute_incentives(reference_input, energy_result, config_half)

        # Check year 1 AND year 10 (mid-life) — both should be ~50%
        for year_idx in [0, 9, 19]:
            if result_full.cer_tip[year_idx] > 0:
                ratio = result_half.cer_tip[year_idx] / result_full.cer_tip[year_idx]
                assert ratio == pytest.approx(0.5, rel=1e-3), (
                    f"Year {year_idx + 1}: CER TIP ratio {ratio:.4f}, expected 0.5"
                )
