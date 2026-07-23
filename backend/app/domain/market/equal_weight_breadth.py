from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from math import isfinite
from typing import Literal

from app.domain.market.constants import EQUAL_WEIGHT_MARKET_TICKERS


EqualWeightBreadthMode = Literal["schutz", "wachsam", "rueckenwind"]

CONFIRMATION_DAYS = 3
LOOKBACK_TRADING_DAYS = 252
RUECKENWIND_MAX_DRAWDOWN_PCT = 4.0
WACHSAM_MAX_DRAWDOWN_PCT = 8.0


@dataclass(frozen=True)
class EqualWeightTickerStatus:
    ticker: str
    close: float
    high_52w: float
    distance_from_high_pct: float
    drawdown_from_high_pct: float


@dataclass(frozen=True)
class EqualWeightBreadthStatus:
    mode: EqualWeightBreadthMode
    candidate_mode: EqualWeightBreadthMode
    as_of: str
    source: Literal["database", "missing", "insufficient"]
    tickers: list[str]
    ticker_status: list[EqualWeightTickerStatus]
    worst_drawdown_pct: float | None
    confirmation_days: int
    candidate_streak: int
    message: str
    rule: str

    def to_dict(self) -> dict:
        return asdict(self)


def compute_equal_weight_breadth_status(
    series: Mapping[str, Sequence[object]],
    *,
    tickers: Sequence[str] = EQUAL_WEIGHT_MARKET_TICKERS,
    lookback_trading_days: int = LOOKBACK_TRADING_DAYS,
    confirmation_days: int = CONFIRMATION_DAYS,
) -> EqualWeightBreadthStatus:
    """Classify RSP/QQEW breadth by distance from the rolling 52-week high.

    The public labels Rückenwind/Wachsam/Schutz intentionally belong only to
    this equal-weight breadth check. The status changes only after the same
    candidate mode was seen on three consecutive trading days.
    """

    clean_tickers = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    if not clean_tickers:
        return missing_equal_weight_breadth_status("Keine Equal-Weight-Ticker konfiguriert.", tickers=[])

    daily_status_by_date: dict[date, dict[str, EqualWeightTickerStatus]] = {}
    missing_tickers: list[str] = []
    for ticker in clean_tickers:
        points = sorted(series.get(ticker, []), key=lambda item: getattr(item, "date", date.min))
        rolling_highs: list[float] = []
        ticker_has_data = False
        for point in points:
            point_date = getattr(point, "date", None)
            close = _finite_positive(getattr(point, "close", None))
            high = _finite_positive(getattr(point, "high", close))
            if point_date is None or close is None or high is None:
                continue
            ticker_has_data = True
            rolling_highs.append(max(high, close))
            if len(rolling_highs) > lookback_trading_days:
                rolling_highs.pop(0)
            high_52w = max(rolling_highs)
            distance_pct = (close / high_52w - 1.0) * 100.0
            drawdown_pct = max(0.0, -distance_pct)
            daily_status_by_date.setdefault(point_date, {})[ticker] = EqualWeightTickerStatus(
                ticker=ticker,
                close=round(close, 4),
                high_52w=round(high_52w, 4),
                distance_from_high_pct=round(distance_pct, 2),
                drawdown_from_high_pct=round(drawdown_pct, 2),
            )
        if not ticker_has_data:
            missing_tickers.append(ticker)

    dates = [
        current_date
        for current_date, status_by_ticker in sorted(daily_status_by_date.items())
        if all(ticker in status_by_ticker for ticker in clean_tickers)
    ]
    if missing_tickers or not dates:
        missing = ", ".join(missing_tickers) if missing_tickers else ", ".join(clean_tickers)
        return missing_equal_weight_breadth_status(
            f"Keine ausreichenden RSP/QQEW-Kursdaten im Price Cache: {missing}.",
            tickers=clean_tickers,
        )

    confirmed_mode: EqualWeightBreadthMode | None = None
    current_candidate: EqualWeightBreadthMode | None = None
    current_streak = 0
    latest_candidate: EqualWeightBreadthMode = "wachsam"
    latest_status: list[EqualWeightTickerStatus] = []
    latest_worst_drawdown: float | None = None

    for current_date in dates:
        ticker_status = [daily_status_by_date[current_date][ticker] for ticker in clean_tickers]
        worst_drawdown = max(item.drawdown_from_high_pct for item in ticker_status)
        candidate = classify_equal_weight_drawdown(worst_drawdown)
        if candidate == current_candidate:
            current_streak += 1
        else:
            current_candidate = candidate
            current_streak = 1
        if current_streak >= confirmation_days:
            confirmed_mode = candidate
        latest_candidate = candidate
        latest_status = ticker_status
        latest_worst_drawdown = worst_drawdown

    latest_date = dates[-1]
    if confirmed_mode is None:
        return EqualWeightBreadthStatus(
            mode="wachsam",
            candidate_mode=latest_candidate,
            as_of=latest_date.isoformat(),
            source="insufficient",
            tickers=clean_tickers,
            ticker_status=latest_status,
            worst_drawdown_pct=latest_worst_drawdown,
            confirmation_days=confirmation_days,
            candidate_streak=current_streak,
            message=(
                "Equal-Weight-Breite noch nicht bestätigt: "
                f"{latest_candidate} erst {current_streak}/{confirmation_days} Handelstage."
            ),
            rule=_rule_text(confirmation_days),
        )

    return EqualWeightBreadthStatus(
        mode=confirmed_mode,
        candidate_mode=latest_candidate,
        as_of=latest_date.isoformat(),
        source="database",
        tickers=clean_tickers,
        ticker_status=latest_status,
        worst_drawdown_pct=latest_worst_drawdown,
        confirmation_days=confirmation_days,
        candidate_streak=current_streak,
        message=_status_message(confirmed_mode, latest_candidate, current_streak, confirmation_days),
        rule=_rule_text(confirmation_days),
    )


def classify_equal_weight_drawdown(worst_drawdown_pct: float | None) -> EqualWeightBreadthMode:
    if worst_drawdown_pct is None:
        return "wachsam"
    if worst_drawdown_pct <= RUECKENWIND_MAX_DRAWDOWN_PCT:
        return "rueckenwind"
    if worst_drawdown_pct <= WACHSAM_MAX_DRAWDOWN_PCT:
        return "wachsam"
    return "schutz"


def missing_equal_weight_breadth_status(
    message: str,
    *,
    tickers: Sequence[str] = EQUAL_WEIGHT_MARKET_TICKERS,
) -> EqualWeightBreadthStatus:
    clean_tickers = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    return EqualWeightBreadthStatus(
        mode="wachsam",
        candidate_mode="wachsam",
        as_of="",
        source="missing",
        tickers=clean_tickers,
        ticker_status=[],
        worst_drawdown_pct=None,
        confirmation_days=CONFIRMATION_DAYS,
        candidate_streak=0,
        message=message,
        rule=_rule_text(CONFIRMATION_DAYS),
    )


def _finite_positive(value: object) -> float | None:
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not isfinite(result) or result <= 0:
        return None
    return result


def _status_message(
    confirmed_mode: EqualWeightBreadthMode,
    latest_candidate: EqualWeightBreadthMode,
    current_streak: int,
    confirmation_days: int,
) -> str:
    if confirmed_mode == latest_candidate:
        return (
            "Marktbreite Gleichgewichtete Indizes bestätigt: "
            f"{_mode_label(confirmed_mode)} seit {current_streak} Handelstagen."
        )
    return (
        "Marktbreite Gleichgewichtete Indizes bleibt noch bei "
        f"{_mode_label(confirmed_mode)}; {_mode_label(latest_candidate)} erst "
        f"{current_streak}/{confirmation_days} Handelstage."
    )


def _mode_label(mode: EqualWeightBreadthMode) -> str:
    return {
        "rueckenwind": "Rückenwind",
        "wachsam": "Wachsam",
        "schutz": "Schutz",
    }[mode]


def _rule_text(confirmation_days: int) -> str:
    return (
        "Status nur für Marktbreite Gleichgewichtete Indizes (RSP, QQEW): "
        "Rückenwind <= 4% unter 52W-Hoch, Wachsam > 4% bis 8%, Schutz > 8%; "
        f"Aktivierung nach {confirmation_days} bestätigten Handelstagen."
    )
