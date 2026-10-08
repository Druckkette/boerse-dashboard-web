"""Disposable HTTP fixture for the production frontend build; never reads NAS data."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import fakeredis
import uvicorn
from app.api.v1 import stocks as stocks_api, market as market_api
from app.core_config import get_settings
from app.domain.stocks.assessment import compute_stock_assessment
from app.domain.sell import service as sell_service
from app.repositories import jobs as repository
from app.schemas import PriceHistoryResponse, PriceBarPoint, StockSearchResponse, StockFundamentalsResponse, StockSignalChangesResponse, RsRatingDetailResponse, Institutional13FTrendResponse
from app.services import beta, stocks, jobs
from app.main import create_app
from tests.helpers.sell_fixture_data import fixture_price_bars

cache = fakeredis.FakeRedis(decode_responses=True)
beta.redis_client = lambda: cache
import redis
redis.Redis.from_url = lambda *a, **kw: cache
repository._with_db = lambda operation, *, fallback: fallback()
created = {}
state = {"NVDA": False, "AAPL": True}
scores = {}
stocks.fundamentals_repository.get_instrument_profile = lambda ticker: {"ticker": ticker}
beta.stock_freshness = lambda ticker: {"ticker": ticker, "fresh": state.get(ticker, True), "as_of": "2026-10-07"}
def enqueue(name, **kwargs):
    job_id = kwargs["args"][0]
    created[job_id] = time.monotonic()
    return SimpleNamespace(id="fixture-celery-id")
jobs.celery_app.send_task = enqueue
original_status = beta.refresh_status
def status(handle, capability):
    record = beta._load_record(cache, handle)
    if record and time.monotonic() - created.get(record["internal_id"], time.monotonic()) > 2:
        ticker = record["ticker"]
        state[ticker] = True
        scores[ticker] = 777.77
        repository.mark_done(record["internal_id"])
    return original_status(handle, capability)
beta.refresh_status = status

def assessment(ticker):
    result = stocks._to_response(compute_stock_assessment(ticker, fixture_price_bars(ticker)))
    result.metrics.last_close = scores.get(ticker, 123.45)
    result.scores.overall = 90 if ticker in scores else 50
    result.technical_v2["score"] = 91 if ticker in scores else 30
    return result
stocks_api.get_stock_assessment = assessment
def comparison(*, tickers, limit=12):
    from app.schemas import StockAssessmentCompareResponse
    requested = stocks._parse_compare_tickers(tickers, limit=limit)
    rows = [stocks._to_compare_item(compute_stock_assessment(ticker, fixture_price_bars(ticker)),
                                   name=ticker, rs_context={}) for ticker in requested]
    # Include an incomplete row to exercise the warning after beta projection
    # removes missing_tickers, just as the live NAS response does.
    rows[-1] = rows[-1].model_copy(update={"source": "missing", "data_status": "missing"})
    return StockAssessmentCompareResponse(as_of="2026-10-07", source="partial",
                                         requested_tickers=requested, missing_tickers=[requested[-1]], rows=rows)
stocks_api.get_stock_assessment_compare = comparison
stocks_api.get_stock_assessment_ranking = lambda **kw: __import__('app.schemas', fromlist=['StockAssessmentRankingResponse']).StockAssessmentRankingResponse(as_of="2026-10-07", source="missing", rows=[])
stocks_api.search_stocks = lambda q, **kw: StockSearchResponse(query=q, rows=[{"ticker": "NVDA", "name": "NVIDIA", "exchange": "NASDAQ"}])
stocks_api.get_stock_fundamentals = lambda ticker: StockFundamentalsResponse(ticker=ticker, source="missing", item=None, as_of="2026-10-07")
stocks_api.get_relative_strength_for_ticker = lambda ticker: RsRatingDetailResponse(ticker=ticker, source="missing", found=False, item=None, as_of="2026-10-07")
stocks_api.get_institutional_13f_for_ticker = lambda ticker: Institutional13FTrendResponse(ticker=ticker, source="missing", item=None, as_of="2026-10-07")
stocks_api.get_stock_signal_changes = lambda ticker: StockSignalChangesResponse(ticker=ticker, current_as_of="2026-10-07", changes=[])
def history(ticker, **kw):
    return PriceHistoryResponse(ticker=ticker, currency="USD", range=kw.get("range_key", "1y"), source="database", data_status="fresh", as_of="2026-10-07",
                                points=[PriceBarPoint(date=bar.date.isoformat(), open=bar.open, high=bar.high, low=bar.low, close=bar.close, volume=bar.volume) for bar in fixture_price_bars(ticker)],
                                last_close=scores.get(ticker, 123.45), last_date="2026-10-07")
stocks_api.get_price_history = history
beta.home_dashboard = lambda: {"generated_at": "2026-10-08T10:00:00Z", "market": {"indices": [], "phase": None, "phase_label": "Marktstand fehlt", "status": "missing", "session": {"phase": "closed", "last_completed_as_of": "2026-10-07"}}, "opportunities": [], "industry_groups": []}
sell_service.prices_repository.list_price_bars = fixture_price_bars
sell_service.yahoo_quote_currency = lambda ticker: "USD"
sell_service.cached_currency_usd_factor = lambda currency: 1 if currency == "USD" else 1.2
# If any personal API is accidentally allowed, its unmistakable payload makes failures visible.
app = create_app()
@app.get("/__fixture/stats")
def stats():
    return {"enqueued": len(created), "by_ticker": state}
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18380, access_log=False)
