from dataclasses import replace
from datetime import date, timedelta
from types import SimpleNamespace
import pytest
from app.domain.market.ampel import TrendAmpelPoint
from app.domain.market import context_scores as s
from app.schemas import MarketContextScore


def points(n=90, **changes):
    result = []
    for i in range(n):
        p = TrendAmpelPoint(
            date=(date(2024, 1, 1) + timedelta(days=i)).isoformat(),
            phase="gruen",
            close=100,
            ema21=95,
            sma50=90,
            sma200=80,
            pct_change=0,
            closing_range=0.7,
            dist_count_25=0,
            anchor_date=None,
            floor_mark=None,
            startschuss_low=None,
            startschuss_bonus=False,
            open=99,
            high=101,
            low=98,
            volume=1000,
            ema21_held=True,
            sma50_held=True,
            sma200_held=True,
            powertrend_state="on",
            powertrend_low_above_21_streak=10,
            powertrend_ema21_over_50_streak=5,
            powertrend_sma50_rising_1d=True,
            powertrend_positive_or_flat_day=True,
        )
        result.append(replace(p, **changes))
    return result


def criteria(result):
    return {c["id"]: c for group in result["subscores"] for c in group["criteria"]}


def test_unweighted_index_features_cannot_reduce_score_and_w14_is_not_counted_twice():
    base = points()
    damaged = [
        replace(
            p, dist_21ema=4, dist_50sma_pct=9, ema21_held=False, sma50_held=False, sma200_held=False
        )
        for p in base
    ]
    a, b = s.index_score(base), s.index_score(damaged)
    assert a["score"] == b["score"]
    assert set(criteria(a)) == {f"W{i:02}" for i in range(1, 15)} | {"A09", "A11"}
    assert all(
        criteria(a)[id]["weight"] == 0
        for id in ["W06", "W07", "W08", "W09", "W10", "W12", "W13", "W14"]
    )


def test_w04_has_small_weight_and_unknown_volume_is_not_a_healthy_signal():
    base = s.index_score(points(dist_count_25=6))
    assert criteria(base)["W04"]["weight"] == 0.5
    assert criteria(base)["W04"]["score"] == 0
    unknown = s.index_score(points(volume=0, dist_count_25=6))
    for id in ["W03", "W04", "W11"]:
        assert criteria(unknown)[id]["evaluation"] == "missing"
        assert criteria(unknown)[id]["score"] is None
    assert unknown["data_status"] == "partial"


def test_confirmed_uptrend_bonus_and_ftd_negation_malus_are_separate():
    base = s.index_score(points())["score"]
    assert s.index_score(points(phase="aufwaertstrend"))["score"] > base
    assert s.index_score(points(ftd_negated=True))["score"] < base


def test_missing_does_not_penalize_or_count_as_zero():
    result = s.subscore(
        "example",
        "Example",
        100,
        [
            s.criterion("a", "A", 1, 80, "a", "rule"),
            s.criterion("b", "B", 1, None, "Nicht verfügbar", "rule"),
        ],
    )
    assert result["score"] == 80
    assert result["coverage_pct"] == 50
    assert result["data_status"] == "partial"
    assert result["criteria"][1]["contribution"] is None


def test_w14_alone_does_not_make_missing_universe_breadth_look_healthy():
    result = s.breadth_score(points(), [])
    assert result["score"] is None
    assert result["coverage_pct"] == 5
    assert criteria(result)["W14"]["score"] == 100


def test_zero_participation_is_valid_and_zero_denominator_is_explicit():
    rows = [
        dict(
            advancers=10,
            decliners=0,
            new_highs=3,
            new_lows=0,
            pct_above_20sma=0,
            pct_above_50sma=0,
            pct_above_200sma=0,
            mcclellan=0,
            up_volume=10,
            down_volume=0,
        )
        for _ in range(20)
    ]
    result = s.breadth_score(points(), rows, ad_divergence=False)
    c = criteria(result)
    assert c["B01"]["score"] == 0 and c["B01"]["evaluation"] == "rated"
    assert c["B04"]["score"] == 100 and c["B04"]["value"] == "∞"
    assert c["D07"]["score"] == 50
    assert c["B03"]["weight"] == 0
    assert s._ratio([{"a": 0, "b": 0}], "a", "b") is None


def test_recovery_is_fraction_of_drop_not_percentage_gain():
    close = [80 + i * (20 / 59) for i in range(60)] + [98, 95, 90, 91, 92]
    p = [replace(x, close=v) for x, v in zip(points(len(close)), close)]
    result = s.breadth_score(p, [])
    assert criteria(result)["W14"]["score"] == pytest.approx(20)
    assert (
        criteria(s.breadth_score([*p[:-1], replace(p[-1], price_data_complete=False)], []))["W14"][
            "score"
        ]
        is None
    )


def test_powertrend_on_survives_loss_of_start_conditions():
    result = s.powertrend_score(
        points(powertrend_low_above_21_streak=1, powertrend_sma50_rising_1d=False), enabled=True
    )
    assert result["status"] == "Konstruktiv"
    assert criteria(result)["P05"]["score"] == 100
    assert s.powertrend_score(points(), enabled=False)["score"] is None
    assert (
        s.powertrend_score(points(powertrend_state="under_pressure"), enabled=True)["score"]
        < result["score"]
    )


def test_equal_weight_fallback_cannot_be_scored_as_neutral():
    assert s.equal_weight_score({"source": "missing", "mode": "wachsam"})["score"] is None
    values = {
        mode: s.equal_weight_score({"source": "database", "mode": mode, "candidate_streak": 3})
        for mode in ["rueckenwind", "wachsam", "schutz"]
    }
    assert values["rueckenwind"]["score"] > values["wachsam"]["score"] > values["schutz"]["score"]
    assert criteria(values["wachsam"])["E02"]["weight"] == 0


def test_volatility_stress_changes_only_context_and_missing_is_unknown():
    p = SimpleNamespace(
        vix_regime="Stress",
        vxx_state="Steigend",
        vol_regime="Risk Off bestätigt",
        vix_panic_overextension=True,
    )
    risk = s.volatility_score(p, vix_valid=True, vxx_valid=True)
    assert risk["status"] == "Schwach"
    assert criteria(risk)["V07"]["score"] == 0
    assert criteria(risk)["V03"]["weight"] == 0
    assert s.volatility_score(p)["score"] is None
    MarketContextScore.model_validate(risk)


@pytest.mark.parametrize(
    "value,status",
    [
        (0, "Schwach"),
        (39.99, "Schwach"),
        (40, "Gemischt"),
        (64.99, "Gemischt"),
        (65, "Konstruktiv"),
        (100, "Konstruktiv"),
        (None, "Nicht bewertbar"),
    ],
)
def test_score_status_boundaries(value, status):
    assert s.band(value)[0] == status


def test_signal_confirmation_resets_on_unknown():
    assert s.confirmed_warning([True]) == 100
    assert s.confirmed_warning([True, True]) == 0
    assert s.confirmed_warning([True, True, None]) is None
    assert s.confirmed_warning([True, True, None, True]) == 100


def test_information_scores_use_only_their_input_prefix():
    hist = points(100)
    before = s.index_score(hist[:90])
    hist[90:] = [replace(p, dist_count_25=10, ftd_negated=True, volume=0) for p in hist[90:]]
    assert s.index_score(hist[:90]) == before
