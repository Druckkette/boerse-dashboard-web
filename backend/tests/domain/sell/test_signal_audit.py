"""Regression cases for real signal failures and WRO #73 position targets."""
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app.domain.sell import rules, service
from app.domain.sell.metrics import build_sell_decision_metrics_payload
from app.services.market_calendar import ExpectedMarketSession


def frame(closes, start='2026-01-05', final=True):
    index = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({'Open': closes, 'High': [c + 1 for c in closes], 'Low': [c - 1 for c in closes], 'Close': closes, 'Volume': 1000, 'IsFinal': final}, index=index)


def payload(asset, benchmark=None, buy_price=80, buy_date=None):
    benchmark = benchmark if benchmark is not None else frame([100.] * len(asset), start=str(asset.index[0].date()))
    return build_sell_decision_metrics_payload(ticker='TEST', buy_date=buy_date or asset.index[-10], buy_price=buy_price, shares=10, price_frame=asset, benchmark_frame=benchmark)


def evaluate(data, strategy='rs_line_ema', **setup):
    return rules.evaluate_sell_decision(data, {'use_global_sell_setup': False, 'sell_setup': {'strategy_key': strategy, **setup}})


@pytest.mark.parametrize('rs,emas,target', [
    (1.1, (1., 1., 1.), 0),
    (1., (1., 1., 1.), 0),  # A touch is not a break.
    (.99, (1., .98, .97), 60),
    (.97, (1., .98, .96), 80),
    (.95, (1., .98, .96), 100),
    (.97, (.96, .98, .95), 80),  # Medium line alone: don't lose earlier target.
    (.97, (.96, .95, .98), 100),  # Slow exit can skip both earlier steps.
])
def test_wro73_stage_targets_are_cumulative_not_added(rs, emas, target):
    data = {'ticker': 'TEST', 'buy_price': 80, 'as_of': '2026-10-02', 'metrics': {'rs_line': rs, **dict(zip(('rs_ema21', 'rs_ema34', 'rs_ema50'), emas))}}
    result = evaluate(data)
    assert result['strategy']['label'] == 'RS-Linie EMA'
    assert result['target_total_sold_percent'] == target
    assert result['sell_now_percent'] == target
    assert result['pending_status'] == ('scharf' if target else 'halten')
    assert result['next_tranche_trigger_price'] is None  # RS threshold isn't a price MA.


def test_wro73_logs_and_configurable_core_are_respected():
    data = {'ticker': 'TEST', 'buy_price': 80, 'metrics': {'rs_line': .95, 'rs_ema21': 1., 'rs_ema34': 1., 'rs_ema50': 1.}}
    manual = {'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'rs_line_ema'}}
    result = rules.evaluate_sell_decision(data, manual, [{'ticker': 'TEST', 'pct': 60}, {'ticker': 'TEST', 'pct': 20}])
    assert result['sell_now_percent'] == 20
    assert result['remaining_after_sale_percent'] == 0
    data['metrics'].update(rs_ema34=.94, rs_ema50=.93)
    assert evaluate(data, rs_ema_core_pct=100, rs_ema_first_pct=25, rs_ema_second_pct=25)['sell_now_percent'] == 25


@pytest.mark.parametrize('setup', [
    {'rs_ema_core_pct': 0}, {'rs_ema_core_pct': 101}, {'rs_ema_core_pct': 60.5},
    {'rs_ema_core_pct': 60, 'rs_ema_first_pct': 40, 'rs_ema_second_pct': 30},
])
def test_invalid_wro73_allocations_rejected(setup):
    with pytest.raises(ValueError):
        rules.validate_sell_setup_payload({'strategy_key': 'rs_line_ema', **setup})


def test_wro73_emas_match_independent_recursive_calculation_and_chart():
    asset = frame([100. + i / 2 for i in range(100)] + [140., 135., 130.])
    data = payload(asset)
    ratios = asset.Close / 100
    for period in (21, 34, 50):
        expected = ratios.iloc[0]
        for value in ratios.iloc[1:]:
            expected += 2 / (period + 1) * (value - expected)
        assert data['metrics'][f'rs_ema{period}'] == pytest.approx(expected)
        assert data['metrics']['rs_chart_history'][-1][f'rs_ema{period}'] == pytest.approx(expected)
    assert data['metrics']['rs_data_complete'] is True


def test_intraday_candle_cannot_confirm_daily_sale_but_emergency_remains_live():
    asset = frame([100.] * 100 + [90., 90., 60.])
    asset.loc[asset.index[-1], 'IsFinal'] = False
    data = payload(asset, buy_price=100)
    assert data['metrics']['days_under_ema21'] == 2
    assert data['metrics']['current_price'] == 60
    assert data['metrics']['signal_close'] == 90
    assert data['ohlc_frames']['daily_history'].index[-1] == asset.index[-2]
    result = evaluate(data, strategy='ema21_offensive', emergency_stop_value=50)
    assert result['strategy']['recommendations'][0]['active'] is False
    result = evaluate(data, strategy='rs_line_ema')
    assert result['killer_signals']
    assert result['target_total_sold_percent'] == 100


def test_missing_benchmark_session_disables_rs_instead_of_emitting_old_sale():
    asset = frame([100.] * 100 + [90.] * 3)
    benchmark = frame([100.] * len(asset))
    benchmark = benchmark.drop(benchmark.index[-2])
    data = payload(asset, benchmark)
    assert data['metrics']['rs_data_complete'] is False
    result = evaluate(data)
    assert result['sell_now_percent'] == 0
    assert 'unvollständig' in result['explanation_short']


@pytest.mark.parametrize('last_day,expected_weeks', [('2026-10-01', 3), ('2026-10-02', 4), ('2026-04-02', 4)])
def test_unfinished_week_excluded_and_good_friday_week_completed(last_day, expected_weeks):
    last = pd.Timestamp(last_day)
    # Exactly four calendar weeks; Good Friday's last session is Thursday.
    first = last - pd.Timedelta(days=last.weekday() + 21)
    index = pd.bdate_range(first, last)
    asset = frame([100.] * len(index), start=str(first.date()))
    data = payload(asset, buy_date=first)
    assert len(data['ohlc_frames']['weekly_since_buy']) == expected_weeks


def test_continuous_low_breaches_do_not_restart_reclaim_deadline():
    index = pd.bdate_range('2026-09-01', periods=5)
    close = pd.Series([101., 98., 97., 96., 95.], index=index)
    result = rules._breach_reclaim_status(close, close - 1, 100, 3)
    assert result['active'] is True
    assert result['signal_date'] == str(index[1].date())
    close.iloc[-1] = 101
    assert rules._breach_reclaim_status(close, close - 1, 100, 3)['active'] is False
    # After a reclaim, a genuinely new breach starts a new deadline.
    close.iloc[2] = 101
    assert rules._breach_reclaim_status(close, close - 1, 100, 3)['active'] is False


def test_new_pending_selloff_does_not_hide_already_confirmed_failure():
    daily = frame([100., 90., 90., 90., 90., 90., 80.]).rename(columns=str.lower)
    daily.loc[daily.index[1], 'high'] = 100
    result = rules._sharp_drop_without_reclaim(daily, daily.close.pct_change() * 100, 2, 'pct', 6, 4)
    assert result['active'] is True
    assert result['signal_date'] == str(daily.index[1].date())


def test_cache_does_not_invent_volume_or_candle_extremes(monkeypatch):
    bars = [SimpleNamespace(date=date(2026, 10, 2), fetched_at=datetime(2026, 10, 2, 21, tzinfo=UTC), open=100, high=None, low=None, close=100, volume=None), SimpleNamespace(date=date(2026, 10, 1), fetched_at=None, open=100, high=101, low=99, close=100, volume=0)]
    monkeypatch.setattr(service.prices_repository, 'list_price_bars', lambda *a: bars)
    monkeypatch.setattr('app.services.market_calendar.completed_us_market_session', lambda: ExpectedMarketSession(date=date(2026, 10, 2), phase='closed'))
    cached = service._price_frame_from_cache('TEST')
    assert pd.isna(cached.iloc[-1].Volume)
    assert pd.isna(cached.iloc[-1].High)
    assert pd.isna(cached.iloc[-1].Low)
    assert cached.iloc[0].Volume == 0


def test_missing_volume_is_displayed_as_unknown_not_a_pass():
    asset = frame([100.] * 100)
    asset['Volume'] = float('nan')
    result = evaluate(payload(asset), strategy='custom', custom_strategy_steps=[{'feature_id': 'offensive_stall_days', 'tranche_percent': 20}])
    feature = next(f for f in result['offensive_features'] if f['id'] == 'offensive_stall_days')
    assert feature['available'] is False
    assert feature['active'] is False
    assert 'nicht prüfbar' in result['explanation_short']


@pytest.mark.parametrize('feature_id', list(rules.BOOK_REFERENCES))
def test_each_of_all_23_custom_criteria_delivers_its_selected_signal_only(monkeypatch, feature_id):
    def features(category):
        return [rules.RuleFeature(id=key, category=category, label=key, active=True, contribution_percent=25) for key in rules.BOOK_REFERENCES if key.startswith(category)]
    for category in ('offensive', 'defensive', 'emergency'):
        # Avoid a universal emergency overriding every positive routing case.
        group = features(category)
        if category == 'emergency' and feature_id != 'emergency_loss_limit':
            group = [rules.replace(f, active=False) for f in group]
        monkeypatch.setattr(rules, f'_detect_{category}_features', lambda *a, group=group: group)
    result = evaluate({'ticker': 'TEST', 'metrics': {}}, strategy='custom', custom_strategy_steps=[{'feature_id': feature_id, 'tranche_percent': 20}])
    assert result['target_total_sold_percent'] == (100 if feature_id == 'emergency_loss_limit' else 20)
    selected = [f for name in ('offensive_features', 'defensive_features') for f in result[name] if f['strategy_selected']]
    assert [f['id'] for f in selected] == ([] if feature_id == 'emergency_loss_limit' else [feature_id])


def test_api_preserves_zero_remaining_position_after_full_sale(monkeypatch):
    from tests.helpers.sell_fixture_data import fixture_positions, fixture_price_bars
    monkeypatch.setattr(service.portfolio_repository, 'list_open_positions', fixture_positions)
    monkeypatch.setattr(service.prices_repository, 'list_price_bars', fixture_price_bars)
    result = service.preview_position_sell_decision('PLTR')
    assert result.target_total_sold_percent == 100
    assert result.remaining_after_sale_percent == 0


def test_wro73_global_default_and_stock_override_round_trip(monkeypatch):
    from tests.helpers.sell_fixture_data import fixture_positions, fixture_price_bars
    from app.repositories import sell_state
    from app.services import settings as settings_service
    from fastapi.testclient import TestClient
    from app.main import app
    values, manuals = {}, {}
    def save_settings(new):
        values.update(new)
        return dict(values)
    def save_manual(manual):
        manuals[manual.ticker] = manual
        return manual
    monkeypatch.setattr(settings_service.settings_repository, 'read_settings', lambda: dict(values))
    monkeypatch.setattr(settings_service.settings_repository, 'write_settings', save_settings)
    monkeypatch.setattr(service.portfolio_repository, 'list_open_positions', fixture_positions)
    monkeypatch.setattr(service.prices_repository, 'list_price_bars', fixture_price_bars)
    monkeypatch.setattr(sell_state, 'get_manual_input', lambda ticker: manuals.get(ticker))
    monkeypatch.setattr(sell_state, 'upsert_manual_input', save_manual)
    monkeypatch.setattr(sell_state, 'invalidate_ranking_snapshot', lambda: None)
    client = TestClient(app)
    response = client.patch('/api/v1/settings', json={'sell_rule_setup': {'strategy_key': 'rs_line_ema'}})
    assert response.status_code == 200
    assert response.json()['sell_rule_setup']['rs_ema_core_pct'] == 60
    assert client.post('/api/v1/sell/NVDA/evaluate').json()['strategy']['label'] == 'RS-Linie EMA'
    response = client.patch('/api/v1/sell/NVDA/manual', json={'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'rs_line', 'rs_tranche_1_pct': 25}})
    assert response.status_code == 200
    assert client.post('/api/v1/sell/NVDA/evaluate').json()['strategy']['strategy_key'] == 'rs_line'
    assert client.get('/api/v1/sell/PLTR/manual').json()['manual']['sell_setup']['strategy_key'] == 'rs_line_ema'


@pytest.mark.parametrize('feature_id', list(rules.BOOK_REFERENCES))
@pytest.mark.parametrize('should_trigger', [False, True])
def test_all_23_real_detectors_have_positive_and_negative_cases(feature_id, should_trigger):
    index = pd.bdate_range('2025-01-06', periods=220)
    full = pd.DataFrame({'open': 100., 'high': 101., 'low': 99., 'close': 100., 'volume': 1000.}, index=index)
    weekly_index = pd.date_range('2026-01-09', periods=8, freq='W-FRI')
    weekly = pd.DataFrame({'open': 100., 'high': 102., 'low': 99., 'close': 100., 'volume': 1000.}, index=weekly_index)
    metrics = {'current_price': 100., 'signal_close': 100., 'ema21': 100., 'atr14': 2., 'high_since_buy': 100.}
    setup = dict(rules.DEFAULT_SELL_RULE_SETUP)
    manual = {'low_day_1': 100., 'low_day_0': 100.}
    def set_last(closes):
        for day, value in zip(index[-len(closes):], closes):
            full.loc[day, ['open', 'high', 'low', 'close']] = [value, value + 1, value - 1, value]
        metrics['current_price'] = metrics['signal_close'] = closes[-1]
    if feature_id == 'emergency_loss_limit':
        metrics['current_price'] = 92. if should_trigger else 94.
    elif feature_id == 'offensive_profit_target':
        metrics['signal_close'] = 121. if should_trigger else 119.
    elif feature_id == 'offensive_ema21_break':
        metrics['signal_close'] = 97. if should_trigger else 99.
    elif feature_id == 'offensive_peak_drop':
        if should_trigger:
            full.loc[index[-10:], 'high'] = 120.
    elif feature_id.startswith('offensive_ma_extension_'):
        setup['ma_extension_unit'] = 'pct'
        key = feature_id.removeprefix('offensive_ma_extension_')
        setup[f'ma_extension_{key}_pct'] = 5.
        if should_trigger:
            set_last([120., 118.])  # Still overextended; falling below the peak matters.
    elif feature_id == 'offensive_low_closes':
        if should_trigger:
            full.loc[index[-4:], 'high'] = 110.
    elif feature_id == 'offensive_sharp_drop_no_reclaim':
        if should_trigger:
            set_last([120., 105., 105., 105., 105., 105.])
            full.loc[index[-5], 'high'] = 120.
    elif feature_id == 'offensive_loss_days_cluster':
        if should_trigger:
            set_last(list(range(109, 98, -1)))
    elif feature_id == 'offensive_biggest_gain':
        if should_trigger:
            set_last([115.])
            full.loc[index[-1], 'volume'] = 3000.
    elif feature_id == 'offensive_stall_days':
        if should_trigger:
            full.loc[index[-3:], 'volume'] = 4000.
    elif feature_id == 'offensive_buy_price_reached':
        metrics['high_since_buy'] = 110. if should_trigger else 100.
    elif feature_id == 'defensive_buy_day_low':
        manual['low_day_1'] = 98.
        if should_trigger:
            set_last([98., 97., 96., 95.])
    elif feature_id == 'defensive_previous_day_low':
        metrics['signal_close'] = 99. if should_trigger else 100.
    elif feature_id.startswith('defensive_ma_break_'):
        if should_trigger:
            set_last([95.] * 3)
    elif feature_id == 'defensive_loss_weeks':
        if should_trigger:
            weekly.loc[weekly_index[-4:], 'close'] = [99., 98., 97., 96.]
    elif feature_id == 'defensive_worst_daily_drop':
        if should_trigger:
            set_last([100., 90.])
    elif feature_id == 'defensive_worst_weekly_drop':
        if should_trigger:
            weekly.loc[weekly_index[-1], 'close'] = 80.
    else:
        pytest.fail(f'No detector case defined for {feature_id}')
    data = {'ticker': 'TEST', 'buy_price': 100., 'as_of': str(index[-1].date()), 'metrics': metrics, 'ohlc_frames': {'daily_history': full, 'daily_since_buy': full.tail(30), 'weekly_since_buy': weekly}}
    groups = {
        'emergency': rules._detect_emergency_features(data, manual, setup, metrics, 100.),
        'offensive': rules._detect_offensive_features(data, setup, metrics, 100.),
        'defensive': rules._detect_defensive_features(data, manual, setup, metrics),
    }
    feature = next(f for f in groups[feature_id.split('_')[0]] if f.id == feature_id)
    assert feature.active is should_trigger, feature


def test_past_position_sales_do_not_suppress_reentered_position_signals():
    data = {'ticker': 'TEST', 'buy_date': '2026-10-01', 'buy_price': 80, 'metrics': {'rs_line': .95, 'rs_ema21': 1., 'rs_ema34': 1., 'rs_ema50': 1.}}
    result = rules.evaluate_sell_decision(data, {'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'rs_line_ema'}}, [{'ticker': 'TEST', 'date': '2026-09-10', 'pct': 100}, {'ticker': 'TEST', 'date': '2026-10-02', 'pct': 20}])
    assert result['already_sold_percent'] == 20
    assert result['sell_now_percent'] == 80


def test_missing_atr_never_becomes_a_percent_stop_price():
    assert rules._build_stop_price({'emergency_stop_unit': 'atr', 'emergency_stop_value': 2}, 100, None) is None
    assert rules._build_stop_price({'emergency_stop_unit': 'atr', 'emergency_stop_value': 2}, 100, 3) == 94


def test_recommendation_confirmation_requires_consecutive_sessions():
    status, state = rules._compute_recommendation_status(sell_now=50, has_killer=False, as_of_date='2026-10-06', prior_state={'last_seen_date': '2026-10-02', 'last_pct': 50, 'consecutive_days': 1})
    assert status == 'in_bestaetigung'
    assert state['consecutive_days'] == 1
    status, state = rules._compute_recommendation_status(sell_now=50, has_killer=False, as_of_date='2026-10-05', prior_state={'last_seen_date': '2026-10-02', 'last_pct': 50, 'consecutive_days': 1})
    assert status == 'scharf'
    assert state['consecutive_days'] == 2


def test_rs_trend_uses_selected_ema_lines_instead_of_sma_lines():
    data = {'ticker': 'TEST', 'metrics': {'rs_line': .98, 'rs_ma21': .95, 'rs_ma50': .95, 'rs_ema21': .99, 'rs_ema34': .99, 'rs_ema50': .99}}
    health = rules.compute_sell_health_score(data, {'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'rs_line_ema'}})
    assert health['rs_trend'] == 'runter'


@pytest.mark.parametrize('event_atr,active', [(2., True), (10., False)])
def test_historical_selloff_uses_event_atr_not_latest_atr(event_atr, active):
    daily = frame([100., 90., 90., 90., 90., 90.]).rename(columns=str.lower)
    daily.loc[daily.index[1], 'high'] = 100.
    atrs = pd.Series(2., index=daily.index)
    atrs.loc[daily.index[1]] = event_atr
    assert rules._sharp_drop_without_reclaim(daily, daily.close.pct_change() * 100, 2., 'atr', 2., 4, atr_series=atrs)['active'] is active


@pytest.mark.parametrize('event_atr,active', [(2., True), (10., False)])
def test_historical_gain_uses_event_atr_and_first_held_day_previous_close(event_atr, active):
    history = frame([100.] * 60 + [110.]).rename(columns=str.lower)
    history.loc[history.index[-1], 'volume'] = 2000.
    daily = history.tail(1)
    pct = history.close.pct_change() * 100
    atrs = pd.Series(event_atr, index=daily.index)
    feature = rules._biggest_gain_feature(daily, pct.reindex(daily.index), daily.volume, pd.Series(1000., index=daily.index), 1., {**rules.DEFAULT_SELL_RULE_SETUP, 'biggest_gain_unit': 'atr', 'biggest_gain_value': 2.}, str(daily.index[-1].date()), history=history, atr_series=atrs)
    assert feature.active is active


def test_no_completed_price_data_is_an_error_not_a_hold_recommendation(monkeypatch):
    from app.domain.sell.schemas import SellMetricsRequest
    unfinished = frame([100.] * 100, final=False)
    monkeypatch.setattr(service, '_price_frame_from_cache', lambda *a: unfinished)
    monkeypatch.setattr(service, '_sell_frame_in_currency', lambda source, *a: source)
    with pytest.raises(service.SellMarketDataUnavailableError, match='bestätigten Tagesschlusskurse'):
        service._build_metrics_payload(SellMetricsRequest(ticker='TEST', buy_date=date(2026, 1, 5), buy_price=80, shares=10))
