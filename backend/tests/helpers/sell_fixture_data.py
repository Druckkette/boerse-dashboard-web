from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.repositories.portfolio import PortfolioPositionRow


FIXTURE_END_DATE = date(2026, 6, 5)
FIXTURE_PERIODS = 280


def fixture_positions() -> list[PortfolioPositionRow]:
    buy_date = fixture_price_dates()[-170].date()
    definitions = [
        ("NVDA", "NVIDIA", 100.0, 12.0, "profit"),
        ("PLTR", "Palantir", 70.0, 20.0, "losing"),
        ("EMAB", "EMA21 Break Setup", 100.0, 10.0, "ema21_break"),
        ("CLMX", "Climax Winner", 80.0, 8.0, "climax"),
    ]
    return [
        PortfolioPositionRow(
            ticker=ticker,
            name=name,
            shares=shares,
            entry_price=entry_price,
            current_price=float(build_fixture_price_frame(scenario)["Close"].iloc[-1]),
            currency="USD",
            buy_date=buy_date,
            broker="Fixture",
            account="Tests",
        )
        for ticker, name, entry_price, shares, scenario in definitions
    ]


def fixture_price_bars(ticker: str, *args, **kwargs) -> list[SimpleNamespace]:
    scenario = {
        "NVDA": "profit",
        "PLTR": "losing",
        "EMAB": "ema21_break",
        "CLMX": "climax",
        "SPY": "benchmark",
    }.get(ticker.upper(), "profit")
    frame = build_fixture_price_frame(scenario)
    return [
        SimpleNamespace(
            date=index.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            adj_close=float(row["Close"]),
            volume=float(row["Volume"]),
        )
        for index, row in frame.iterrows()
    ]


def build_fixture_price_frame(scenario: str) -> pd.DataFrame:
    dates = fixture_price_dates()
    close = _close_curve(scenario, len(dates))
    idx = np.arange(len(dates), dtype=float)
    open_ = close * (1 + 0.004 * np.sin(idx / 4.0))
    high = np.maximum(open_, close) * (1.012 + 0.003 * np.cos(idx / 8.0))
    low = np.minimum(open_, close) * (0.988 - 0.002 * np.sin(idx / 6.0))
    volume = 1_000_000 * (1 + 0.12 * np.sin(idx / 9.0) + 0.04 * np.cos(idx / 3.0))

    if scenario == "losing":
        volume[-30:] *= np.linspace(1.2, 1.8, 30)
    elif scenario == "ema21_break":
        volume[-8:] *= np.linspace(1.1, 1.7, 8)
    elif scenario == "climax":
        volume[-6:] *= [1.2, 1.4, 2.2, 2.8, 2.0, 2.5]

    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": np.maximum(volume, 100_000),
        },
        index=dates,
    )


def fixture_price_dates() -> pd.DatetimeIndex:
    return pd.bdate_range(end=pd.Timestamp(FIXTURE_END_DATE), periods=FIXTURE_PERIODS)


def _close_curve(scenario: str, periods: int) -> np.ndarray:
    if scenario == "benchmark":
        curve = np.linspace(380, 430, periods)
        curve[-20:] = np.linspace(curve[-21], 432, 20)
        return curve
    if scenario == "losing":
        curve = np.linspace(86, 61, periods)
        curve[-15:] = np.linspace(curve[-16] * 0.98, 58.2, 15)
        return curve
    if scenario == "ema21_break":
        curve = np.concatenate(
            [
                np.linspace(82, 132, periods - 28),
                np.linspace(135, 123, 18),
                np.linspace(121, 118.5, 10),
            ]
        )
        return curve[:periods]
    if scenario == "climax":
        curve = np.linspace(72, 144, periods)
        curve[-8:] = [145, 149, 154, 162, 171, 166, 169, 174]
        return curve
    curve = np.linspace(82, 134, periods)
    curve[-18:] = np.linspace(curve[-19], 138, 18)
    return curve
