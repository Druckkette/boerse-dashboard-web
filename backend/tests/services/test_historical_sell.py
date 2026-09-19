from datetime import date
from types import SimpleNamespace
import json

import pandas as pd
from app.services.historical_sell import assess_historical_sale


def test_existing_engine_receives_only_pre_sale_history():
    queries = []
    bars = [SimpleNamespace(date=day.date(), open=100+i*.1, high=102+i*.1,
            low=98+i*.1, close=100+i*.1, volume=1000000+i*100)
            for i, day in enumerate(pd.bdate_range("2023-01-02", "2024-01-30"))]
    class DB:
        def scalars(self, query):
            queries.append(query)
            return bars
    event = {"ticker": "TEST", "date": "2024-01-31", "currency": "USD", "shares": 2,
             "unallocated": 0, "allocations": [{"cost_basis": 240, "buy_date": "2023-12-01"}]}
    result = assess_historical_sale(DB(), event)
    assert result["status"] == "available"
    assert result["as_of"] == "2024-01-30"
    assert result["evaluation"]
    json.dumps(result, allow_nan=False)
    for query in queries:
        assert "price_bars.date <" in str(query)
        assert date(2024, 1, 31) in query.compile().params.values()


def test_unknown_cost_never_generates_a_score():
    result = assess_historical_sale(None, {"ticker": "TEST", "date": "2024-01-31",
        "allocations": [], "unallocated": 1})
    assert result["status"] == "missing" and "evaluation" not in result
