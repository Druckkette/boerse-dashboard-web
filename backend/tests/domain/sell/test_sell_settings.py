from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domain.sell import rules, service
from app.domain.sell.schemas import SellManualInput
from app.repositories import sell_state
from app.services import settings as settings_service
from tests.helpers.sell_fixture_data import fixture_positions, fixture_price_bars

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    values, manual_inputs = {}, {}
    def write_settings(next_values):
        values.clear()
        values.update(next_values)
        return dict(values)
    monkeypatch.setattr(settings_service.settings_repository, 'read_settings', lambda: dict(values))
    monkeypatch.setattr(settings_service.settings_repository, 'write_settings', write_settings)
    monkeypatch.setattr(service.portfolio_repository, 'list_open_positions', fixture_positions)
    monkeypatch.setattr(service.prices_repository, 'list_price_bars', fixture_price_bars)
    monkeypatch.setattr(sell_state, 'get_manual_input', lambda ticker: manual_inputs.get(ticker))
    def write_manual(manual):
        manual_inputs[manual.ticker] = manual
        return manual
    monkeypatch.setattr(sell_state, 'upsert_manual_input', write_manual)
    monkeypatch.setattr(sell_state, 'invalidate_ranking_snapshot', lambda: None)
    yield manual_inputs


def test_global_default_override_and_return_to_inheritance(isolated_settings):
    response = client.patch('/api/v1/settings', json={'sell_rule_setup': {'strategy_key': 'ema21_offensive', 'emergency_stop_value': 5}})
    assert response.status_code == 200
    assert response.json()['sell_rule_setup']['rs_tranche_3_pct'] == 50
    inherited = client.get('/api/v1/sell/NVDA/manual').json()['manual']
    assert inherited['use_global_sell_setup'] is True
    assert inherited['sell_setup']['emergency_stop_value'] == 5
    assert client.post('/api/v1/sell/NVDA/evaluate').json()['strategy']['strategy_key'] == 'ema21_offensive'
    own = {**inherited, 'use_global_sell_setup': False, 'sell_setup': {**inherited['sell_setup'], 'strategy_key': 'peak_drawdown'}}
    assert client.patch('/api/v1/sell/NVDA/manual', json=own).status_code == 200
    assert client.post('/api/v1/sell/NVDA/evaluate').json()['strategy']['strategy_key'] == 'peak_drawdown'
    client.patch('/api/v1/settings', json={'sell_rule_setup': {'strategy_key': 'ma_breaks', 'emergency_stop_value': 4}})
    assert client.get('/api/v1/sell/NVDA/manual').json()['manual']['sell_setup']['emergency_stop_value'] == 5
    assert client.get('/api/v1/sell/PLTR/manual').json()['manual']['sell_setup']['strategy_key'] == 'ma_breaks'
    response = client.patch('/api/v1/sell/NVDA/manual', json={**own, 'use_global_sell_setup': True})
    assert response.status_code == 200
    assert isolated_settings['NVDA'].sell_setup == {}
    assert response.json()['manual']['sell_setup']['strategy_key'] == 'ma_breaks'
    assert client.post('/api/v1/sell/NVDA/evaluate').json()['strategy']['strategy_key'] == 'ma_breaks'


def test_existing_stock_rules_remain_an_override(isolated_settings):
    isolated_settings['NVDA'] = SellManualInput(ticker='NVDA', sell_setup={'strategy_key': 'buy_day_low', 'profit_target_value': 30})
    client.patch('/api/v1/settings', json={'sell_rule_setup': {'strategy_key': 'peak_drawdown'}})
    manual = client.get('/api/v1/sell/NVDA/manual').json()['manual']
    assert manual['use_global_sell_setup'] is False
    assert manual['sell_setup']['strategy_key'] == 'buy_day_low'
    assert manual['sell_setup']['profit_target_value'] == 30


def test_rule_editor_does_not_require_price_history(monkeypatch):
    monkeypatch.setattr(service.prices_repository, 'list_price_bars', lambda *a, **kw: pytest.fail('Editor must not fetch prices'))
    response = client.get('/api/v1/sell/NEW/manual')
    assert response.status_code == 200
    assert response.json()['manual']['use_global_sell_setup'] is True


@pytest.mark.parametrize('setup', [
    {'strategy_key': 'unknown'}, {'strategy_key': []}, {'ma_extension_unit': {}}, {'emergency_stop_value': -1}, {'emergency_stop_value': 0}, {'ma_break_reclaim_days': 0}, {'rs_tranche_1_pct': 110},
    {'custom_strategy_steps': [{'feature_id': 'unknown', 'tranche_percent': 25}]},
    {'custom_strategy_steps': [{'feature_id': 'offensive_profit_target', 'tranche_percent': 25}] * 2},
    {'custom_strategy_steps': [{'feature_id': 'offensive_profit_target', 'tranche_percent': 2.5}]},
])
def test_invalid_global_and_stock_rules_are_rejected(setup):
    assert client.patch('/api/v1/settings', json={'sell_rule_setup': setup}).status_code == 422
    assert client.patch('/api/v1/sell/NVDA/manual', json={'sell_setup': setup, 'use_global_sell_setup': False}).status_code == 422


def test_modern_custom_strategy_matching_legacy_defaults_is_preserved():
    setup = {'strategy_key': 'custom', 'custom_strategy_steps': rules.PREVIOUS_DEFAULT_CUSTOM_STRATEGY_STEPS}
    response = client.patch('/api/v1/sell/NVDA/manual', json={'sell_setup': setup, 'use_global_sell_setup': False})
    assert response.status_code == 200
    assert response.json()['manual']['sell_setup']['strategy_key'] == 'custom'
    assert response.json()['manual']['sell_setup']['custom_strategy_steps'] == rules.PREVIOUS_DEFAULT_CUSTOM_STRATEGY_STEPS


def test_unselected_active_features_do_not_escalate_custom_sale(monkeypatch):
    features = [rules.RuleFeature(id=key, category='offensive', label=key, active=True, contribution_percent=25) for key in ['offensive_peak_drop', 'offensive_ema21_break', 'offensive_ma_extension_sma200', 'offensive_biggest_gain']]
    features.append(rules.RuleFeature(id='offensive_profit_target', category='offensive', label='profit', active=False))
    monkeypatch.setattr(rules, '_detect_emergency_features', lambda *a: [])
    monkeypatch.setattr(rules, '_detect_defensive_features', lambda *a: [])
    monkeypatch.setattr(rules, '_detect_offensive_features', lambda *a: features)
    manual = {'market_environment': 'Bärisch', 'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'custom', 'custom_strategy_steps': [{'feature_id': 'offensive_profit_target', 'tranche_percent': 20}]}}
    payload = {'ticker': 'TEST', 'buy_price': 100, 'as_of': '2026-10-02', 'metrics': {'pnl_pct': 120}}
    result = rules.evaluate_sell_decision(payload, manual)
    assert result['target_total_sold_percent'] == 0
    assert result['sell_now_percent'] == 0
    assert result['offensive_features'][-1]['strategy_selected'] is True
    assert result['offensive_features'][0]['strategy_selected'] is False
    features[-1] = rules.RuleFeature(id='offensive_profit_target', category='offensive', label='profit', active=True)
    result = rules.evaluate_sell_decision(payload, manual)
    assert result['target_total_sold_percent'] == 20
    assert result['sell_now_percent'] == 20
    assert result['offensive_features'][-1]['recommendation_contribution_percent'] == 20
    result = rules.evaluate_sell_decision(payload, manual, [{'ticker': 'TEST', 'pct': 5}])
    assert result['sell_now_percent'] == 15


def test_emergency_overrides_custom_selection_and_snooze(monkeypatch):
    monkeypatch.setattr(rules, '_detect_emergency_features', lambda *a: [rules.RuleFeature(id='emergency_loss_limit', category='emergency', label='Nothalt', active=True)])
    manual = {'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'custom', 'custom_strategy_steps': [{'feature_id': 'offensive_profit_target', 'tranche_percent': 20}]}}
    result = rules.evaluate_sell_decision({'ticker': 'TEST', 'buy_price': 100, 'as_of': '2026-10-02', 'metrics': {}}, manual, recommendation_state={'snoozed_until': '2026-10-10', 'snoozed_pct': 100})
    assert result['target_total_sold_percent'] == 100
    assert result['pending_status'] == 'scharf'
    assert result['emergency_features'][0]['recommendation_contribution_percent'] == 100


def test_atr_extension_uses_atr_instead_of_percent():
    index = pd.date_range('2026-01-01', periods=3)
    kwargs = dict(key='ema21', label='21-EMA', close=pd.Series([100, 110, 108], index=index), ma_series=pd.Series([100, 100, 100], index=index), threshold_pct=2, current=108, as_of='2026-01-03', contribution=25)
    atr_feature = rules._ma_extension_feature(**kwargs, unit='atr', atr_series=pd.Series([5, 5, 5], index=index))
    assert atr_feature.active is True
    assert 'ATR' in atr_feature.value
    assert atr_feature.setup['unit'] == 'atr'
    assert rules._ma_extension_feature(**kwargs).active is False
    missing = rules._ma_extension_feature(**kwargs, unit='atr', atr_series=pd.Series([float('nan')] * 3, index=index))
    assert missing.active is False


def test_use_global_flag_round_trips_database_representation():
    row = SimpleNamespace(ticker='NVDA', pivot=None, low_day_1=None, low_day_0=None, market_environment='Unsicher', industry_group_status='Neutral', checkboxes_json={'use_global_sell_setup': False}, setup_json={'strategy_key': 'peak_drawdown'})
    assert sell_state._manual_from_model(row).use_global_sell_setup is False


def test_long_ma_uses_history_before_purchase():
    index = pd.date_range('2025-01-01', periods=220)
    close = [100.0] * 210 + [90.0] * 10
    frame = pd.DataFrame({'open': close, 'high': [c + 1 for c in close], 'low': [c - 1 for c in close], 'close': close, 'volume': 1000}, index=index)
    payload = {'ticker': 'TEST', 'as_of': str(index[-1].date()), 'buy_price': 80, 'metrics': {'current_price': 90}, 'ohlc_frames': {'daily_history': frame, 'daily_since_buy': frame.iloc[-10:]}}
    result = rules.evaluate_sell_decision(payload, {'use_global_sell_setup': False, 'sell_setup': {'strategy_key': 'ma_breaks'}})
    ma200 = next(f for f in result['defensive_features'] if f['id'] == 'defensive_ma_break_200')
    assert ma200['active'] is True
    assert ma200['recommendation_contribution_percent'] == 100
    assert result['target_total_sold_percent'] == 100


@pytest.mark.parametrize('last_change, active', [(0.0, False), (0.1, False), (-0.1, True)])
def test_worst_drop_requires_an_actual_loss(last_change, active):
    feature = rules._worst_drop_feature(feature_id='defensive_worst_daily_drop', label='Verlust', changes=pd.Series([0.2, 0.3, last_change]), warmup=2, as_of='2026-10-02', period_label='Tage')
    assert feature.active is active


@pytest.mark.parametrize('days, lower, expected', [(1, False, 25), (2, True, 25), (3, False, 50)])
def test_rs_second_stage_requires_three_closes(days, lower, expected):
    payload = {'ticker': 'TEST', 'as_of': '2026-10-02', 'buy_price': 100, 'metrics': {'current_price': 110, 'pnl_pct': 10, 'rs_line': 1.1, 'rs_ma21': 1.2, 'rs_ma50': 1.0, 'days_under_rs_ma21': days, 'rs_lower_than_break_day': lower}}
    result = rules.evaluate_sell_decision(payload, {'use_global_sell_setup': True, 'sell_setup': {'strategy_key': 'rs_line'}})
    assert result['target_total_sold_percent'] == expected
    assert result['pending_status'] == 'scharf'


@pytest.mark.parametrize('already_sold, remaining', [(0, 100), (25, 75), (50, 50), (70, 30)])
def test_rs_slow_line_sells_entire_remaining_position_even_above_fast_line(already_sold, remaining):
    payload = {'ticker': 'TEST', 'as_of': '2026-10-02', 'buy_price': 100, 'metrics': {'current_price': 110, 'pnl_pct': 10, 'rs_line': 1.1, 'rs_ma21': 1.0, 'rs_ma50': 1.2, 'days_under_rs_ma21': 0}}
    result = rules.evaluate_sell_decision(payload, {'use_global_sell_setup': True, 'sell_setup': {'strategy_key': 'rs_line'}}, [{'ticker': 'TEST', 'pct': already_sold}])
    assert result['target_total_sold_percent'] == 100
    assert result['sell_now_percent'] == remaining
    assert result['remaining_after_sale_percent'] == 0
    assert result['pending_status'] == 'scharf'


def test_rs_confirmation_keeps_explicit_snooze():
    status, _ = rules._compute_recommendation_status(sell_now=50, has_killer=False, as_of_date='2026-10-02', prior_state={'snoozed_until': '2026-10-10', 'snoozed_pct': 50}, confirmed_signal=True)
    assert status == 'snoozed'


def test_rs_third_allocation_is_the_remaining_share():
    response = client.patch('/api/v1/settings', json={'sell_rule_setup': {'strategy_key': 'rs_line', 'rs_tranche_1_pct': 20, 'rs_tranche_2_pct': 30, 'rs_tranche_3_pct': 70}})
    assert response.status_code == 200
    assert response.json()['sell_rule_setup']['rs_tranche_3_pct'] == 50
    assert client.patch('/api/v1/settings', json={'sell_rule_setup': {'strategy_key': 'rs_line', 'rs_tranche_1_pct': 60, 'rs_tranche_2_pct': 60}}).status_code == 422
    assert rules.validate_sell_setup_payload({}) == {}


def test_rs_metrics_exclude_unfinished_daily_bars():
    from app.domain.sell.metrics import build_sell_decision_metrics_payload
    index = pd.date_range('2026-01-01', periods=60, freq='B')
    close = [100.0] * 57 + [95.0, 94.0, 93.0]
    asset = pd.DataFrame({'Open': close, 'High': [c + 1 for c in close], 'Low': [c - 1 for c in close], 'Close': close, 'Volume': 1000, 'IsFinal': True}, index=index)
    benchmark = pd.DataFrame({'Close': 100.0, 'IsFinal': True}, index=index)
    asset.loc[index[-1], 'IsFinal'] = False
    def build():
        return build_sell_decision_metrics_payload(ticker='TEST', buy_date=index[-10], buy_price=90, shares=10, price_frame=asset, benchmark_frame=benchmark)['metrics']
    metrics = build()
    assert metrics['days_under_rs_ma21'] == 2
    assert metrics['rs_as_of'] == str(index[-2].date())
    asset.loc[index[-1], 'IsFinal'] = True
    benchmark.loc[index[-1], 'IsFinal'] = False
    assert build()['days_under_rs_ma21'] == 2
    benchmark.loc[index[-1], 'IsFinal'] = True
    assert build()['days_under_rs_ma21'] == 3


def test_missing_asset_close_interrupts_rs_confirmation():
    from app.domain.sell.metrics import build_sell_decision_metrics_payload
    index = pd.date_range('2026-01-01', periods=60, freq='B')
    close = [100.0] * 56 + [95.0, 94.0, 93.0, 92.0]
    asset = pd.DataFrame({'Open': close, 'High': close, 'Low': close, 'Close': close, 'Volume': 1000, 'IsFinal': True}, index=index).drop(index[-3])
    benchmark = pd.DataFrame({'Close': 100.0, 'IsFinal': True}, index=index)
    metrics = build_sell_decision_metrics_payload(ticker='TEST', buy_date=index[-10], buy_price=90, shares=10, price_frame=asset, benchmark_frame=benchmark)['metrics']
    assert metrics['days_under_rs_ma21'] == 2
