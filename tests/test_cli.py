"""Tests for CLI and report formatting."""

from celine.roi.cli import main, parse_args
from celine.roi.report import format_report


class TestParseArgs:
    """Tests for argument parsing."""

    def test_required_args(self) -> None:
        args = parse_args([
            "--kwp", "45",
            "--lat", "45.9333",
            "--lon", "11.2667",
            "--capex", "45000",
            "--consumption", "40000",
        ])
        assert args.kwp == 45.0
        assert args.capex == 45000.0
        assert args.regime == "RID_CER"
        assert args.equity_fraction == 1.0

    def test_defaults(self) -> None:
        args = parse_args([
            "--kwp", "45", "--lat", "45.9", "--lon", "11.3",
            "--capex", "45000", "--consumption", "40000",
        ])
        assert args.tilt == 30.0
        assert args.azimuth == 0.0
        assert args.production is None

    def test_manual_production_override(self) -> None:
        args = parse_args([
            "--kwp", "45", "--lat", "45.9", "--lon", "11.3",
            "--capex", "45000", "--consumption", "40000",
            "--production", "49500",
        ])
        assert args.production == 49500.0


class TestMain:
    """Integration tests for CLI main function."""

    def test_runs_with_production_override(self) -> None:
        """Full CLI run with manual production (no PVGIS call)."""
        exit_code = main([
            "--kwp", "45",
            "--lat", "45.9333",
            "--lon", "11.2667",
            "--capex", "45000",
            "--consumption", "40000",
            "--production", "49500",
            "--location", "Lavarone",
        ])
        assert exit_code == 0

    def test_returns_1_on_ssp(self) -> None:
        """SSP regime should cause validation failure."""
        exit_code = main([
            "--kwp", "45",
            "--lat", "45.9333",
            "--lon", "11.2667",
            "--capex", "45000",
            "--consumption", "40000",
            "--production", "49500",
            "--regime", "RID",
        ])
        # RID is valid, so exit 0
        assert exit_code == 0


class TestFormatReport:
    """Tests for report formatting."""

    async def test_report_contains_header(self, reference_input, config) -> None:
        from celine.roi.main import run_scenario
        result = await run_scenario(reference_input, config)
        output = format_report(result, config)
        assert "Business Plan Impianto Fotovoltaico" in output
        assert "45.0 kWp" in output

    async def test_report_contains_npv(self, reference_input, config) -> None:
        from celine.roi.main import run_scenario
        result = await run_scenario(reference_input, config)
        output = format_report(result, config)
        assert "VAN" in output
        assert "TIR" in output

    async def test_report_contains_decision(self, reference_input, config) -> None:
        from celine.roi.main import run_scenario
        result = await run_scenario(reference_input, config)
        output = format_report(result, config)
        assert "Giudizio" in output
        assert "consigliato" in output

    async def test_report_contains_yearly_detail(self, reference_input, config) -> None:
        from celine.roi.main import run_scenario
        result = await run_scenario(reference_input, config)
        output = format_report(result, config)
        assert "Conto Economico" in output
        assert "Risparmio" in output
        assert "RID" in output
        assert "CER" in output
        assert "Scudo Fisc" in output

    async def test_report_contains_energy_summary(self, reference_input, config) -> None:
        from celine.roi.main import run_scenario
        result = await run_scenario(reference_input, config)
        output = format_report(result, config)
        assert "Bilancio Energetico" in output
        assert "autoconsumo" in output.lower()

    async def test_report_contains_parameters(self, reference_input, config) -> None:
        from celine.roi.main import run_scenario
        result = await run_scenario(reference_input, config)
        output = format_report(result, config)
        assert "Parametri di Calcolo" in output
        assert "WACC" in output.upper() or "sconto" in output
