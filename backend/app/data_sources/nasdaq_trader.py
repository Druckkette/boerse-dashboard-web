from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd
import requests


NASDAQ_LISTED_URLS = [
    "https://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
]
OTHER_LISTED_URLS = [
    "https://ftp.nasdaqtrader.com/SymbolDirectory/otherlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
]


@dataclass(frozen=True)
class UniverseFetchResult:
    key: str
    name: str
    source: str
    tickers: list[str]
    metadata: dict
    instruments: dict[str, dict] | None = None


def fetch_us_common_stock_universe(*, timeout: int = 30) -> UniverseFetchResult:
    nasdaq_tickers, nasdaq_source, nasdaq_text = _fetch_first_working(NASDAQ_LISTED_URLS, parse_nasdaq_listed_text, timeout)
    nyse_tickers, nyse_source, nyse_text = _fetch_first_working(OTHER_LISTED_URLS, parse_otherlisted_text, timeout)
    tickers = list(dict.fromkeys([*nasdaq_tickers, *nyse_tickers]))
    if len(tickers) < 100:
        raise RuntimeError("Nasdaq Trader universe returned too few common-stock tickers.")
    return UniverseFetchResult(
        key="us_common_stocks",
        name="US Common Stocks",
        source="nasdaq_trader",
        tickers=tickers,
        metadata={
            "nasdaq_count": len(nasdaq_tickers),
            "nyse_count": len(nyse_tickers),
            "nasdaq_source_url": nasdaq_source,
            "nyse_source_url": nyse_source,
        },
        instruments={**_listing_details(nasdaq_text, "symbol", default_exchange="NASDAQ"),
                     **_listing_details(nyse_text, "cqs symbol", "nasdaq symbol", "act symbol")},
    )


def parse_nasdaq_listed_text(text: str) -> list[str]:
    df = _read_pipe_table(text)
    if df.empty:
        return []
    cols = _lower_cols(df)
    symbol_col = cols.get("symbol")
    if symbol_col is None:
        return []
    df = _filter_common_stock_rows(df, cols)
    symbols = []
    for _, row in df.iterrows():
        name = row.get(cols.get("security name", ""), "")
        if not _looks_like_common_equity_name(name):
            continue
        symbol = str(row.get(symbol_col, "") or "")
        symbols.append(symbol)
    return normalize_tickers(symbols)


def parse_otherlisted_text(text: str) -> list[str]:
    df = _read_pipe_table(text)
    if df.empty:
        return []
    cols = _lower_cols(df)
    exchange_col = cols.get("exchange")
    if exchange_col is None:
        return []
    df[exchange_col] = df[exchange_col].fillna("").astype(str).str.strip().str.upper()
    df = df[df[exchange_col].isin({"A", "N", "P", "Z"})]
    df = _filter_common_stock_rows(df, cols)

    cqs_col = cols.get("cqs symbol")
    nasdaq_col = cols.get("nasdaq symbol")
    act_col = cols.get("act symbol")
    name_col = cols.get("security name")
    symbols = []
    for _, row in df.iterrows():
        if not _looks_like_common_equity_name(row.get(name_col, "") if name_col else ""):
            continue
        for col in (cqs_col, nasdaq_col, act_col):
            if col is None:
                continue
            candidate = str(row.get(col, "") or "").strip()
            if candidate:
                symbols.append(candidate)
                break
    return normalize_tickers(symbols)


def normalize_tickers(values: list[str]) -> list[str]:
    tickers = []
    for value in values:
        ticker = str(value or "").strip().upper().replace(".", "-").replace("/", "-").replace(" ", "")
        if not ticker or ticker in {"NAN", "NONE", "NULL", "N/A", "USD", "CASH", "-"}:
            continue
        if not re.fullmatch(r"[A-Z0-9\-]+", ticker):
            continue
        tickers.append(ticker)
    return list(dict.fromkeys(tickers))


def _fetch_first_working(urls: list[str], parser, timeout: int) -> tuple[list[str], str, str]:
    headers = {"User-Agent": "boerse-dashboard-web", "Accept": "text/plain,*/*"}
    best: tuple[list[str], str, str] = ([], "", "")
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            tickers = parser(response.text)
            if len(tickers) > len(best[0]):
                best = (tickers, url, response.text)
            if len(tickers) >= 500:
                return tickers, url, response.text
        except requests.RequestException:
            continue
    return best


def _listing_details(text: str, *symbol_columns: str, default_exchange: str = "") -> dict[str, dict]:
    from app.domain.stocks.instrument_type import classify_instrument

    frame = _read_pipe_table(text)
    if frame.empty:
        return {}
    columns = _lower_cols(frame)
    details: dict[str, dict] = {}
    for _, row in frame.iterrows():
        symbol = next((str(row.get(columns[col]) or "").strip() for col in symbol_columns
                       if col in columns and str(row.get(columns[col]) or "").strip()), "")
        clean = normalize_tickers([symbol])
        if not clean:
            continue
        name = str(row.get(columns.get("security name", ""), "") or "")
        etf = str(row.get(columns.get("etf", ""), "") or "")
        nextshares = str(row.get(columns.get("nextshares", ""), "") or "")
        exchange_code = str(row.get(columns.get("exchange", ""), "") or "").strip().upper()
        exchange = default_exchange or {"A": "NYSE American", "N": "NYSE", "P": "NYSE Arca", "Z": "Cboe BZX"}.get(exchange_code, exchange_code)
        details[clean[0]] = {"name": name, "etf": etf, "nextshares": nextshares, "exchange": exchange,
                             "instrument_type": classify_instrument(ticker=clean[0], name=name, etf=etf, nextshares=nextshares),
                             "classification_source": "nasdaq_trader"}
    return details


def _read_pipe_table(text: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(text), sep="|", dtype=str, engine="python")
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df.columns = [str(column).strip() for column in df.columns]
    first_col = df.columns[0]
    df = df[~df[first_col].fillna("").str.startswith("File Creation Time", na=False)].copy()
    return df.dropna(how="all")


def _lower_cols(df: pd.DataFrame) -> dict[str, str]:
    return {str(column).strip().lower(): column for column in df.columns}


def _filter_common_stock_rows(df: pd.DataFrame, cols: dict[str, str]) -> pd.DataFrame:
    nextshares_col = cols.get("nextshares")
    for column_name in ("etf", "test issue"):
        column = cols.get(column_name)
        if column is not None:
            df[column] = df[column].fillna("").astype(str).str.strip().str.upper()
            df = df[df[column] != "Y"]
    if nextshares_col is not None:
        df[nextshares_col] = df[nextshares_col].fillna("").astype(str).str.strip().str.upper()
        df = df[df[nextshares_col] != "Y"]
    return df


def _looks_like_common_equity_name(name: object) -> bool:
    low = f" {str(name or '').lower()} "
    if not low.strip():
        return False
    reject_patterns = (
        r"\bpreferred\b",
        r"\bpreference shares?\b",
        r"\bpfd\b",
        r"\bdepositary\b",
        r"\bdep(?:ositary)? shs\b",
        r"\bperpetual non cumulative\b",
        r"\bwarrants?\b",
        r"\brights?\b",
        r"\bunits?\b",
        r"\bnotes?\b",
        r"\bbonds?\b",
        r"\bdebentures?\b",
        r"\betn\b",
        r"\betf\b",
        r"\bclosed\s+end\b",
        r"\bmutual\s+fund\b",
        r"\btrust\s+units?\b",
        r"\bcapital trust\b",
        r"\btrust certificates?\b",
        r"\btrust preference securities?\b",
        r"\bcorp backed tr certs?\b",
        r"\bsce trust\s+[ivx]+\b",
        r"\b(?:gold|silver|commodity|bitcoin|ether(?:eum)?) trust\b",
        r"\b\d+(?:\.\d+)?%\s+series\s+[a-z]\b",
        r"\bzones\b",
    )
    return not any(re.search(pattern, low) for pattern in reject_patterns)
