from __future__ import annotations

import os
import re
import tempfile
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pandas as pd
import requests


SEC_13F_DATASETS_URL = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
SEC_COMPANY_TICKERS_EXCHANGE_URL = "https://www.sec.gov/files/company_tickers_exchange.json"

DEFAULT_CUSIP_OVERRIDES = {
    "02079K305": "GOOGL",
    "02079K107": "GOOG",
    "084670108": "BRK-A",
    "084670702": "BRK-B",
    "35137L105": "FOXA",
    "35137L204": "FOX",
    "65249B109": "NWSA",
    "65249B208": "NWS",
    "115637100": "BF-A",
    "115637209": "BF-B",
    "526057104": "LEN",
    "526057302": "LEN-B",
}

ProgressCallback = Callable[[int, str, str, dict[str, Any]], None]


@dataclass(frozen=True)
class DatasetLink:
    label: str
    url: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1]

    @property
    def sort_key(self) -> tuple[int, int]:
        text = f"{self.label} {self.url}".lower()
        match = re.search(r"(20\d{2})\D*q([1-4])", text)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 0, 0


@dataclass(frozen=True)
class SymbolRecord:
    ticker: str
    name: str
    exchange: str = ""

    @property
    def base_key(self) -> str:
        return normalize_issuer_name(self.name)

    @property
    def share_class(self) -> str:
        return extract_share_class(self.name)


@dataclass(frozen=True)
class Sec13FBuildResult:
    payload: dict[str, Any]
    mapping_rows: list[dict[str, Any]]
    unmatched_rows: list[dict[str, Any]]
    metadata: dict[str, Any]


class SECAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value for key, value in attrs}
        self._href = attrs_dict.get("href")
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        text = " ".join("".join(self._text_parts).split())
        self.links.append((text, self._href))
        self._href = None
        self._text_parts = []


def build_institutional_13f_payload(
    *,
    universe: Iterable[str],
    cache_dir: Path,
    dataset_count: int = 2,
    large_holder_min_value_usd: float = 10_000_000,
    chunksize: int = 250_000,
    cusip_overrides: dict[str, str] | None = None,
    progress: ProgressCallback | None = None,
    sec_user_agent: str = "",
) -> Sec13FBuildResult:
    tickers = {normalize_ticker(value) for value in universe}
    tickers.discard("")
    if not tickers:
        raise RuntimeError("13F refresh requires at least one ticker in the universe.")

    effective_dataset_count = max(2, min(6, int(dataset_count or 2)))
    _emit(progress, 8, "SEC Dataset-Liste laden", "SEC Form-13F-Datensaetze werden gesucht.", {})
    dataset_links = list_sec_13f_datasets(sec_user_agent=sec_user_agent)[:effective_dataset_count]

    _emit(
        progress,
        15,
        "SEC ZIP-Dateien laden",
        f"{len(dataset_links)} SEC-Datensaetze werden aus Cache oder Netzwerk geladen.",
        {"dataset_count": len(dataset_links)},
    )
    zip_paths = [download_dataset(link, cache_dir, sec_user_agent=sec_user_agent) for link in dataset_links]

    _emit(progress, 28, "Submission-Index lesen", "13F-HR-Submissions werden gefiltert.", {})
    submission_indexes = [load_submission_index(path) for path in zip_paths]
    all_submissions = pd.concat(submission_indexes, ignore_index=True)
    period_counts = (
        all_submissions.groupby("period_date")["ACCESSION_NUMBER"].nunique().sort_index(ascending=False)
    )
    periods = [period.isoformat() for period in period_counts.index.tolist()]
    if len(periods) < 2:
        raise RuntimeError("Not enough 13F reporting periods found for a trend comparison.")
    current_period, previous_period = periods[0], periods[1]

    _emit(
        progress,
        42,
        "Holdings aggregieren",
        f"Vergleich {previous_period} -> {current_period}; INFOTABLE wird chunkweise gelesen.",
        {"current_period": current_period, "previous_period": previous_period},
    )
    holdings, cusip_meta = process_holdings(
        zip_paths=zip_paths,
        submission_indexes=submission_indexes,
        target_periods={current_period, previous_period},
        large_holder_min_value_usd=large_holder_min_value_usd,
        chunksize=chunksize,
    )

    _emit(progress, 68, "CUSIP Mapping", "SEC Company-Ticker werden mit CUSIPs gemappt.", {})
    records = fetch_sec_company_symbol_records(tickers, sec_user_agent=sec_user_agent)
    overrides = load_default_overrides(tickers)
    for raw_cusip, raw_ticker in (cusip_overrides or {}).items():
        cusip = normalize_cusip(raw_cusip)
        ticker = normalize_ticker(raw_ticker)
        if cusip and ticker and ticker in tickers:
            overrides[cusip] = ticker
    mapping, unmatched = build_cusip_mapping(cusip_meta, tickers, records, overrides)

    _emit(progress, 78, "Ticker-Trends berechnen", "13F-Halter und Werte werden je Ticker aggregiert.", {})
    ticker_agg = aggregate_by_ticker(
        holdings,
        mapping,
        large_holder_min_value_usd=large_holder_min_value_usd,
    )

    current_cusips = set(holdings.loc[holdings["period"] == current_period, "CUSIP"])
    mapped_current_cusips = set(mapping["cusip"]) & current_cusips if not mapping.empty else set()
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "source": "SEC Form 13F Data Sets",
        "source_url": SEC_13F_DATASETS_URL,
        "current_period": current_period,
        "previous_period": previous_period,
        "datasets": [{"label": link.label, "url": link.url} for link in dataset_links],
        "universe_count": len(tickers),
        "large_holder_min_value_usd": large_holder_min_value_usd,
        "matched_cusips": int(len(mapping)),
        "current_cusips": int(len(current_cusips)),
        "current_cusip_mapping_coverage": float(len(mapped_current_cusips) / max(len(current_cusips), 1)),
        "matched_tickers": int(ticker_agg["ticker"].nunique()) if not ticker_agg.empty else 0,
        "manager_names_included": False,
    }
    payload, rows = build_outputs(ticker_agg, mapping, holdings, current_period, previous_period, metadata)
    unmatched_enriched = enrich_unmatched_cusips(unmatched, holdings, current_period)
    _emit(
        progress,
        88,
        "13F Payload fertig",
        f"{len(rows)} Ticker-Trends berechnet.",
        {"records_seen": len(rows), "matched_tickers": metadata["matched_tickers"]},
    )
    return Sec13FBuildResult(
        payload=payload,
        mapping_rows=_dataframe_records(mapping),
        unmatched_rows=_dataframe_records(unmatched_enriched),
        metadata=metadata,
    )


def sec_headers(sec_user_agent: str = "") -> dict[str, str]:
    user_agent = (sec_user_agent or os.environ.get("SEC_USER_AGENT", "")).strip()
    if not user_agent:
        raise RuntimeError(
            "SEC_USER_AGENT is not set. Configure it as '<project> <contact-email>' before running 13F jobs."
        )
    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


def fetch_text(url: str, timeout: int = 30, *, sec_user_agent: str = "") -> str:
    response = requests.get(url, headers=sec_headers(sec_user_agent), timeout=timeout)
    response.raise_for_status()
    return response.text


def list_sec_13f_datasets(*, sec_user_agent: str = "") -> list[DatasetLink]:
    parser = SECAnchorParser()
    parser.feed(fetch_text(SEC_13F_DATASETS_URL, sec_user_agent=sec_user_agent))
    links: list[DatasetLink] = []
    seen: set[str] = set()
    for label, href in parser.links:
        if "form13f.zip" not in href.lower():
            continue
        url = urljoin(SEC_13F_DATASETS_URL, href)
        if url in seen:
            continue
        seen.add(url)
        links.append(DatasetLink(label=label, url=url))
    links.sort(key=lambda item: item.sort_key, reverse=True)
    if not links:
        raise RuntimeError("No SEC 13F data set links found.")
    return links


def download_dataset(link: DatasetLink, cache_dir: Path, *, sec_user_agent: str = "") -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / link.filename
    if target.exists() and target.stat().st_size > 1_000_000:
        return target

    tmp_path: Path | None = None
    try:
        with requests.get(link.url, headers=sec_headers(sec_user_agent), stream=True, timeout=120) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile("wb", delete=False, dir=cache_dir) as tmp:
                tmp_path = Path(tmp.name)
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        tmp.write(chunk)
        tmp_path.replace(target)
        return target
    except Exception:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def fetch_sec_company_symbol_records(universe: set[str], *, sec_user_agent: str = "") -> list[SymbolRecord]:
    response = requests.get(SEC_COMPANY_TICKERS_EXCHANGE_URL, headers=sec_headers(sec_user_agent), timeout=30)
    response.raise_for_status()
    payload = response.json()
    fields = payload.get("fields") or []
    rows = payload.get("data") or []
    try:
        ticker_index = fields.index("ticker")
        name_index = fields.index("name")
        exchange_index = fields.index("exchange")
    except ValueError as exc:
        raise RuntimeError("SEC company_tickers_exchange.json has an unexpected format.") from exc

    records: list[SymbolRecord] = []
    for row in rows:
        ticker = normalize_ticker(row[ticker_index] if len(row) > ticker_index else "")
        if not ticker or (universe and ticker not in universe):
            continue
        name = str(row[name_index] if len(row) > name_index else "").strip()
        exchange = str(row[exchange_index] if len(row) > exchange_index else "").strip()
        if name:
            records.append(SymbolRecord(ticker=ticker, name=name, exchange=exchange))
    return records


def load_submission_index(zip_path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("SUBMISSION.tsv") as handle:
            df = pd.read_csv(
                handle,
                sep="\t",
                dtype=str,
                usecols=["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"],
            )
    df["period_date"] = df["PERIODOFREPORT"].map(parse_sec_date)
    df["filing_date"] = df["FILING_DATE"].map(parse_sec_date)
    cik_digits = df["CIK"].astype(str).str.replace(r"\D", "", regex=True)
    df["CIK"] = cik_digits.where(cik_digits.str.len() > 0).str.zfill(10)
    df = df[df["ACCESSION_NUMBER"].notna()]
    df = df[df["period_date"].notna()]
    df = df[df["CIK"].notna()]
    df = df[df["SUBMISSIONTYPE"].astype(str).str.upper().str.startswith("13F-HR")]
    return df


def value_multiplier_for_period(period: str) -> int:
    parsed = parse_sec_date(period)
    if parsed and parsed.year <= 2022:
        return 1000
    return 1


def process_holdings(
    zip_paths: list[Path],
    submission_indexes: list[pd.DataFrame],
    target_periods: set[str],
    large_holder_min_value_usd: float,
    chunksize: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    accession_to_period: dict[str, str] = {}
    accession_to_cik: dict[str, str] = {}
    for df in submission_indexes:
        target_rows = df[df["period_date"].map(lambda d: d.isoformat()).isin(target_periods)]
        for _, row in target_rows.iterrows():
            accession = str(row["ACCESSION_NUMBER"])
            accession_to_period[accession] = row["period_date"].isoformat()
            accession_to_cik[accession] = str(row["CIK"])

    if not accession_to_period:
        raise RuntimeError("No 13F-HR submissions found for the selected reporting periods.")

    holder_groups: list[pd.DataFrame] = []
    meta_groups: list[pd.DataFrame] = []
    usecols = [
        "ACCESSION_NUMBER",
        "NAMEOFISSUER",
        "TITLEOFCLASS",
        "CUSIP",
        "VALUE",
        "SSHPRNAMT",
        "SSHPRNAMTTYPE",
        "PUTCALL",
    ]

    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as zf:
            with zf.open("INFOTABLE.tsv") as handle:
                reader = pd.read_csv(
                    handle,
                    sep="\t",
                    dtype=str,
                    usecols=usecols,
                    chunksize=chunksize,
                    low_memory=False,
                )
                for chunk in reader:
                    chunk = chunk[chunk["ACCESSION_NUMBER"].isin(accession_to_period)]
                    if chunk.empty:
                        continue
                    chunk["CUSIP"] = chunk["CUSIP"].map(normalize_cusip)
                    chunk = chunk[chunk["CUSIP"] != ""]
                    if chunk.empty:
                        continue

                    putcall = chunk["PUTCALL"].fillna("").astype(str).str.strip()
                    amount_type = chunk["SSHPRNAMTTYPE"].fillna("").astype(str).str.upper().str.strip()
                    chunk = chunk[(putcall == "") & (amount_type.isin(["", "SH"]))]
                    chunk = chunk[stock_title_mask(chunk["TITLEOFCLASS"])]
                    if chunk.empty:
                        continue

                    chunk["period"] = chunk["ACCESSION_NUMBER"].map(accession_to_period)
                    chunk["CIK"] = chunk["ACCESSION_NUMBER"].map(accession_to_cik)
                    values = pd.to_numeric(chunk["VALUE"], errors="coerce").fillna(0)
                    multipliers = chunk["period"].map(value_multiplier_for_period).astype(float)
                    chunk["value_usd"] = values * multipliers
                    chunk["shares"] = pd.to_numeric(chunk["SSHPRNAMT"], errors="coerce").fillna(0)

                    holder_groups.append(
                        chunk.groupby(["period", "CUSIP", "CIK"], as_index=False).agg(
                            value_usd=("value_usd", "sum"),
                            shares=("shares", "sum"),
                        )
                    )
                    meta_groups.append(
                        chunk.groupby("CUSIP", as_index=False).agg(
                            issuer=("NAMEOFISSUER", "first"),
                            title=("TITLEOFCLASS", "first"),
                        )
                    )

    if not holder_groups:
        raise RuntimeError("No matching 13F INFOTABLE holdings found.")

    holdings = pd.concat(holder_groups, ignore_index=True)
    holdings = holdings.groupby(["period", "CUSIP", "CIK"], as_index=False).agg(
        value_usd=("value_usd", "sum"),
        shares=("shares", "sum"),
    )
    holdings["is_large_holder"] = holdings["value_usd"] >= large_holder_min_value_usd
    meta = pd.concat(meta_groups, ignore_index=True).drop_duplicates("CUSIP", keep="first")
    return holdings, meta


def load_default_overrides(universe: set[str]) -> dict[str, str]:
    return {
        cusip: ticker
        for cusip, ticker in DEFAULT_CUSIP_OVERRIDES.items()
        if not universe or ticker in universe
    }


def build_symbol_indexes(
    records: Iterable[SymbolRecord],
) -> tuple[dict[str, list[SymbolRecord]], dict[tuple[str, str], list[SymbolRecord]]]:
    by_base: dict[str, list[SymbolRecord]] = {}
    by_base_class: dict[tuple[str, str], list[SymbolRecord]] = {}
    for record in records:
        if not record.base_key:
            continue
        by_base.setdefault(record.base_key, []).append(record)
        if record.share_class:
            by_base_class.setdefault((record.base_key, record.share_class), []).append(record)
    return by_base, by_base_class


def build_cusip_mapping(
    meta: pd.DataFrame,
    universe: set[str],
    records: list[SymbolRecord],
    overrides: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    by_base, by_base_class = build_symbol_indexes(records)
    mapped_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []

    for _, row in meta.iterrows():
        cusip = normalize_cusip(row.get("CUSIP", ""))
        issuer = str(row.get("issuer", "") or "")
        title = str(row.get("title", "") or "")
        if not cusip:
            continue

        ticker = overrides.get(cusip, "")
        method = "override" if ticker else ""
        reason = ""
        candidates: list[SymbolRecord] = []
        if not ticker:
            base = normalize_issuer_name(issuer)
            share_class = extract_share_class(title, issuer)
            if base and share_class:
                candidates = by_base_class.get((base, share_class), [])
                if len(candidates) == 1:
                    ticker = candidates[0].ticker
                    method = "name_class"
            if not ticker and base:
                candidates = by_base.get(base, [])
                if len(candidates) == 1:
                    ticker = candidates[0].ticker
                    method = "name_unique"
                elif len(candidates) > 1:
                    ticker = choose_ticker_for_ambiguous(candidates, share_class)
                    if ticker:
                        method = "name_ambiguous_class_suffix"
                    else:
                        reason = "ambiguous_name"
            if not ticker and not reason:
                reason = "no_name_match"

        if ticker and (not universe or ticker in universe):
            mapped_rows.append(
                {
                    "cusip": cusip,
                    "ticker": ticker,
                    "issuer": issuer,
                    "title": title,
                    "method": method,
                }
            )
        else:
            unmatched_rows.append(
                {
                    "cusip": cusip,
                    "issuer": issuer,
                    "title": title,
                    "reason": reason or "ticker_not_in_universe",
                    "candidate_tickers": ",".join(record.ticker for record in candidates[:8]),
                }
            )

    return pd.DataFrame(mapped_rows), pd.DataFrame(unmatched_rows)


def aggregate_by_ticker(
    holdings: pd.DataFrame,
    mapping: pd.DataFrame,
    large_holder_min_value_usd: float | None = None,
) -> pd.DataFrame:
    if mapping.empty:
        return pd.DataFrame()
    mapped = holdings.merge(mapping[["cusip", "ticker"]], left_on="CUSIP", right_on="cusip", how="inner")
    if mapped.empty:
        return pd.DataFrame()
    manager_ticker = mapped.groupby(["period", "ticker", "CIK"], as_index=False).agg(
        value_usd=("value_usd", "sum"),
        shares=("shares", "sum"),
    )
    if large_holder_min_value_usd is not None:
        manager_ticker["is_large_holder"] = manager_ticker["value_usd"] >= large_holder_min_value_usd
    else:
        legacy = mapped.groupby(["period", "ticker", "CIK"], as_index=False).agg(
            is_large_holder=("is_large_holder", "max"),
        )
        manager_ticker = manager_ticker.merge(legacy, on=["period", "ticker", "CIK"], how="left")
        manager_ticker["is_large_holder"] = manager_ticker["is_large_holder"].fillna(False)
    return manager_ticker.groupby(["period", "ticker"], as_index=False).agg(
        holder_count=("CIK", "nunique"),
        large_holder_count=("is_large_holder", "sum"),
        total_value_usd=("value_usd", "sum"),
        total_shares=("shares", "sum"),
    )


def build_outputs(
    ticker_agg: pd.DataFrame,
    mapping: pd.DataFrame,
    holdings: pd.DataFrame,
    current_period: str,
    previous_period: str,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if ticker_agg.empty:
        return {"metadata": metadata, "tickers": {}}, []

    current = (
        ticker_agg[ticker_agg["period"] == current_period]
        .drop_duplicates("ticker", keep="last")
        .set_index("ticker")
    )
    previous = (
        ticker_agg[ticker_agg["period"] == previous_period]
        .drop_duplicates("ticker", keep="last")
        .set_index("ticker")
    )

    current_cusips = holdings[holdings["period"] == current_period].merge(
        mapping[["cusip", "ticker"]],
        left_on="CUSIP",
        right_on="cusip",
        how="inner",
    )
    current_cusip_by_ticker: dict[str, str] = {}
    if not current_cusips.empty:
        by_cusip = current_cusips.groupby(["ticker", "CUSIP"], as_index=False)["value_usd"].sum()
        by_cusip = by_cusip.sort_values(["ticker", "value_usd"], ascending=[True, False])
        current_cusip_by_ticker = by_cusip.drop_duplicates("ticker").set_index("ticker")[
            "CUSIP"
        ].to_dict()

    rows: list[dict[str, Any]] = []
    tickers = sorted(set(current.index).union(previous.index))
    for ticker in tickers:
        cur = current.loc[ticker] if ticker in current.index else None
        prev = previous.loc[ticker] if ticker in previous.index else None

        holder_count = as_int(cur["holder_count"]) if cur is not None else 0
        prev_holder_count = as_int(prev["holder_count"]) if prev is not None else None
        large_count = as_int(cur["large_holder_count"]) if cur is not None else 0
        prev_large_count = as_int(prev["large_holder_count"]) if prev is not None else None
        total_value = as_float(cur["total_value_usd"]) if cur is not None else 0.0
        prev_total_value = as_float(prev["total_value_usd"]) if prev is not None else None
        total_shares = as_float(cur["total_shares"]) if cur is not None else 0.0
        prev_total_shares = as_float(prev["total_shares"]) if prev is not None else None

        holder_delta = holder_count - prev_holder_count if prev_holder_count is not None else None
        large_delta = large_count - prev_large_count if prev_large_count is not None else None
        rows.append(
            {
                "ticker": ticker,
                "period": current_period,
                "previous_period": previous_period,
                "holder_count": holder_count,
                "previous_holder_count": prev_holder_count,
                "holder_count_delta": holder_delta,
                "holder_count_delta_pct": pct_delta(holder_count, prev_holder_count),
                "large_holder_count": large_count,
                "previous_large_holder_count": prev_large_count,
                "large_holder_delta": large_delta,
                "large_holder_delta_pct": pct_delta(large_count, prev_large_count),
                "total_value_usd": total_value,
                "previous_total_value_usd": prev_total_value,
                "total_value_delta_pct": pct_delta(total_value, prev_total_value),
                "total_shares": total_shares,
                "previous_total_shares": prev_total_shares,
                "total_shares_delta_pct": pct_delta(total_shares, prev_total_shares),
                "trend": trend_label(large_delta, large_count),
                "cusip": current_cusip_by_ticker.get(ticker, ""),
            }
        )

    tickers_payload = {
        row["ticker"]: {
            key: value
            for key, value in row.items()
            if key != "ticker" and value is not None and not (isinstance(value, float) and pd.isna(value))
        }
        for row in rows
    }
    return {"metadata": metadata, "tickers": tickers_payload}, rows


def enrich_unmatched_cusips(
    unmatched: pd.DataFrame,
    holdings: pd.DataFrame,
    current_period: str,
) -> pd.DataFrame:
    if unmatched.empty:
        return unmatched
    current_agg = holdings[holdings["period"] == current_period].groupby("CUSIP", as_index=False).agg(
        current_holder_count=("CIK", "nunique"),
        current_total_value_usd=("value_usd", "sum"),
    )
    if current_agg.empty:
        return unmatched
    enriched = unmatched.merge(current_agg, left_on="cusip", right_on="CUSIP", how="left").drop(
        columns=["CUSIP"]
    )
    return enriched.sort_values("current_total_value_usd", ascending=False, na_position="last")


def normalize_ticker(raw: object) -> str:
    ticker = str(raw or "").strip().upper()
    ticker = ticker.replace(".", "-").replace("/", "-").replace(" ", "")
    if not ticker or ticker in {"NAN", "NONE", "NULL", "N/A", "USD", "CASH", "-"}:
        return ""
    if not re.fullmatch(r"[A-Z0-9\-]+", ticker):
        return ""
    return ticker


def normalize_cusip(raw: object) -> str:
    cusip = str(raw or "").strip().upper()
    cusip = re.sub(r"[^A-Z0-9]", "", cusip)
    return cusip if len(cusip) == 9 else ""


def extract_share_class(*values: object) -> str:
    text = " ".join(str(value or "") for value in values).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    patterns = (
        r"\bCLASS\s+([A-Z])\b",
        r"\bCL\s+([A-Z])\b",
        r"\bCLA\s+([A-Z])\b",
        r"\bSHS\s+([A-Z])\b",
        r"\bCOM\s+([A-Z])\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def normalize_issuer_name(raw: object) -> str:
    text = str(raw or "").upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"['`’]", "", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    phrases = (
        "COMMON STOCK",
        "COMMON SHARES",
        "ORDINARY SHARES",
        "ORD SHS",
        "ORDINARY SHARE",
        "CLASS A",
        "CLASS B",
        "CLASS C",
        "CL A",
        "CL B",
        "CL C",
        "COM STK",
        "CAP STK",
        "CAPITAL STOCK",
        "NEW COMMON",
        "NEW",
        "SPONSORED ADR",
        "SPONSORED ADS",
        "ADR",
        "ADS",
        "AMERICAN DEPOSITARY",
        "DEPOSITARY SHARES",
        "DEPOSITARY SHARE",
        "SHS BEN INT",
        "BENEFICIAL INTEREST",
    )
    for phrase in phrases:
        text = re.sub(rf"\b{re.escape(phrase)}\b", " ", text)
    suffixes = {
        "COM",
        "INC",
        "INCORPORATED",
        "CORP",
        "CORPORATION",
        "CO",
        "COMPANY",
        "PLC",
        "LTD",
        "LIMITED",
        "NV",
        "N V",
        "SA",
        "S A",
        "AG",
        "SE",
        "LP",
        "L P",
        "LLC",
        "HOLDING",
        "HOLDINGS",
        "GROUP",
        "THE",
        "DEL",
    }
    words = [word for word in text.split() if word not in suffixes]
    return " ".join(words)


def stock_title_mask(title_series: pd.Series) -> pd.Series:
    title = title_series.fillna("").astype(str).str.upper()
    compact = " " + title.str.replace(r"[^A-Z0-9]+", " ", regex=True).str.strip() + " "
    reject_patterns = (
        r"\bCALL\b",
        r"\bPUT\b",
        r"\bNOTE\b",
        r"\bNOTES\b",
        r"\bBOND\b",
        r"\bDEBT\b",
        r"\bDEBENTURE\b",
        r"\bPFD\b",
        r"\bPREFERRED\b",
        r"\bWARRANT\b",
        r"\bWARRANTS\b",
        r"\bWT\b",
        r"\bWTS\b",
        r"\bRIGHT\b",
        r"\bRIGHTS\b",
        r"\bUNIT\b",
        r"\bUNITS\b",
    )
    mask = pd.Series(True, index=title_series.index)
    for pattern in reject_patterns:
        mask &= ~compact.str.contains(pattern, regex=True, na=False)
    return mask


def parse_sec_date(raw: object) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text.upper(), fmt).date()
        except ValueError:
            continue
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def choose_ticker_for_ambiguous(candidates: list[SymbolRecord], share_class: str) -> str:
    if not share_class:
        return ""
    preferred_suffixes = (f"-{share_class}", share_class)
    matches = [
        record.ticker
        for record in candidates
        if any(record.ticker.endswith(suffix) for suffix in preferred_suffixes)
    ]
    deduped = list(dict.fromkeys(matches))
    return deduped[0] if len(deduped) == 1 else ""


def trend_label(delta: int | None, current_count: int) -> str:
    if delta is None:
        return "new" if current_count > 0 else "missing"
    if delta > 0:
        return "positive"
    if delta < 0:
        return "negative"
    return "neutral"


def pct_delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1) * 100


def as_int(value: object) -> int | None:
    if _is_na_scalar(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def as_float(value: object) -> float | None:
    if _is_na_scalar(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_na_scalar(value: object) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(result, bool) and result


def _dataframe_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    clean = df.where(pd.notna(df), None)
    return [dict(row) for row in clean.to_dict(orient="records")]


def _emit(
    callback: ProgressCallback | None,
    progress: int,
    step: str,
    message: str,
    partial: dict[str, Any],
) -> None:
    if callback is not None:
        callback(progress, step, message, partial)
