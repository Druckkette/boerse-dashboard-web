from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import StringIO

import pandas as pd


ISIN_TO_YAHOO: dict[str, str] = {
    "US0378331005": "AAPL",
    "US5949181045": "MSFT",
    "US67066G1040": "NVDA",
    "US02079K3059": "GOOGL",
    "US0231351067": "AMZN",
    "US30303M1027": "META",
    "US88160R1014": "TSLA",
    "US1912161007": "KO",
    "US8740391003": "TSM",
    "DE0007236101": "SIE.DE",
    "DE0007164600": "SAP.DE",
    "DE000BAY0017": "BAYN.DE",
    "DE0007030009": "RHM.DE",
    "DE000ENER6Y0": "ENR.DE",
    "DE0007664039": "VOW3.DE",
    "DE000HLAG475": "HLAG.DE",
    "DE000A0WMPJ6": "AIXA.DE",
    "DE000A0Z1JH9": "PSAN.DE",
    "DE000RENK730": "R3NK.DE",
    "DE000A2N4H07": "WEW.DE",
    "KYG7397A1067": "1337.HK",
    "US20717M1036": "CFLT",
    "US4878361082": "K",
}

REQUIRED_TRANSACTION_COLUMNS = {"date", "type", "asset_class", "name", "symbol", "shares", "price", "currency"}
POSITION_ASSET_CLASSES = {"STOCK", "FUND"}


@dataclass(frozen=True)
class TradeRepublicTransactionRow:
    date: pd.Timestamp
    event_ts: pd.Timestamp
    transaction_type: str
    asset_class: str
    name: str
    isin: str
    shares: float
    price: float
    currency: str
    amount: float
    fee: float
    tax: float
    external_id: str
    raw: dict

    @property
    def cash_delta(self) -> float:
        return self.amount + self.fee + self.tax


@dataclass(frozen=True)
class TradeRepublicPosition:
    isin: str
    ticker: str
    name: str
    shares: float
    avg_buy_price: float
    first_buy_date: str
    currency: str
    asset_class: str


@dataclass(frozen=True)
class TradeRepublicSkippedPosition:
    isin: str
    name: str
    shares: float
    asset_class: str
    reason: str


def normalize_ticker(value: str) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def parse_transaction_export_csv(content: str) -> list[TradeRepublicTransactionRow]:
    if not content.strip():
        raise ValueError("CSV-Inhalt ist leer.")
    try:
        df = pd.read_csv(StringIO(content))
    except Exception as exc:
        raise ValueError(f"CSV konnte nicht gelesen werden: {exc}") from exc
    if df.empty:
        raise ValueError("Die CSV-Datei ist leer.")

    normalized_columns = {str(col).strip(): col for col in df.columns}
    missing = sorted(REQUIRED_TRANSACTION_COLUMNS - set(normalized_columns))
    if missing:
        raise ValueError(f"Fehlende Spalten: {', '.join(missing)}")

    df = df.rename(columns={original: str(original).strip() for original in df.columns}).copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", utc=True).dt.tz_convert(None)
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce", utc=True).dt.tz_convert(None)
        df["event_ts"] = df["datetime"].fillna(df["date"])
    else:
        df["event_ts"] = df["date"]
    df = df.dropna(subset=["date"]).sort_values("event_ts", kind="stable").reset_index(drop=True)
    if df.empty:
        raise ValueError("Keine gültigen Datumswerte im Transaktionsexport.")

    for col in ("shares", "price", "amount", "fee", "tax"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0) if col in df.columns else 0.0

    rows: list[TradeRepublicTransactionRow] = []
    for order, record in enumerate(df.to_dict("records")):
        raw = {str(key): _json_safe(value) for key, value in record.items()}
        transaction_type = _string_field(record.get("type")).upper()
        asset_class = _string_field(record.get("asset_class")).upper()
        isin = _string_field(record.get("symbol")).upper()
        event_ts = pd.Timestamp(record.get("event_ts")).tz_localize(None)
        day = pd.Timestamp(record.get("date")).tz_localize(None).normalize()
        external_id = _external_id(record, order)
        rows.append(
            TradeRepublicTransactionRow(
                date=day,
                event_ts=event_ts,
                transaction_type=transaction_type,
                asset_class=asset_class,
                name=_string_field(record.get("name")),
                isin=isin,
                shares=float(record.get("shares") or 0.0),
                price=float(record.get("price") or 0.0),
                currency=(_string_field(record.get("currency")) or "EUR").upper(),
                amount=float(record.get("amount") or 0.0),
                fee=float(record.get("fee") or 0.0),
                tax=float(record.get("tax") or 0.0),
                external_id=external_id,
                raw=raw,
            )
        )
    return rows


def resolve_isin_mappings(
    rows: list[TradeRepublicTransactionRow],
    *,
    saved_mappings: dict[str, str] | None = None,
    overrides: dict[str, str] | None = None,
) -> list[dict]:
    saved = {str(key).upper().strip(): normalize_ticker(value) for key, value in (saved_mappings or {}).items()}
    manual = {str(key).upper().strip(): normalize_ticker(value) for key, value in (overrides or {}).items()}
    diagnostics: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        if row.asset_class not in POSITION_ASSET_CLASSES or not row.isin or row.isin in seen:
            continue
        seen.add(row.isin)
        ticker = manual.get(row.isin) or saved.get(row.isin) or normalize_ticker(ISIN_TO_YAHOO.get(row.isin, ""))
        source = "manual" if manual.get(row.isin) else "saved" if saved.get(row.isin) else "static" if ticker else "missing"
        diagnostics.append(
            {
                "isin": row.isin,
                "name": row.name,
                "asset_class": row.asset_class,
                "ticker": ticker,
                "source": source,
            }
        )
    return diagnostics


def reconstruct_open_positions(
    rows: list[TradeRepublicTransactionRow],
    ticker_by_isin: dict[str, str],
) -> tuple[list[TradeRepublicPosition], list[TradeRepublicSkippedPosition]]:
    states: dict[str, dict] = {}
    for row in rows:
        if not row.isin:
            continue
        state = states.setdefault(
            row.isin,
            {
                "shares": 0.0,
                "cost": 0.0,
                "first_buy_date": None,
                "name": row.name,
                "asset_class": row.asset_class,
                "currency": row.currency or "EUR",
            },
        )
        state["name"] = row.name or state["name"]
        state["asset_class"] = row.asset_class or state["asset_class"]
        state["currency"] = row.currency or state["currency"]
        raw_shares = abs(float(row.shares or 0.0))
        price = float(row.price or 0.0)
        typ = row.transaction_type

        if typ in {"BUY", "TRANSFER_IN"}:
            if state["shares"] <= 0:
                state["first_buy_date"] = row.date
            state["shares"] += raw_shares
            state["cost"] += raw_shares * price
        elif typ == "SELL_CANCELLED":
            avg = (state["cost"] / state["shares"]) if state["shares"] > 0 else price
            state["shares"] += raw_shares
            state["cost"] += raw_shares * avg
        elif typ in {"SELL", "TRANSFER_OUT", "WARRANT_EXERCISE", "INSOLVENCY_PROCEEDINGS", "DELISTED", "EXPIRATION"}:
            sell_shares = min(raw_shares, max(state["shares"], 0.0))
            avg = (state["cost"] / state["shares"]) if state["shares"] > 0 else 0.0
            state["shares"] -= sell_shares
            state["cost"] -= sell_shares * avg
        elif typ == "SPLIT":
            state["shares"] = max(raw_shares, 0.0)

        if state["shares"] <= 1e-9:
            state["shares"] = 0.0
            state["cost"] = 0.0
            state["first_buy_date"] = None

    positions: list[TradeRepublicPosition] = []
    skipped: list[TradeRepublicSkippedPosition] = []
    for isin, state in states.items():
        shares = float(state["shares"] or 0.0)
        if shares <= 1e-9:
            continue
        asset_class = str(state["asset_class"] or "").upper()
        if asset_class not in POSITION_ASSET_CLASSES:
            skipped.append(
                TradeRepublicSkippedPosition(
                    isin=isin,
                    name=str(state["name"] or isin),
                    shares=shares,
                    asset_class=asset_class or "UNKNOWN",
                    reason="Anlageklasse wird nicht automatisch als Aktie/Fonds importiert.",
                )
            )
            continue
        ticker = normalize_ticker(ticker_by_isin.get(isin, ""))
        if not ticker:
            skipped.append(
                TradeRepublicSkippedPosition(
                    isin=isin,
                    name=str(state["name"] or isin),
                    shares=shares,
                    asset_class=asset_class,
                    reason="Keine Yahoo-Ticker-Zuordnung vorhanden.",
                )
            )
            continue
        avg = float(state["cost"] or 0.0) / shares if shares > 0 else 0.0
        first = state["first_buy_date"]
        positions.append(
            TradeRepublicPosition(
                isin=isin,
                ticker=ticker,
                name=str(state["name"] or ticker),
                shares=shares,
                avg_buy_price=avg,
                first_buy_date=pd.Timestamp(first).date().isoformat() if first is not None else "",
                currency=str(state["currency"] or "EUR").upper(),
                asset_class=asset_class,
            )
        )
    return positions, skipped


def estimate_cash_balance(rows: list[TradeRepublicTransactionRow]) -> float:
    return round(sum(row.cash_delta for row in rows), 2)


def _external_id(record: dict, order: int) -> str:
    parts = [
        str(record.get("datetime") or record.get("date") or ""),
        str(record.get("type") or ""),
        str(record.get("asset_class") or ""),
        str(record.get("symbol") or ""),
        str(record.get("shares") or ""),
        str(record.get("price") or ""),
        str(record.get("amount") or ""),
        str(record.get("fee") or ""),
        str(record.get("tax") or ""),
        str(order),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"tr:{digest}"


def _json_safe(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _string_field(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()
