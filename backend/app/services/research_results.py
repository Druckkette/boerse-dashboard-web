"""Verified, public, immutable research artifacts. Never reads private exports."""
import csv
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from statistics import mean

DIRECTORY = Path(__file__).resolve().parents[1] / "research" / "public"


@lru_cache(maxsize=1)
def research_results() -> dict:
    manifest = json.loads((DIRECTORY / "manifest.json").read_text())
    for name, expected in manifest["files"].items():
        if name not in {"sell-summary.csv", "recommendation-events.csv"} or hashlib.sha256((DIRECTORY / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Forschungsartefakt stimmt nicht mit der veröffentlichten Prüfsumme überein.")
    def read(name):
        with (DIRECTORY / name).open() as stream:
            return list(csv.DictReader(stream))
    events = read("recommendation-events.csv")
    horizons = []
    for horizon in [1, 5, 10, 20, 63]:
        usable = [row for row in events if row.get(f"return_{horizon}d_pct")]
        for bps in [0, 10, 25]:
            stock = [float(row[f"net_{horizon}d_{bps}bps_pct"]) for row in usable]
            benchmark = [((1 + float(row[f"spy_{horizon}d_pct"]) / 100) * (1 - bps / 10000) / (1 + bps / 10000) - 1) * 100 for row in usable]
            horizons.append(dict(sessions=horizon, bps=bps, observations=len(usable), recommendation_days=len({row["as_of"] for row in usable}),
                tickers=len({row["ticker"] for row in usable}), stock_net_pct=mean(stock) if stock else None,
                benchmark_net_pct=mean(benchmark) if benchmark else None,
                excess_pp=mean([left - right for left, right in zip(stock, benchmark)]) if stock else None))
    summary = []
    for row in read("sell-summary.csv"):
        numeric = {key: float(value) for key, value in row.items() if key not in {"sample", "strategy", "first_entry", "last_end"} and value}
        for benchmark in ["mean_buy_hold_pct", "mean_spy_pct"]:
            if benchmark in numeric:
                numeric[benchmark] = ((1 + numeric[benchmark] / 100) * (1 - 10 / 10000) / (1 + 10 / 10000) - 1) * 100
        summary.append({**row, **numeric})
    return dict(manifest=manifest, horizons=horizons, sell_summary=summary,
        notes=["Echte archivierte Empfehlungen beginnen am 22.09.2026. Offene Horizonte bleiben offen.",
               "Kostenvergleich für Aktien und SPY mit denselben Basispunkten je Kauf und Verkauf.",
               "Wiederkehrende Aktien und überlappende Zeiträume sind abhängig. Keine Jahresrendite und kein zusammengesetztes Depot.",
               "Die ergänzende Ausstiegskohorte verwendet das heutige Universum und enthält Survivorship-Bias.",
               "Preisrenditen ohne Dividenden, Steuern, FX oder Intraday-Stoppausführungen. Keine nachträgliche Parameteroptimierung."])
