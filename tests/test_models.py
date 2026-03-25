"""Tests for data model dataclasses."""

import numpy as np
import pytest

from celine_roi.models import (
    EnergyResult,
    ProductionData,
    SystemInput,
    ValidationReport,
)


class TestSystemInput:
    """Tests for SystemInput dataclass."""

    def test_create_with_required_fields(self) -> None:
        si = SystemInput(
            kwp=45.0,
            latitude=45.9333,
            longitude=11.2667,
            tilt=30.0,
            azimuth=0.0,
            capex=45000.0,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
        )
        assert si.kwp == 45.0
        assert si.annual_production_kwh is None
        assert si.location == ""

    def test_create_with_manual_override(self) -> None:
        si = SystemInput(
            kwp=45.0,
            latitude=45.9333,
            longitude=11.2667,
            tilt=30.0,
            azimuth=0.0,
            capex=45000.0,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
            annual_production_kwh=49500.0,
            location="Lavarone, Trentino",
        )
        assert si.annual_production_kwh == 49500.0
        assert si.location == "Lavarone, Trentino"

    def test_frozen_immutability(self) -> None:
        si = SystemInput(
            kwp=45.0,
            latitude=45.9333,
            longitude=11.2667,
            tilt=30.0,
            azimuth=0.0,
            capex=45000.0,
            annual_consumption_kwh=40000.0,
            user_type="commercial",
            regime="RID_CER",
            equity_fraction=1.0,
            loan_rate=0.0,
            loan_duration_years=0,
        )
        with pytest.raises(AttributeError):
            si.kwp = 50.0  # type: ignore[misc]


class TestProductionData:
    """Tests for ProductionData dataclass."""

    def test_create(self) -> None:
        monthly = np.array([100.0] * 12)
        pd = ProductionData(
            monthly_production_kwh=monthly,
            annual_production_kwh=1200.0,
            source="synthetic",
        )
        assert pd.annual_production_kwh == 1200.0
        assert pd.source == "synthetic"
        assert len(pd.monthly_production_kwh) == 12


class TestEnergyResult:
    """Tests for EnergyResult dataclass."""

    def test_create(self) -> None:
        arr = np.zeros(12)
        er = EnergyResult(
            production=arr,
            consumption=arr,
            autoconsumo=arr,
            immissione=arr,
            prelievo=arr,
            energia_condivisa=arr,
            tasso_autoconsumo=0.0,
        )
        assert er.tasso_autoconsumo == 0.0


class TestValidationReport:
    """Tests for ValidationReport dataclass."""

    def test_create_empty(self) -> None:
        vr = ValidationReport(fails=[], warns=[], passes=[])
        assert len(vr.fails) == 0
        assert len(vr.warns) == 0
        assert len(vr.passes) == 0

    def test_create_with_entries(self) -> None:
        vr = ValidationReport(
            fails=[("ssp_check", "SSP abolished May 2025")],
            warns=[("degradation", "Degradation 0.2% below benchmark")],
            passes=[("energy_balance", "OK")],
        )
        assert len(vr.fails) == 1
        assert vr.fails[0][0] == "ssp_check"
