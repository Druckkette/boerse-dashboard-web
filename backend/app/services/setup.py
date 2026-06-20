from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from app.repositories import jobs as job_repository
from app.schemas import (
    DataDiagnosticIssue,
    DataDiagnosticsResponse,
    FreshnessResponse,
    Job,
    JobType,
    ServiceFreshness,
    SetupStatusResponse,
    SetupStep,
    SystemReadinessResponse,
)
from app.services.freshness import get_freshness
from app.services.settings import get_data_diagnostics
from app.services.system import get_system_readiness


ACTIVE_STATUSES = {"queued", "running"}
SetupStepKey = Literal[
    "system",
    "portfolio",
    "prices",
    "market_breadth",
    "relative_strength",
    "institutional_13f",
    "atr_monitor",
]
SetupStepStatus = Literal["complete", "pending", "running", "warning", "blocked", "error"]
SetupOverallStatus = Literal["ready", "needs_action", "running", "blocked"]


def get_setup_status() -> SetupStatusResponse:
    readiness = get_system_readiness()
    diagnostics = get_data_diagnostics()
    freshness = get_freshness()
    jobs = job_repository.list_jobs(limit=100)
    steps = _build_steps(readiness=readiness, diagnostics=diagnostics, freshness=freshness, jobs=jobs)
    status = _overall_status(steps)
    next_step = _next_action_step(steps)

    return SetupStatusResponse(
        as_of=datetime.now(UTC),
        status=status,
        summary=_summary(status, steps),
        next_step_key=next_step.key if next_step else "",
        steps=steps,
    )


def _build_steps(
    *,
    readiness: SystemReadinessResponse,
    diagnostics: DataDiagnosticsResponse,
    freshness: FreshnessResponse,
    jobs: list[Job],
) -> list[SetupStep]:
    freshness_by_name = {item.name: item for item in freshness.services}
    return [
        _system_step(readiness),
        _portfolio_step(diagnostics),
        _prices_step(diagnostics, freshness_by_name.get("prices"), jobs),
        _breadth_step(freshness_by_name.get("market_breadth"), freshness_by_name.get("prices"), jobs),
        _relative_strength_step(freshness_by_name.get("relative_strength"), freshness_by_name.get("prices"), jobs),
        _institutional_13f_step(freshness_by_name.get("institutional_13f"), jobs),
        _atr_monitor_step(diagnostics, freshness_by_name.get("sell_ranking"), freshness_by_name.get("prices"), jobs),
    ]


def _system_step(readiness: SystemReadinessResponse) -> SetupStep:
    if readiness.status == "ready":
        return SetupStep(
            key="system",
            label="System",
            status="complete",
            detail="Postgres, Migrationen und Redis sind bereit.",
            href="/settings",
            action_label="Systemstatus",
        )
    if readiness.status == "degraded":
        return SetupStep(
            key="system",
            label="System",
            status="warning",
            detail="Die API ist erreichbar, aber mindestens ein optionaler oder prüfbarer Dienst meldet Warnungen.",
            href="/settings",
            action_label="Details prüfen",
        )
    return SetupStep(
        key="system",
        label="System",
        status="error",
        detail="Mindestens ein erforderlicher Systemcheck ist fehlgeschlagen.",
        href="/settings",
        action_label="Details prüfen",
    )


def _portfolio_step(diagnostics: DataDiagnosticsResponse) -> SetupStep:
    if diagnostics.open_positions_count > 0:
        return SetupStep(
            key="portfolio",
            label="Depot",
            status="complete",
            detail=f"{diagnostics.open_positions_count} offene Positionen sind gespeichert.",
            href="/portfolio",
            action_label="Depot öffnen",
        )
    return SetupStep(
        key="portfolio",
        label="Depot",
        status="pending",
        detail="Noch keine offenen Positionen gespeichert.",
        href="/portfolio/imports",
        action_label="Depot importieren",
    )


def _prices_step(
    diagnostics: DataDiagnosticsResponse,
    freshness: ServiceFreshness | None,
    jobs: list[Job],
) -> SetupStep:
    latest_job = _latest_job(jobs, "bootstrap_market_data") or _latest_job(jobs, "refresh_prices")
    if _is_active(latest_job):
        return _job_step(
            key="prices",
            label="Kursdaten",
            status="running",
            detail="Price-Cache-Refresh läuft im Worker.",
            job_type="bootstrap_market_data",
            job_payload={},
            latest_job=latest_job,
        )

    missing_issue = _issue(diagnostics, "missing_price_cache")
    stale_issue = _issue(diagnostics, "stale_price_cache")
    if missing_issue:
        return _job_step(
            key="prices",
            label="Kursdaten",
            status="pending",
            detail=missing_issue.detail,
            job_type="bootstrap_market_data",
            job_payload=missing_issue.job_payload,
            latest_job=latest_job,
            action_label=missing_issue.action_label or "Kurse laden",
        )
    if stale_issue:
        return _job_step(
            key="prices",
            label="Kursdaten",
            status="warning",
            detail=stale_issue.detail,
            job_type="bootstrap_market_data",
            job_payload=stale_issue.job_payload,
            latest_job=latest_job,
            action_label=stale_issue.action_label or "Kurse aktualisieren",
        )
    if freshness is None or freshness.status == "missing":
        return _job_step(
            key="prices",
            label="Kursdaten",
            status="pending",
            detail="Noch kein Price-Cache vorhanden.",
            job_type="bootstrap_market_data",
            job_payload={"mode": "initial", "source": "setup", "range": "2y", "universe": "us_common_stocks", "limit_universe": 5000},
            latest_job=latest_job,
            action_label="Kurse laden",
        )
    if freshness.status == "stale":
        return _job_step(
            key="prices",
            label="Kursdaten",
            status="warning",
            detail=f"Price-Cache ist vorhanden, aber veraltet ({freshness.as_of}).",
            job_type="refresh_prices",
            job_payload={"mode": "update", "source": "setup", "range": "6m", "universe": "us_common_stocks", "limit_universe": 5000},
            latest_job=latest_job,
            action_label="Kurse aktualisieren",
        )
    return _job_step(
        key="prices",
        label="Kursdaten",
        status="complete",
        detail=f"Price-Cache ist aktuell ({freshness.as_of}).",
        job_type="bootstrap_market_data",
        job_payload={"mode": "update", "source": "setup", "range": "6m", "universe": "us_common_stocks", "limit_universe": 5000},
        latest_job=latest_job,
        action_label="Kurse aktualisieren",
    )


def _breadth_step(
    freshness: ServiceFreshness | None,
    price_freshness: ServiceFreshness | None,
    jobs: list[Job],
) -> SetupStep:
    latest_job = _latest_job(jobs, "refresh_breadth")
    if _is_active(latest_job):
        return _job_step(
            key="market_breadth",
            label="Marktbreite",
            status="running",
            detail="Breadth-Refresh läuft im Worker.",
            job_type="refresh_breadth",
            job_payload={},
            latest_job=latest_job,
        )
    if price_freshness is None or price_freshness.status == "missing":
        return _blocked_job_step(
            key="market_breadth",
            label="Marktbreite",
            detail="Breadth benötigt zuerst gecachte Kursdaten.",
            job_type="refresh_breadth",
            latest_job=latest_job,
        )
    payload = {"mode": "manual", "lookback_days": 550, "universe": "us_common_stocks", "limit_universe": 5000}
    if freshness is None or freshness.status == "missing":
        return _job_step(
            key="market_breadth",
            label="Marktbreite",
            status="pending",
            detail="Noch keine vorberechnete Marktbreite vorhanden.",
            job_type="refresh_breadth",
            job_payload=payload,
            latest_job=latest_job,
            action_label="Breadth berechnen",
        )
    if freshness.status == "stale":
        return _job_step(
            key="market_breadth",
            label="Marktbreite",
            status="warning",
            detail=f"Marktbreite ist vorhanden, aber veraltet ({freshness.as_of}).",
            job_type="refresh_breadth",
            job_payload=payload,
            latest_job=latest_job,
            action_label="Breadth aktualisieren",
        )
    return _job_step(
        key="market_breadth",
        label="Marktbreite",
        status="complete",
        detail=f"Market-Snapshot und Breadth-Daten sind aktuell ({freshness.as_of}).",
        job_type="refresh_breadth",
        job_payload=payload,
        latest_job=latest_job,
        action_label="Breadth aktualisieren",
    )


def _relative_strength_step(
    freshness: ServiceFreshness | None,
    price_freshness: ServiceFreshness | None,
    jobs: list[Job],
) -> SetupStep:
    latest_job = _latest_job(jobs, "refresh_relative_strength")
    if _is_active(latest_job):
        return _job_step(
            key="relative_strength",
            label="Relative Stärke",
            status="running",
            detail="RS-Refresh läuft im Worker.",
            job_type="refresh_relative_strength",
            job_payload={},
            latest_job=latest_job,
        )
    if price_freshness is None or price_freshness.status == "missing":
        return _blocked_job_step(
            key="relative_strength",
            label="Relative Stärke",
            detail="RS-Ratings benötigen zuerst gecachte Kursdaten.",
            job_type="refresh_relative_strength",
            latest_job=latest_job,
        )
    payload = {
        "mode": "manual",
        "lookback_days": 430,
        "benchmark_ticker": "SPY",
        "universe": "us_common_stocks",
        "limit_universe": 5000,
    }
    if freshness is None or freshness.status == "missing":
        return _job_step(
            key="relative_strength",
            label="Relative Stärke",
            status="pending",
            detail="Noch keine RS-Ratings berechnet.",
            job_type="refresh_relative_strength",
            job_payload=payload,
            latest_job=latest_job,
            action_label="RS berechnen",
        )
    if freshness.status == "stale":
        return _job_step(
            key="relative_strength",
            label="Relative Stärke",
            status="warning",
            detail=f"RS-Ratings sind vorhanden, aber veraltet ({freshness.as_of}).",
            job_type="refresh_relative_strength",
            job_payload=payload,
            latest_job=latest_job,
            action_label="RS aktualisieren",
        )
    return _job_step(
        key="relative_strength",
        label="Relative Stärke",
        status="complete",
        detail=f"RS-Ratings sind aktuell ({freshness.as_of}).",
        job_type="refresh_relative_strength",
        job_payload=payload,
        latest_job=latest_job,
        action_label="RS aktualisieren",
    )


def _institutional_13f_step(
    freshness: ServiceFreshness | None,
    jobs: list[Job],
) -> SetupStep:
    latest_job = _latest_job(jobs, "refresh_sec13f")
    payload = {
        "mode": "incremental",
        "source": "setup",
        "universe": "open_positions",
        "limit_universe": 500,
        "dataset_count": 2,
    }
    if _is_active(latest_job):
        return _job_step(
            key="institutional_13f",
            label="13F/SEC",
            status="running",
            detail="13F/SEC-Refresh läuft im Worker.",
            job_type="refresh_sec13f",
            job_payload=payload,
            latest_job=latest_job,
        )
    if freshness is None or freshness.status == "missing":
        return _job_step(
            key="institutional_13f",
            label="13F/SEC",
            status="pending",
            detail="Noch keine institutionellen 13F-Trends gespeichert. SEC_USER_AGENT muss im Setup/Security-Bereich gesetzt sein.",
            job_type="refresh_sec13f",
            job_payload=payload,
            latest_job=latest_job,
            action_label="13F laden",
        )
    if freshness.status == "stale":
        return _job_step(
            key="institutional_13f",
            label="13F/SEC",
            status="warning",
            detail=f"13F-Trends sind vorhanden, aber veraltet ({freshness.as_of}).",
            job_type="refresh_sec13f",
            job_payload=payload,
            latest_job=latest_job,
            action_label="13F aktualisieren",
        )
    return _job_step(
        key="institutional_13f",
        label="13F/SEC",
        status="complete",
        detail=f"13F-Trends sind aktuell bis Report-Periode {freshness.as_of}.",
        job_type="refresh_sec13f",
        job_payload=payload,
        latest_job=latest_job,
        action_label="13F aktualisieren",
    )


def _atr_monitor_step(
    diagnostics: DataDiagnosticsResponse,
    freshness: ServiceFreshness | None,
    price_freshness: ServiceFreshness | None,
    jobs: list[Job],
) -> SetupStep:
    latest_job = _latest_job(jobs, "position_atr_monitor")
    if _is_active(latest_job):
        return _job_step(
            key="atr_monitor",
            label="ATR-Monitor",
            status="running",
            detail="Positionsmonitor läuft im Worker.",
            job_type="position_atr_monitor",
            job_payload={},
            latest_job=latest_job,
        )
    if diagnostics.open_positions_count == 0:
        return _blocked_job_step(
            key="atr_monitor",
            label="ATR-Monitor",
            detail="Der Positionsmonitor benötigt importierte offene Positionen.",
            job_type="position_atr_monitor",
            latest_job=latest_job,
        )
    if diagnostics.missing_price_count > 0 or price_freshness is None or price_freshness.status == "missing":
        return _blocked_job_step(
            key="atr_monitor",
            label="ATR-Monitor",
            detail="Der Positionsmonitor benötigt Kursdaten für die offenen Positionen.",
            job_type="position_atr_monitor",
            latest_job=latest_job,
        )
    payload = {"mode": "manual"}
    if freshness is None or freshness.status == "missing":
        return _job_step(
            key="atr_monitor",
            label="ATR-Monitor",
            status="pending",
            detail="Offene Positionen wurden noch nicht gegen die Sell-Engine geprüft.",
            job_type="position_atr_monitor",
            job_payload=payload,
            latest_job=latest_job,
            action_label="Monitor starten",
        )
    if freshness.status == "stale":
        return _job_step(
            key="atr_monitor",
            label="ATR-Monitor",
            status="warning",
            detail=f"Letzter Monitorlauf ist veraltet ({freshness.as_of}).",
            job_type="position_atr_monitor",
            job_payload=payload,
            latest_job=latest_job,
            action_label="Monitor aktualisieren",
        )
    return _job_step(
        key="atr_monitor",
        label="ATR-Monitor",
        status="complete",
        detail=f"Sell-Ranking und ATR-Monitor sind aktuell ({freshness.as_of}).",
        job_type="position_atr_monitor",
        job_payload=payload,
        latest_job=latest_job,
        action_label="Monitor aktualisieren",
    )


def _job_step(
    *,
    key: SetupStepKey,
    label: str,
    status: SetupStepStatus,
    detail: str,
    job_type: JobType,
    job_payload: dict,
    latest_job: Job | None,
    action_label: str = "",
) -> SetupStep:
    return SetupStep(
        key=key,
        label=label,
        status=status,
        detail=detail,
        action_label=action_label,
        job_type=job_type,
        job_payload=job_payload,
        latest_job=latest_job,
    )


def _blocked_job_step(
    *,
    key: SetupStepKey,
    label: str,
    detail: str,
    job_type: JobType,
    latest_job: Job | None,
) -> SetupStep:
    return SetupStep(
        key=key,
        label=label,
        status="blocked",
        detail=detail,
        job_type=job_type,
        job_payload={},
        latest_job=latest_job,
    )


def _latest_job(jobs: list[Job], job_type: str) -> Job | None:
    return next((job for job in jobs if job.job_type == job_type), None)


def _is_active(job: Job | None) -> bool:
    return bool(job and job.status in ACTIVE_STATUSES)


def _issue(diagnostics: DataDiagnosticsResponse, key: str) -> DataDiagnosticIssue | None:
    return next((issue for issue in diagnostics.issues if issue.key == key), None)


def _overall_status(steps: list[SetupStep]) -> SetupOverallStatus:
    if any(step.status == "error" for step in steps):
        return "blocked"
    if any(step.status == "running" for step in steps):
        return "running"
    if any(step.status in {"pending", "blocked", "warning"} for step in steps):
        return "needs_action"
    return "ready"


def _next_action_step(steps: list[SetupStep]) -> SetupStep | None:
    for step in steps:
        if step.status in {"error", "pending", "warning"} and (step.href or step.job_type):
            return step
    return None


def _summary(status: str, steps: list[SetupStep]) -> str:
    if status == "ready":
        return "Erststart abgeschlossen. Depot, Marktdaten, RS-Ratings, 13F-Daten und Positionsmonitor sind vorbereitet."
    if status == "running":
        running = next((step for step in steps if step.status == "running"), None)
        return f"{running.label if running else 'Ein Job'} läuft im Worker. Die Oberfläche bleibt bedienbar."
    if status == "blocked":
        return "Ein erforderlicher Systemcheck blockiert den Erststart."
    next_step = _next_action_step(steps)
    return f"Nächster Schritt: {next_step.label}." if next_step else "Es gibt noch abhängige Setup-Schritte."
