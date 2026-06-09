from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO

from app.repositories import portfolio as portfolio_repository
from app.repositories.portfolio import PortfolioRepositoryUnavailable
from app.schemas import (
    KpiCard,
    PortfolioImportRequest,
    PortfolioImportResponse,
    PortfolioImportRow,
    PortfolioPosition,
    PortfolioSnapshotResponse,
)
from app.services.dummy_data import get_portfolio_positions as get_dummy_portfolio_positions
from app.services.dummy_data import get_portfolio_snapshot as get_dummy_portfolio_snapshot


REQUIRED_IMPORT_FIELDS = {"ticker", "shares", "entry_price"}

HEADER_ALIASES = {
    "ticker": {"ticker", "symbol", "wertpapier", "isin_ticker"},
    "name": {"name", "bezeichnung", "instrument", "security", "wertpapiername"},
    "shares": {"shares", "quantity", "qty", "stueck", "stück", "anzahl", "menge"},
    "entry_price": {"entry_price", "buy_price", "avg_price", "average_price", "kaufkurs", "einstand", "einstandskurs"},
    "current_price": {"current_price", "last_price", "kurs", "aktueller_kurs", "market_price"},
    "currency": {"currency", "waehrung", "währung"},
    "buy_date": {"buy_date", "date", "kaufdatum", "opened_at"},
    "broker": {"broker", "bank", "depotbank"},
    "account": {"account", "depot", "portfolio"},
    "note": {"note", "notiz", "comment", "kommentar"},
}


def get_portfolio_positions() -> list[PortfolioPosition]:
    try:
        rows = portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        rows = []
    if not rows:
        return get_dummy_portfolio_positions()

    invested = sum(row.current_price * row.shares for row in rows)
    positions: list[PortfolioPosition] = []
    for row in rows:
        market_value = row.current_price * row.shares
        pnl_pct = (row.current_price / row.entry_price - 1) * 100 if row.entry_price else 0
        positions.append(
            PortfolioPosition(
                ticker=row.ticker,
                name=row.name,
                shares=row.shares,
                entry_price=row.entry_price,
                current_price=row.current_price,
                market_value=market_value,
                pnl_pct=pnl_pct,
                weight_pct=market_value / invested * 100 if invested else 0,
                atr_pct=0,
                beta=1,
                status=_status_for_pnl(pnl_pct),
            )
        )
    return positions


def get_portfolio_snapshot() -> PortfolioSnapshotResponse:
    try:
        rows = portfolio_repository.list_open_positions()
    except PortfolioRepositoryUnavailable:
        rows = []
    if not rows:
        return get_dummy_portfolio_snapshot()

    positions = get_portfolio_positions()
    invested = sum(position.market_value for position in positions)
    cash = 0.0
    total = invested + cash
    return PortfolioSnapshotResponse(
        as_of=datetime.now(UTC).isoformat(),
        total_value=total,
        invested_value=invested,
        cash_balance=cash,
        cash_ratio_pct=0,
        portfolio_atr_pct=0,
        beta_balancer=1,
        max_depot_loss_pct=sum(position.weight_pct * 0.08 for position in positions) / 100,
        kpis=[
            KpiCard(label="Depotwert", value=f"{total:,.0f} EUR", detail="aus Import", tone="neutral"),
            KpiCard(label="Positionen", value=str(len(positions)), detail="offen", tone="good"),
            KpiCard(label="Gewinner", value=str(sum(1 for row in positions if row.pnl_pct >= 0)), detail="P&L >= 0", tone="good"),
            KpiCard(label="Risiko", value="Basis", detail="ATR folgt mit Price Cache", tone="neutral"),
        ],
        positions=positions,
    )


def import_portfolio_positions(payload: PortfolioImportRequest) -> PortfolioImportResponse:
    parse_result = parse_positions_csv(payload.content)
    if parse_result.errors or payload.dry_run:
        return PortfolioImportResponse(
            ok=not parse_result.errors,
            dry_run=payload.dry_run,
            rows_total=parse_result.rows_total,
            rows_imported=0,
            positions=parse_result.positions,
            errors=parse_result.errors,
            warnings=parse_result.warnings,
        )

    result = portfolio_repository.upsert_imported_positions(
        parse_result.positions,
        source=payload.source,
        file_name=payload.file_name,
        replace_open_positions=payload.replace_open_positions,
    )
    return PortfolioImportResponse(
        ok=True,
        dry_run=False,
        import_id=result.import_id,
        rows_total=parse_result.rows_total,
        rows_imported=result.rows_imported,
        positions=parse_result.positions,
        warnings=parse_result.warnings,
    )


class PortfolioCsvParseResult:
    def __init__(
        self,
        *,
        positions: list[PortfolioImportRow],
        rows_total: int,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.positions = positions
        self.rows_total = rows_total
        self.errors = errors or []
        self.warnings = warnings or []


def parse_positions_csv(content: str) -> PortfolioCsvParseResult:
    clean_content = content.strip("\ufeff \n\r\t")
    if not clean_content:
        return PortfolioCsvParseResult(positions=[], rows_total=0, errors=["CSV-Inhalt ist leer."])

    dialect = _sniff_dialect(clean_content)
    reader = csv.DictReader(StringIO(clean_content), dialect=dialect)
    if not reader.fieldnames:
        return PortfolioCsvParseResult(positions=[], rows_total=0, errors=["CSV-Header fehlt."])

    normalized_headers = {header: _canonical_header(header) for header in reader.fieldnames}
    present = {canonical for canonical in normalized_headers.values() if canonical}
    missing = sorted(REQUIRED_IMPORT_FIELDS - present)
    if missing:
        return PortfolioCsvParseResult(
            positions=[],
            rows_total=0,
            errors=[f"Pflichtspalten fehlen: {', '.join(missing)}."],
            warnings=[f"Erkannte Spalten: {', '.join(reader.fieldnames)}"],
        )

    positions: list[PortfolioImportRow] = []
    errors: list[str] = []
    warnings: list[str] = []
    rows_total = 0
    for line_number, raw_row in enumerate(reader, start=2):
        rows_total += 1
        row = {
            canonical: (raw_row.get(header) or "").strip()
            for header, canonical in normalized_headers.items()
            if canonical
        }
        if not any(row.values()):
            continue

        ticker = row.get("ticker", "").upper().replace(" ", "")
        shares = _parse_number(row.get("shares", ""))
        entry_price = _parse_number(row.get("entry_price", ""))
        if not ticker:
            errors.append(f"Zeile {line_number}: ticker fehlt.")
            continue
        if shares is None or shares <= 0:
            errors.append(f"Zeile {line_number}: shares ist ungültig.")
            continue
        if entry_price is None or entry_price <= 0:
            errors.append(f"Zeile {line_number}: entry_price ist ungültig.")
            continue

        current_price = _parse_number(row.get("current_price", ""))
        row_warnings: list[str] = []
        if current_price is None:
            row_warnings.append("Kein aktueller Kurs in CSV; Price Cache oder Einstandskurs wird genutzt.")
        positions.append(
            PortfolioImportRow(
                ticker=ticker,
                name=row.get("name", "") or ticker,
                shares=shares,
                entry_price=entry_price,
                current_price=current_price,
                currency=(row.get("currency", "") or "EUR").upper(),
                buy_date=row.get("buy_date") or None,
                broker=row.get("broker", ""),
                account=row.get("account", ""),
                note=row.get("note", ""),
                warnings=row_warnings,
            )
        )

    if not positions and not errors:
        errors.append("Keine importierbaren Positionen gefunden.")
    duplicate_tickers = sorted({row.ticker for row in positions if sum(1 for item in positions if item.ticker == row.ticker) > 1})
    if duplicate_tickers:
        warnings.append(f"Doppelte Ticker in CSV: {', '.join(duplicate_tickers)}. Der letzte Import überschreibt später denselben offenen Ticker.")
    return PortfolioCsvParseResult(positions=positions, rows_total=rows_total, errors=errors, warnings=warnings)


def _status_for_pnl(pnl_pct: float) -> str:
    if pnl_pct <= -8:
        return "sell"
    if pnl_pct <= -4:
        return "risk"
    if pnl_pct >= 25:
        return "watch"
    return "ok"


def _sniff_dialect(content: str) -> csv.Dialect:
    sample = content[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def _canonical_header(header: str) -> str | None:
    clean = header.strip().lower().replace(" ", "_").replace("-", "_")
    for canonical, aliases in HEADER_ALIASES.items():
        if clean in aliases:
            return canonical
    return None


def _parse_number(value: str) -> float | None:
    clean = value.strip()
    if not clean:
        return None
    clean = clean.replace("\u00a0", "").replace(" ", "")
    if "," in clean and "." in clean:
        if clean.rfind(",") > clean.rfind("."):
            clean = clean.replace(".", "").replace(",", ".")
        else:
            clean = clean.replace(",", "")
    else:
        clean = clean.replace(",", ".")
    try:
        return float(clean)
    except ValueError:
        return None
