from __future__ import annotations

from datetime import date, timedelta

from app.domain.stocks.assessment import StockAssessmentBar, compute_stock_assessment, evaluate_fundamentals_context


def test_stock_assessment_scores_constructive_leader() -> None:
    bars = _synthetic_bars(start_price=35, drift=0.004, volume=2_500_000)
    result = compute_stock_assessment(
        "LEAD",
        bars,
        rs_context={
            "rating": 92,
            "percentile": 94.0,
            "above_21": True,
            "above_50": True,
            "trend_5w": True,
            "trend_13w": True,
            "near_high_52w": True,
            "new_high_52w": True,
            "excess_return_3m_pct": 18.0,
            "excess_return_6m_pct": 32.0,
        },
    )

    assert result.source == "database"
    assert result.scores.overall >= 60
    assert result.scores.technical >= 60
    assert result.metrics.rs_rating == 92
    assert any(check.label == "RS-Bewertung >=80" and check.passed for check in result.checks)
    assert result.drivers


def test_stock_assessment_flags_weak_position() -> None:
    bars = _synthetic_bars(start_price=80, drift=-0.003, volume=180_000)
    result = compute_stock_assessment(
        "WEAK",
        bars,
        rs_context={
            "rating": 38,
            "percentile": 30.0,
            "above_21": False,
            "above_50": False,
            "trend_5w": False,
            "trend_13w": False,
            "near_high_52w": False,
            "distance_to_high_pct": -24.0,
        },
    )

    assert result.scores.overall < 60
    assert result.verdict_tone in {"warning", "bad"}
    assert any("Dollar-Volumen" in warning for warning in result.warnings)
    assert any(signal.category == "negative" for signal in result.chart_signals)


def test_stock_assessment_places_price_and_high_distance_in_technical_checks() -> None:
    bars = _synthetic_bars(start_price=35, drift=0.004, volume=2_500_000)
    prior_high = max(bar.high or 0 for bar in bars[:-1])
    last = bars[-1]
    close = round(prior_high * 1.02, 2)
    bars[-1] = StockAssessmentBar(
        date=last.date,
        open=last.open,
        high=round(close * 1.01, 2),
        low=last.low,
        close=close,
        volume=last.volume,
    )

    result = compute_stock_assessment("HIGH", bars)
    checks = {check.label: check for check in result.checks}
    labels = [check.label for check in result.checks]

    assert checks["Preis >= $15"].category == "technical"
    assert checks["Dollar-Volumen >= $30 Mio."].category == "technical"
    assert labels.index("Dollar-Volumen >= $30 Mio.") == labels.index("Preis >= $15") + 1
    assert checks["Entfernung zum All-Time-High"].category == "technical"
    assert checks["Entfernung zum All-Time-High"].passed is True
    assert checks["Entfernung zum 52-Wochen-Hoch"].category == "technical"
    assert checks["Entfernung zum 52-Wochen-Hoch"].passed is True
    assert "Nahe am 52W-Hoch" not in checks


def test_stock_assessment_missing_payload_is_stable() -> None:
    result = compute_stock_assessment("MISS", [])

    assert result.source == "missing"
    assert result.data_status == "missing"
    assert result.verdict_label == "Nicht bewertbar"
    assert result.scores.overall == 0
    assert result.warnings


def test_stock_assessment_uses_cached_fundamentals() -> None:
    bars = _synthetic_bars(start_price=45, drift=0.0035, volume=3_000_000)
    result = compute_stock_assessment(
        "FUND",
        bars,
        rs_context={"rating": 88, "above_21": True, "above_50": True, "trend_5w": True, "trend_13w": True},
        fundamentals_context={
            "ticker": "FUND",
            "as_of": "2026-06-01",
            "source": "manual",
            "fiscal_period": "Q1 2026",
            "quarterly_eps_growth_pct": 65.0,
            "eps_quarter_history": _eps_history([65.0, 42.0, 31.0]),
            "annual_eps_growth_pct": 48.0,
            "annual_eps_history": _annual_eps_history([48.0, 32.0, 26.0]),
            "quarterly_revenue_growth_pct": 36.0,
            "revenue_quarter_history": _revenue_history([36.0, 29.0, 24.0]),
            "annual_revenue_growth_pct": 31.0,
            "annual_revenue_history": _annual_revenue_history([31.0, 28.0, 25.0]),
            "roe_pct": 28.0,
            "roe_history": _roe_history([28.0, 22.0, 18.0]),
            "profit_margin_pct": 18.0,
            "trailing_eps": 3.42,
            "quarterly_eps_accelerating": True,
            "quarterly_revenue_accelerating": True,
            "beta": 1.25,
        },
        institutional_context={
            "report_period": "2025-12-31",
            "holder_count": 22,
            "holder_count_delta": 3,
            "large_holder_count": 12,
            "large_holder_delta": 2,
            "trend": "positive",
        },
    )

    assert result.fundamentals_available is True
    assert result.scores.fundamental > 70
    assert result.metrics.beta == 1.25
    assert any(check.label == "ROE >=17% über letzte 3 Jahre" and check.passed for check in result.checks)
    assert any("ROE" in driver or "EPS" in driver for driver in result.drivers)


def test_eps_three_quarter_rule_passes_only_when_all_three_quarters_clear_threshold() -> None:
    checks, score, available = evaluate_fundamentals_context({"eps_quarter_history": _eps_history([32.4, 27.1, 45.8])})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert available is True
    assert eps_check.passed is True
    assert "Q1 +32.4%" in eps_check.detail
    assert "Q2 +27.1%" in eps_check.detail
    assert "Q3 +45.8%" in eps_check.detail
    assert "alle >=20%" in eps_check.detail
    assert score > 0


def test_eps_three_quarter_rule_fails_when_one_quarter_is_below_threshold() -> None:
    checks, _, _ = evaluate_fundamentals_context({"eps_quarter_history": _eps_history([32.4, 12.1, 45.8])})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert eps_check.passed is False
    assert "Q2 unter 20%" in eps_check.detail


def test_eps_three_quarter_rule_fails_when_less_than_three_quarters_are_available() -> None:
    checks, _, _ = evaluate_fundamentals_context({"eps_quarter_history": _eps_history([32.4, 27.1])})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert eps_check.passed is False
    assert "nur 2/3 Quartale verfügbar" in eps_check.detail


def test_eps_three_quarter_rule_handles_invalid_prior_year_eps_without_division_error() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {
            "eps_quarter_history": [
                {"fiscal_period": "Q1", "eps_current_quarter": 1.32, "eps_same_quarter_last_year": 1.00},
                {"fiscal_period": "Q2", "eps_current_quarter": 1.25, "eps_same_quarter_last_year": 0.0},
                {"fiscal_period": "Q3", "eps_current_quarter": 1.40, "eps_same_quarter_last_year": -0.25},
            ]
        }
    )

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert eps_check.passed is False
    assert "Q2, Q3 nicht auswertbar" in eps_check.detail


def test_eps_three_quarter_rule_does_not_pass_with_only_legacy_single_quarter_growth() -> None:
    checks, _, available = evaluate_fundamentals_context({"quarterly_eps_growth_pct": 80.0})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert available is True
    assert eps_check.passed is False
    assert "keine EPS-Quartalshistorie" in eps_check.detail


def test_annual_eps_three_year_rule_passes_only_when_all_three_years_clear_threshold() -> None:
    checks, score, available = evaluate_fundamentals_context({"annual_eps_history": _annual_eps_history([32.4, 27.1, 45.8])})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert available is True
    assert eps_check.passed is True
    assert "2025 +32.4%" in eps_check.detail
    assert "2024 +27.1%" in eps_check.detail
    assert "2023 +45.8%" in eps_check.detail
    assert "alle >=20%" in eps_check.detail
    assert score > 0


def test_annual_eps_three_year_rule_fails_when_one_year_is_below_threshold() -> None:
    checks, _, _ = evaluate_fundamentals_context({"annual_eps_history": _annual_eps_history([32.4, 12.1, 45.8])})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert eps_check.passed is False
    assert "2024 unter 20%" in eps_check.detail


def test_annual_eps_three_year_rule_fails_when_less_than_three_years_are_available() -> None:
    checks, _, _ = evaluate_fundamentals_context({"annual_eps_history": _annual_eps_history([32.4, 27.1])})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert eps_check.passed is False
    assert "nur 2/3 Jahre verfügbar" in eps_check.detail


def test_annual_eps_three_year_rule_handles_invalid_prior_year_eps_without_division_error() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {
            "annual_eps_history": [
                {"fiscal_year": "2025", "eps_current_year": 7.2, "eps_previous_year": 5.2},
                {"fiscal_year": "2024", "eps_current_year": 5.2, "eps_previous_year": 0.0},
                {"fiscal_year": "2023", "eps_current_year": 3.4, "eps_previous_year": -1.0},
            ]
        }
    )

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert eps_check.passed is False
    assert "2024, 2023 nicht auswertbar" in eps_check.detail


def test_annual_eps_three_year_rule_does_not_pass_with_only_legacy_single_year_growth() -> None:
    checks, _, available = evaluate_fundamentals_context({"annual_eps_growth_pct": 80.0})

    eps_check = _check(checks, "EPS-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert available is True
    assert eps_check.passed is False
    assert "keine jährliche EPS-Historie" in eps_check.detail


def test_trailing_eps_sum_last_four_quarters_must_be_positive() -> None:
    checks, _, _ = evaluate_fundamentals_context({"trailing_eps": 0.25})
    assert _check(checks, "Summe EPS letzte 4 Quartale > 0").passed is True

    checks, _, _ = evaluate_fundamentals_context({"trailing_eps": -0.01})
    trailing_check = _check(checks, "Summe EPS letzte 4 Quartale > 0")
    assert trailing_check.passed is False
    assert "$-0.01" in trailing_check.detail


def test_eps_acceleration_bonus_uses_last_three_quarter_growth_rates() -> None:
    checks, _, _ = evaluate_fundamentals_context({"eps_quarter_history": _eps_history([40.0, 25.0, 20.0])})

    accel_check = _check(checks, "Bonus: EPS-Beschleunigung letzte 3 Quartale")
    assert accel_check.passed is True
    assert "Bonus erfüllt" in accel_check.detail


def test_revenue_three_quarter_rule_passes_only_when_all_three_quarters_clear_threshold() -> None:
    checks, score, available = evaluate_fundamentals_context(
        {"revenue_quarter_history": _revenue_history([32.4, 27.1, 45.8])}
    )

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert available is True
    assert revenue_check.passed is True
    assert "Q1 +32.4%" in revenue_check.detail
    assert "Q2 +27.1%" in revenue_check.detail
    assert "Q3 +45.8%" in revenue_check.detail
    assert "alle >=20%" in revenue_check.detail
    assert score > 0


def test_revenue_three_quarter_rule_fails_when_one_quarter_is_below_threshold() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {"revenue_quarter_history": _revenue_history([32.4, 12.1, 45.8])}
    )

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert revenue_check.passed is False
    assert "Q2 unter 20%" in revenue_check.detail


def test_revenue_three_quarter_rule_fails_when_less_than_three_quarters_are_available() -> None:
    checks, _, _ = evaluate_fundamentals_context({"revenue_quarter_history": _revenue_history([32.4, 27.1])})

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert revenue_check.passed is False
    assert "nur 2/3 Quartale verfügbar" in revenue_check.detail


def test_revenue_three_quarter_rule_handles_invalid_prior_year_revenue_without_division_error() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {
            "revenue_quarter_history": [
                {"fiscal_period": "Q1", "revenue_current_quarter": 132.0, "revenue_same_quarter_last_year": 100.0},
                {"fiscal_period": "Q2", "revenue_current_quarter": 125.0, "revenue_same_quarter_last_year": 0.0},
                {"fiscal_period": "Q3", "revenue_current_quarter": 140.0, "revenue_same_quarter_last_year": -25.0},
            ]
        }
    )

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert revenue_check.passed is False
    assert "Q2, Q3 nicht auswertbar" in revenue_check.detail


def test_revenue_three_quarter_rule_does_not_pass_with_only_legacy_single_quarter_growth() -> None:
    checks, _, available = evaluate_fundamentals_context({"quarterly_revenue_growth_pct": 80.0})

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Quartale jeweils >=20% YoY")
    assert available is True
    assert revenue_check.passed is False
    assert "keine Umsatz-Quartalshistorie" in revenue_check.detail


def test_annual_revenue_three_year_rule_passes_only_when_all_three_years_clear_threshold() -> None:
    checks, score, available = evaluate_fundamentals_context(
        {"annual_revenue_history": _annual_revenue_history([32.4, 27.1, 45.8])}
    )

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert available is True
    assert revenue_check.passed is True
    assert "2025 +32.4%" in revenue_check.detail
    assert "2024 +27.1%" in revenue_check.detail
    assert "2023 +45.8%" in revenue_check.detail
    assert "alle >=20%" in revenue_check.detail
    assert score > 0


def test_annual_revenue_three_year_rule_fails_when_one_year_is_below_threshold() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {"annual_revenue_history": _annual_revenue_history([32.4, 12.1, 45.8])}
    )

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert revenue_check.passed is False
    assert "2024 unter 20%" in revenue_check.detail


def test_annual_revenue_three_year_rule_fails_when_less_than_three_years_are_available() -> None:
    checks, _, _ = evaluate_fundamentals_context({"annual_revenue_history": _annual_revenue_history([32.4, 27.1])})

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert revenue_check.passed is False
    assert "nur 2/3 Jahre verfügbar" in revenue_check.detail


def test_annual_revenue_three_year_rule_handles_invalid_prior_year_revenue_without_division_error() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {
            "annual_revenue_history": [
                {"fiscal_year": "2025", "revenue_current_year": 720.0, "revenue_previous_year": 520.0},
                {"fiscal_year": "2024", "revenue_current_year": 520.0, "revenue_previous_year": 0.0},
                {"fiscal_year": "2023", "revenue_current_year": 340.0, "revenue_previous_year": -1.0},
            ]
        }
    )

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert revenue_check.passed is False
    assert "2024, 2023 nicht auswertbar" in revenue_check.detail


def test_annual_revenue_three_year_rule_does_not_pass_with_only_legacy_single_year_growth() -> None:
    checks, _, available = evaluate_fundamentals_context({"annual_revenue_growth_pct": 80.0})

    revenue_check = _check(checks, "Umsatz-Wachstum letzte 3 Jahre jeweils >=20% YoY")
    assert available is True
    assert revenue_check.passed is False
    assert "keine jährliche Umsatz-Historie" in revenue_check.detail


def test_revenue_acceleration_bonus_uses_last_three_quarter_growth_rates() -> None:
    checks, _, _ = evaluate_fundamentals_context(
        {"revenue_quarter_history": _revenue_history([40.0, 25.0, 20.0])}
    )

    accel_check = _check(checks, "Bonus: Umsatz-Beschleunigung letzte 3 Quartale")
    assert accel_check.passed is True
    assert "Bonus erfüllt" in accel_check.detail


def test_roe_three_year_rule_scores_each_year_over_threshold() -> None:
    checks, score, _ = evaluate_fundamentals_context({"roe_history": _roe_history([28.0, 21.0, 17.5])})

    roe_check = _check(checks, "ROE >=17% über letzte 3 Jahre")
    assert roe_check.passed is True
    assert "alle >=17%" in roe_check.detail
    assert score > 0


def test_roe_three_year_rule_fails_when_one_year_is_below_threshold() -> None:
    checks, _, _ = evaluate_fundamentals_context({"roe_history": _roe_history([28.0, 12.0, 18.0])})

    roe_check = _check(checks, "ROE >=17% über letzte 3 Jahre")
    assert roe_check.passed is False
    assert "2024 unter 17%" in roe_check.detail


def test_roe_current_value_is_only_fallback_when_history_missing() -> None:
    checks, score, _ = evaluate_fundamentals_context({"roe_pct": 30.0})

    roe_check = _check(checks, "ROE >=17% über letzte 3 Jahre")
    assert roe_check.passed is False
    assert "Keine ROE-Jahreshistorie" in roe_check.detail
    assert score < 20


def test_stock_assessment_flags_near_earnings() -> None:
    near_earnings = date.today() + timedelta(days=3)
    bars = _synthetic_bars(start_price=45, drift=0.003, volume=2_500_000)
    result = compute_stock_assessment(
        "EARN",
        bars,
        fundamentals_context={
            "ticker": "EARN",
            "as_of": date.today().isoformat(),
            "source": "manual",
            "next_earnings_date": near_earnings.isoformat(),
        },
    )

    assert result.earnings is not None
    assert result.earnings.tone in {"warning", "bad"}
    assert any(check.label == "Earnings-Abstand >14 Handelstage" for check in result.checks)
    assert any("Quartalszahlen" in warning for warning in result.warnings)


def _synthetic_bars(*, start_price: float, drift: float, volume: float) -> list[StockAssessmentBar]:
    bars: list[StockAssessmentBar] = []
    current = start_price
    current_date = date.today() - timedelta(days=360)
    index = 0
    while len(bars) < 260:
        if current_date.weekday() >= 5:
            current_date += timedelta(days=1)
            continue
        wobble = 0.012 if index % 17 == 0 else -0.006 if index % 11 == 0 else 0.0
        previous = current
        current = max(2.0, current * (1 + drift + wobble))
        high = max(previous, current) * 1.015
        low = min(previous, current) * 0.985
        bars.append(
            StockAssessmentBar(
                date=current_date,
                open=round(previous, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(current, 2),
                volume=volume * (1.4 if index % 13 == 0 else 1.0),
            )
        )
        current_date += timedelta(days=1)
        index += 1
    return bars


def _eps_history(values: list[float]) -> list[dict]:
    return [
        {
            "fiscal_period": f"Q{index}",
            "eps_current_quarter": round(1.0 + growth / 100.0, 4),
            "eps_same_quarter_last_year": 1.0,
        }
        for index, growth in enumerate(values, start=1)
    ]


def _annual_eps_history(values: list[float]) -> list[dict]:
    return [
        {
            "fiscal_year": str(2026 - index),
            "eps_current_year": round(10.0 * (1.0 + growth / 100.0), 4),
            "eps_previous_year": 10.0,
        }
        for index, growth in enumerate(values, start=1)
    ]


def _revenue_history(values: list[float]) -> list[dict]:
    return [
        {
            "fiscal_period": f"Q{index}",
            "revenue_current_quarter": round(100.0 * (1.0 + growth / 100.0), 4),
            "revenue_same_quarter_last_year": 100.0,
        }
        for index, growth in enumerate(values, start=1)
    ]


def _annual_revenue_history(values: list[float]) -> list[dict]:
    return [
        {
            "fiscal_year": str(2026 - index),
            "revenue_current_year": round(1000.0 * (1.0 + growth / 100.0), 4),
            "revenue_previous_year": 1000.0,
        }
        for index, growth in enumerate(values, start=1)
    ]


def _roe_history(values: list[float]) -> list[dict]:
    return [
        {
            "fiscal_year": str(2026 - index),
            "roe_pct": value,
            "net_income": round(100.0 * value / 17.0, 4),
            "shareholders_equity": 100.0,
        }
        for index, value in enumerate(values, start=1)
    ]


def _check(checks, label: str):
    return next(check for check in checks if check.label == label)
