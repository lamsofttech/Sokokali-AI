"""Print a walk-forward backtest of the prediction model.

Run from the ``backend`` directory:  python -m app.evaluate [--warmup 20] [--refit-every 1] [--calibration]
Uses whichever sports provider is configured (simulated by default).
"""

import argparse
import asyncio
import logging

from app.core.config import get_settings
from app.core.container import build_container
from app.services.backtest import BacktestReport


def render(report: BacktestReport, show_calibration: bool = False, source: str = "") -> str:
    lines = [
        f"Backtest on {report.matches_evaluated} matches from {', '.join(report.competitions) or 'no competitions'}"
        + (f" [{source}]" if source else ""),
        f"Warm-up {report.warmup_matches} matches per competition; blend = {report.poisson_weight:.0%} Poisson",
        "Outcomes: home {home_win:.0%}, draw {draw:.0%}, away {away_win:.0%}".format(**report.outcome_frequencies),
        "",
        f"{'model':<10}{'log loss':>10}{'Brier':>10}{'accuracy':>10}",
    ]
    for m in report.metrics:
        lines.append(f"{m.model:<10}{m.log_loss:>10.4f}{m.brier_score:>10.4f}{m.accuracy:>10.1%}")
    if report.metrics:
        lines.append("")
        lines.append(f"Best by log loss: {report.best_model()} (lower log loss and Brier are better)")
    if show_calibration:
        for m in report.metrics:
            lines += ["", f"Calibration - {m.model} (predicted vs observed, count)"]
            for b in m.calibration:
                lines.append(
                    f"  {b.lower:.1f}-{b.upper:.1f}: {b.mean_predicted:6.1%} vs {b.observed_frequency:6.1%}  ({b.count})"
                )
    return "\n".join(lines)


async def _run(warmup: int, refit_every: int, calibration: bool) -> None:
    logging.disable(logging.CRITICAL)
    container = build_container(get_settings())
    try:
        report = await container.predictions.evaluate(warmup_matches=warmup, refit_every=refit_every)
        provider = container.sports_provider
        print(render(report, calibration, "SIMULATED data" if provider.is_simulated else provider.name))
    finally:
        await container.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the Sokokali football prediction model")
    parser.add_argument("--warmup", type=int, default=20, help="matches per competition used only for training")
    parser.add_argument("--refit-every", type=int, default=1, help="refit the model every N matches")
    parser.add_argument("--calibration", action="store_true", help="also print calibration tables")
    args = parser.parse_args()
    asyncio.run(_run(args.warmup, args.refit_every, args.calibration))


if __name__ == "__main__":
    main()
