"""Command-line interface for CELINE ROI scenarios."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from celine.roi.config_loader import load_config
from celine.roi.main import run_scenario
from celine.roi.models import SystemInput
from celine.roi.report import format_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="celine-roi",
        description="CELINE ROI — Financial decision engine for Italian PV systems",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=Path("config"),
        help="Path to config directory with YAML files (default: config/)",
    )

    # System parameters
    parser.add_argument(
        "--kwp", type=float, default=0.0,
        help="Installed PV capacity (kWp). Auto-detected from rooftop polygon if --rooftop-wkt is used.",
    )
    parser.add_argument("--lat", type=float, required=True, help="Site latitude")
    parser.add_argument("--lon", type=float, required=True, help="Site longitude")
    parser.add_argument(
        "--tilt", type=float, default=30.0, help="Panel tilt (degrees, default: 30)"
    )
    parser.add_argument(
        "--azimuth", type=float, default=0.0, help="Panel azimuth (0=south, default: 0)"
    )
    parser.add_argument(
        "--capex", type=float, required=True, help="Total CAPEX in EUR (net of IVA)"
    )
    parser.add_argument("--consumption", type=float, required=True, help="Annual consumption (kWh)")
    parser.add_argument(
        "--user-type",
        default="commercial",
        choices=["residential", "office", "commercial", "industrial", "agricultural"],
        help="Consumer type (default: commercial)",
    )
    parser.add_argument(
        "--regime",
        default="RID_CER",
        choices=["RID", "CER", "RID_CER"],
        help="Incentive regime (default: RID_CER)",
    )

    # Financing
    parser.add_argument(
        "--equity-fraction",
        type=float,
        default=1.0,
        help="Equity share of CAPEX (1.0 = no loan, default: 1.0)",
    )
    parser.add_argument(
        "--loan-rate", type=float, default=0.0, help="Annual loan rate (default: 0)"
    )
    parser.add_argument(
        "--loan-duration", type=int, default=0, help="Loan duration in years (default: 0)"
    )

    # Optional overrides
    parser.add_argument(
        "--production",
        type=float,
        default=None,
        help="Manual annual production override (kWh, skips PVGIS)",
    )
    parser.add_argument("--location", type=str, default="", help="Site label (optional)")
    parser.add_argument(
        "--rooftop-wkt",
        type=str,
        default=None,
        help='WKT polygon of rooftop for Trentino Solar API (e.g., "POLYGON((lon lat, ...))")',
    )

    # Output
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Save report to markdown file (default: print to stdout)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run a CELINE ROI scenario from CLI arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Exit code (0 = success, 1 = validation failures).
    """
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config = load_config(args.config_dir)

    system_input = SystemInput(
        kwp=args.kwp,
        latitude=args.lat,
        longitude=args.lon,
        tilt=args.tilt,
        azimuth=args.azimuth,
        capex=args.capex,
        annual_consumption_kwh=args.consumption,
        user_type=args.user_type,
        regime=args.regime,
        equity_fraction=args.equity_fraction,
        loan_rate=args.loan_rate,
        loan_duration_years=args.loan_duration,
        annual_production_kwh=args.production,
        location=args.location,
        rooftop_wkt=args.rooftop_wkt,
    )

    result = asyncio.run(run_scenario(system_input, config))

    output = format_report(result, config)

    if args.output:
        args.output.write_text(output, encoding="utf-8")
        logging.info("Report saved to %s", args.output)
    else:
        print(output)

    return 1 if result.validation.fails else 0


if __name__ == "__main__":
    sys.exit(main())
