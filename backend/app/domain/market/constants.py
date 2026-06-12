DEFAULT_MARKET_UNIVERSE_KEY = "us_largecap_starter"

DEFAULT_MARKET_UNIVERSE_TICKERS = [
    "SPY",
    "QQQ",
    "IWM",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "TSLA",
    "LLY",
    "JPM",
    "V",
    "MA",
    "COST",
    "NFLX",
    "AMD",
    "CRM",
    "ORCL",
    "ADBE",
    "XOM",
    "UNH",
    "HD",
    "PG",
    "WMT",
]

MARKET_INDEX_TICKERS = ["^GSPC", "^IXIC", "^RUT"]

MARKET_INDEX_FALLBACK_TICKERS = {
    "^GSPC": ["SPY"],
    "^IXIC": ["QQQ"],
    "^RUT": ["IWM"],
}

EQUAL_WEIGHT_MARKET_TICKERS = ["RSP", "QQEW"]

MARKET_CORE_PRICE_TICKERS = list(
    dict.fromkeys([*MARKET_INDEX_TICKERS, *EQUAL_WEIGHT_MARKET_TICKERS, *DEFAULT_MARKET_UNIVERSE_TICKERS])
)

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Health Care",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLE": "Energy",
    "XLB": "Materials",
    "XLC": "Communication Services",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
}

SECTOR_ETF_TICKERS = list(SECTOR_ETFS.keys())
