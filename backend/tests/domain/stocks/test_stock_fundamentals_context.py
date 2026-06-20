from __future__ import annotations

from datetime import date

from app.domain.stocks.assessment import evaluate_fundamentals_context
from app.repositories.fundamentals import FundamentalSnapshotRow
from app.repositories.relative_strength import RsRatingRow
from app.services.stocks import _fundamentals_context, _rs_context


def test_fundamentals_context_accepts_alternative_annual_growth_keys() -> None:
    row = _snapshot(
        metadata_json={
            "annual_eps_growth": [
                {"label": "2025", "growth_pct": 32.4},
                {"year": "2024", "annual_eps_growth_pct": 27.1},
                {"calendarYear": "2023", "eps_growth_yoy_pct": 45.8},
            ],
            "annual_revenue_growth": [
                {"label": "2025", "growth_pct": 25.4},
                {"year": "2024", "annual_revenue_growth_pct": 24.1},
                {"calendarYear": "2023", "revenue_growth_yoy_pct": 25.6},
            ],
        }
    )

    context = _fundamentals_context(row)
    checks, _, _ = evaluate_fundamentals_context(context)

    assert [item["fiscal_year"] for item in context["annual_eps_history"]] == ["2025", "2024", "2023"]
    assert [item["eps_growth_yoy_pct"] for item in context["annual_eps_history"]] == [32.4, 27.1, 45.8]
    assert [item["fiscal_year"] for item in context["annual_revenue_history"]] == ["2025", "2024", "2023"]
    assert [item["revenue_growth_yoy_pct"] for item in context["annual_revenue_history"]] == [25.4, 24.1, 25.6]
    assert _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY").passed is True
    assert _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY").passed is True


def test_fundamentals_context_exposes_legacy_annual_scalars_without_passing_three_year_rule() -> None:
    row = _snapshot(
        annual_eps_growth_pct=44.0,
        annual_revenue_growth_pct=35.0,
        metadata_json={},
    )

    context = _fundamentals_context(row)
    checks, _, _ = evaluate_fundamentals_context(context)
    eps_check = _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY")

    assert context["annual_eps_history"] == [
        {
            "fiscal_year": "2026",
            "eps_current_year": None,
            "eps_previous_year": None,
            "eps_growth_yoy_pct": 44.0,
            "flag": "legacy_scalar",
        }
    ]
    assert context["annual_revenue_history"] == [
        {
            "fiscal_year": "2026",
            "revenue_current_year": None,
            "revenue_previous_year": None,
            "revenue_growth_yoy_pct": 35.0,
            "flag": "legacy_scalar",
        }
    ]
    assert eps_check.passed is False
    assert "nur 1/3 Jahre verfügbar" in eps_check.detail
    assert revenue_check.passed is False
    assert "nur 1/3 Jahre verfügbar" in revenue_check.detail


def test_rs_context_maps_persisted_average_metadata_for_stock_assessment() -> None:
    context = _rs_context(
        RsRatingRow(
            ticker="NVDA",
            name="NVDA",
            date=date(2026, 6, 20),
            rating=92,
            score=0.42,
            percentile=94.0,
            method="test",
            source="computed",
            universe_size=100,
            metadata_json={
                "rs_line_last": 112.5,
                "rs_ema21_last": 110.0,
                "rs_sma50_last": 108.0,
                "rs_ema50_last": 107.0,
                "above_21": True,
                "above_50": True,
            },
        )
    )

    assert context["ema21"] == 110.0
    assert context["sma50"] == 108.0
    assert context["above_21"] is True
    assert context["above_50"] is True


def test_rs_context_falls_back_to_legacy_ema50_metadata() -> None:
    context = _rs_context(
        RsRatingRow(
            ticker="NVDA",
            name="NVDA",
            date=date(2026, 6, 20),
            rating=92,
            score=0.42,
            percentile=94.0,
            method="test",
            source="computed",
            universe_size=100,
            metadata_json={
                "rs_line_last": 112.5,
                "rs_ema21_last": 110.0,
                "rs_ema50_last": 107.0,
                "above_21": True,
                "above_50": True,
            },
        )
    )

    assert context["ema21"] == 110.0
    assert context["sma50"] == 107.0


def _snapshot(
    *,
    annual_eps_growth_pct: float | None = None,
    annual_revenue_growth_pct: float | None = None,
    metadata_json: dict,
) -> FundamentalSnapshotRow:
    return FundamentalSnapshotRow(
        ticker="TEST",
        as_of=date(2026, 6, 20),
        source="test",
        fiscal_period="",
        quarterly_eps_growth_pct=None,
        annual_eps_growth_pct=annual_eps_growth_pct,
        quarterly_revenue_growth_pct=None,
        annual_revenue_growth_pct=annual_revenue_growth_pct,
        roe_pct=None,
        profit_margin_pct=None,
        trailing_eps=None,
        quarterly_eps_accelerating=None,
        quarterly_revenue_accelerating=None,
        institutional_holders=None,
        institutional_ownership_pct=None,
        next_earnings_date=None,
        beta=None,
        metadata_json=metadata_json,
    )


def _check(checks, label: str):
    return next(check for check in checks if check.label == label)
