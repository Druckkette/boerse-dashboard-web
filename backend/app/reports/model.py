from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ReportSection:
    title: str
    data: dict[str, Any]


@dataclass(frozen=True)
class InvestmentReport:
    ticker: str
    name: str
    exported_at: datetime
    currency: str = ""
    isin: str = ""
    trade_id: str | None = None
    assessment: dict[str, Any] = field(default_factory=dict)
    prices: dict[str, Any] = field(default_factory=dict)
    sections: list[ReportSection] = field(default_factory=list)
    journal: list[dict[str, Any]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
