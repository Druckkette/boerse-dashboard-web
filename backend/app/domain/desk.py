"""Validated private trading workspace and provider-independent calculations."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from collections import defaultdict
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class WatchItem(Input):
    ticker: str = Field(pattern=r"^[A-Z0-9.^=\-]{1,32}$")
    note: str = Field(default="", max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    stage: Literal["discovered", "reviewed", "planned", "purchased", "reviewed_after"] = (
        "discovered"
    )

    @field_validator("tags")
    @classmethod
    def tags_valid(cls, values):
        if any(not v.strip() or len(v) > 40 for v in values):
            raise ValueError("Kennzeichnungen müssen 1 bis 40 Zeichen lang sein.")
        return list(dict.fromkeys(v.strip() for v in values))


class Watchlist(Input):
    name: str = Field(min_length=1, max_length=60)
    items: list[WatchItem] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        if len({i.ticker for i in self.items}) != len(self.items):
            raise ValueError("Jede Aktie darf nur einmal pro Liste enthalten sein.")
        return self


class Plan(Input):
    ticker: str = Field(pattern=r"^[A-Z0-9.^=\-]{1,32}$")
    account_id: str = Field(default="main", max_length=40)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    entry: float = Field(gt=0, le=1e9)
    stop: float = Field(gt=0, le=1e9)
    risk_pct: float = Field(default=1, gt=0, le=5)
    fees: float = Field(default=0, ge=0, le=1e6)
    target: float | None = Field(default=None, gt=0, le=1e9)
    thesis: str = Field(min_length=1, max_length=8000)
    invalidation: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def long_plan(self):
        if self.stop >= self.entry:
            raise ValueError("Für einen Kaufplan muss der Stopp unter dem Einstieg liegen.")
        if self.target is not None and self.target <= self.entry:
            raise ValueError("Das Kursziel muss über dem Einstieg liegen.")
        return self


class WatchTransfer(Input):
    source: str = Field(min_length=1, max_length=40)
    target: str = Field(min_length=1, max_length=40)
    tickers: list[str] = Field(min_length=1, max_length=100)
    move: bool = False


class PlanStage(Input):
    stage: Literal["reviewed", "planned", "purchased", "reviewed_after", "archived"]
    note: str = Field(min_length=1, max_length=4000)


class Alert(Input):
    name: str = Field(min_length=1, max_length=100)
    ticker: str = Field(default="", pattern=r"^[A-Z0-9.^=\-]{0,32}$")
    kind: Literal["price_above", "price_below", "rs_below", "stop", "earnings", "data"]
    threshold: float = Field(default=0, ge=0, le=1e9)
    repeat_minutes: int = Field(default=1440, ge=15, le=43200)
    quiet_start: str = Field(default="22:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    quiet_end: str = Field(default="07:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True
    push: bool = False

    @model_validator(mode="after")
    def target_valid(self):
        if self.kind != "data" and not self.ticker:
            raise ValueError("Für diesen Alarm fehlt die Aktie.")
        if self.kind in {"price_above", "price_below"} and self.threshold <= 0:
            raise ValueError("Die Kursschwelle muss positiv sein.")
        if self.kind == "rs_below" and not 1 <= self.threshold <= 99:
            raise ValueError("RS-Schwelle zwischen 1 und 99 wählen.")
        if self.kind == "earnings" and self.threshold > 35:
            raise ValueError("Earnings-Vorlauf höchstens 35 Kalendertage.")
        return self


class Event(Input):
    title: str = Field(min_length=1, max_length=160)
    date: date
    ticker: str = Field(default="", pattern=r"^[A-Z0-9.^=\-]{0,32}$")
    kind: Literal["company", "dividend", "split", "macro", "review"] = "company"
    note: str = Field(default="", max_length=4000)


class Account(Input):
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    broker: str = Field(default="", max_length=80)


class ImportRequest(Input):
    csv: str = Field(min_length=1, max_length=2_000_000)
    commit: bool = False
    preview_hash: str = Field(default="", max_length=64)


def plan_numbers(
    plan: Plan, *, total: float, cash: float, fx: float, existing_risk: float | None = None
) -> dict:
    """fx converts the security quote currency into account currency."""
    if not all(math.isfinite(v) for v in (total, cash, fx)) or total <= 0 or fx <= 0:
        raise ValueError("Depotwert und beobachteter Wechselkurs müssen positiv sein.")
    budget = total * plan.risk_pct / 100
    # Fees in quote currency count both against available cash and the loss budget.
    risk_shares = max(0, math.floor((budget / fx - plan.fees) / (plan.entry - plan.stop)))
    cash_shares = max(0, math.floor((cash / fx - plan.fees) / plan.entry))
    shares = min(risk_shares, cash_shares)
    risk = ((plan.entry - plan.stop) * shares + plan.fees) * fx if shares else 0
    return dict(
        shares=shares,
        risk_limited_shares=risk_shares,
        cash_limited_shares=cash_shares,
        risk_budget=round(budget, 2),
        planned_risk=round(risk, 2),
        planned_risk_pct=round(risk / total * 100, 4),
        portfolio_risk_pct=None
        if existing_risk is None
        else round((existing_risk + risk) / total * 100, 4),
        cash_required=round((shares * plan.entry + plan.fees) * fx, 2) if shares else 0,
        position_weight_pct=round(shares * plan.entry * fx / total * 100, 4),
        reward_risk=None
        if plan.target is None
        else round((plan.target - plan.entry) / (plan.entry - plan.stop), 2),
        fx_rate=fx,
        limited_by="cash" if cash_shares < risk_shares else "risk",
    )


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    current = now.strftime("%H:%M")
    return (
        False
        if start == end
        else start <= current < end
        if start < end
        else current >= start or current < end
    )


def import_rows(content: str) -> list[dict]:
    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), dialect=dialect)
    required = {"date", "type", "currency"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError("CSV benötigt die Spalten date,type,currency; siehe Importvorlage.")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("CSV enthält doppelte Spaltennamen.")
    rows = []
    allowed = {"buy", "sell", "deposit", "withdrawal", "dividend", "fee", "split"}
    for line, raw in enumerate(reader, 2):
        if line > 5001:
            raise ValueError("Höchstens 5.000 Buchungen je Import.")
        try:
            if None in raw:
                raise ValueError(
                    "Mehr Werte als Spalten; Trennzeichen und Anführungszeichen prüfen."
                )
            kind = (raw.get("type") or "").strip().lower()
            stamp = date.fromisoformat((raw.get("date") or "").strip())
            if kind not in allowed or not date(1970, 1, 1) <= stamp <= date.today():
                raise ValueError("Ungültiger Buchungstyp oder Datum in der Zukunft.")
            currency = (raw.get("currency") or "").strip().upper()
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValueError("Währung muss ein dreistelliger ISO-Code sein.")

            def number(key):
                value = float((raw.get(key) or "0").replace(",", "."))
                if not math.isfinite(value) or value < 0 or value > 1e12:
                    raise ValueError(f"Ungültige Zahl: {key}")
                return value

            ticker = (raw.get("ticker") or "").strip().upper()
            shares, price = number("shares"), number("price")
            if kind in {"buy", "sell", "split"}:
                WatchItem(ticker=ticker)
                if shares <= 0 or (kind != "split" and price <= 0):
                    raise ValueError("Kauf und Verkauf benötigen positive Stückzahl und Preis.")
            fees, tax, amount = number("fees"), number("tax"), number("amount")
            if kind not in {"buy", "sell", "split"} and amount <= 0:
                raise ValueError("Cashbuchungen benötigen einen positiven Betrag.")
            row = dict(
                date=stamp.isoformat(),
                type=kind,
                ticker=ticker,
                currency=currency,
                shares=shares,
                price=price,
                fees=fees,
                tax=tax,
                amount=amount,
            )
            external_id = (raw.get("external_id") or "").strip()
            if len(external_id) > 160:
                raise ValueError("external_id ist zu lang.")
            digest = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
            row.update(id=external_id or digest, fingerprint=digest)
            rows.append(row)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Zeile {line}: {exc}") from exc
    if not rows:
        raise ValueError("Keine Buchungen in der CSV gefunden.")
    return rows


def merge_import(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int]:
    by_id = {r["id"]: r for r in existing}
    duplicates = 0
    for row in incoming:
        if row["id"] in by_id:
            if by_id[row["id"]]["fingerprint"] != row["fingerprint"]:
                raise ValueError("Eine Buchungs-ID wird mit anderem Inhalt wiederverwendet.")
            duplicates += 1
        else:
            by_id[row["id"]] = row
    merged = sorted(by_id.values(), key=lambda row: row["date"])
    if len(merged) > 20000:
        raise ValueError("Höchstens 20.000 Buchungen je zusätzlichem Depot.")
    holdings = defaultdict(float)
    for row in merged:
        if row["type"] == "buy":
            holdings[row["ticker"]] += row["shares"]
        elif row["type"] == "sell":
            holdings[row["ticker"]] -= row["shares"]
            if holdings[row["ticker"]] < -1e-7:
                raise ValueError(
                    f"Verkauf ohne ausreichenden Bestand: {row['ticker']} am {row['date']}"
                )
        elif row["type"] == "split":
            if holdings[row["ticker"]] <= 0:
                raise ValueError("Ein Split benötigt einen bestehenden Bestand.")
            holdings[row["ticker"]] = row["shares"]
    return merged, duplicates


def money_weighted_return(flows: list[tuple[date, float]]) -> float | None:
    """Annual XIRR; ambiguous/missing roots stay unavailable rather than guessed."""
    net = defaultdict(float)
    for stamp, value in flows:
        if not math.isfinite(value):
            return None
        net[stamp] += value
    if len(net) < 2 or not any(v < 0 for v in net.values()) or not any(v > 0 for v in net.values()):
        return None
    start = min(net)
    terms = [((d - start).days / 365, value) for d, value in net.items()]

    def npv(log_rate):
        powers = [-log_rate * years for years, _ in terms]
        scale = max(powers)
        return sum(value * math.exp(power - scale) for power, (_, value) in zip(powers, terms))

    # Solving in log(1+r) avoids undefined discounting below -100%.
    roots = []
    steps = [-9.21 + i * (23.03 / 400) for i in range(401)]
    for left, right in zip(steps, steps[1:]):
        a, b = npv(left), npv(right)
        if a == 0:
            roots.append(left)
        elif a * b < 0:
            for _ in range(70):
                middle = (left + right) / 2
                if npv(left) * npv(middle) <= 0:
                    right = middle
                else:
                    left = middle
            roots.append((left + right) / 2)
    unique = []
    for root in roots:
        if not any(abs(root - previous) < 1e-6 for previous in unique):
            unique.append(root)
    return (math.exp(unique[0]) - 1) * 100 if len(unique) == 1 else None


def curve_statistics(points: list[dict], *, historical: bool) -> dict:
    valid = [p for p in points if p.get("portfolio_index") is not None]
    complete = bool(points) and len(valid) == len(points)
    peak, worst = 0.0, 0.0
    for point in valid:
        value = point["portfolio_index"]
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value / peak - 1) * 100)
    available = historical and complete and valid[0]["portfolio_index"] > 0
    return dict(
        twr_pct=(valid[-1]["portfolio_index"] / valid[0]["portfolio_index"] - 1) * 100
        if available
        else None,
        max_drawdown_pct=worst if available else None,
        covered_points=len(valid),
        total_points=len(points),
        complete=complete,
        note="Zeitgewichtete Rendite mit Cashflows am Tagesende."
        if available
        else "Vollständige historische Bewertungen erforderlich; Simulationen und Lücken sind keine belegte Depotperformance.",
    )
