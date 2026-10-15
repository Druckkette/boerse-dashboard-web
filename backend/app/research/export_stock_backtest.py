"""Export public research inputs and global strategy parameters without portfolio data."""
import datetime
import hashlib
import json
import sys
from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.settings import get_app_settings as runtime_settings
from app.services.market_calendar import completed_us_market_session
def main():
    cutoff=completed_us_market_session().date
    with SessionLocal() as db:
     db.execute(text("SET statement_timeout='60000'"))
     opportunities=[dict(r) for r in db.execute(text('select * from daily_stock_opportunities where rank<=20 order by as_of,rank')).mappings()]
     universe=[dict(r) for r in db.execute(text("select i.ticker,i.name,i.currency,um.valid_from from universe_members um join instruments i on i.id=um.instrument_id join universes u on u.id=um.universe_id where u.key='us_common_stocks' and um.valid_to is null order by i.ticker")).mappings()]
     recommended={r['ticker'] for r in opportunities if r['rank']<=3}
     sample=sorted([r['ticker'] for r in universe],key=lambda t:hashlib.sha256(('sell-backtest-2026-10-15:'+t).encode()).hexdigest())[:40]
     tickers=sorted(recommended|set(sample)|{'SPY','QQQ'})
     print('export tickers '+str(len(tickers)),file=sys.stderr)
     prices=[]
     for ticker in tickers:
      rows=db.execute(text("select distinct on (b.date) b.date,b.open,b.high,b.low,b.close,b.adj_close,b.volume,b.source,b.fetched_at from price_bars b join instruments i on i.id=b.instrument_id where i.ticker=:ticker and b.date<=:cutoff order by b.date,b.fetched_at desc nulls last,b.source"),{'ticker':ticker,'cutoff':cutoff}).mappings()
      prices.extend({'ticker':ticker,**dict(r)} for r in rows)
      print(ticker+' exported',file=sys.stderr)
     settings=runtime_settings()
    print(json.dumps({'cutoff':cutoff,'exported_at':datetime.datetime.now(datetime.timezone.utc),'universe':universe,'opportunities':opportunities,'sample_tickers':sample,'prices':prices,'sell_setup':settings.sell_rule_setup},default=str))


if __name__ == "__main__":
    main()
