from __future__ import annotations

import hashlib
import json
import csv
from io import StringIO
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from time import monotonic

from app.domain.stocks import assessment
from app.repositories import jobs, stock_assessments, universes
from app.repositories.stock_assessments import StockAssessmentSnapshotWrite
from app.services.market_calendar import expected_us_market_session
from app.services.stocks import _load_assessment_inputs, _to_ranking_item
from app.schemas import StockScreeningFilters
from app.services.assessment_quality import dependency_quality
from app.workers.tasks.common import raise_if_cancelled


BATCH_SIZE = 40


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported screening input: {type(value).__name__}")


def input_fingerprint(inputs: dict, *, engine_version: str, today: date) -> str:
    # Earnings proximity changes with the calendar even when source data does not.
    encoded = json.dumps([engine_version, today, inputs], default=_json_default, sort_keys=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def screen_universe(*, source_job_id: str = "") -> dict:
    tickers = list(dict.fromkeys(universes.list_universe_tickers(limit=None)))
    if not tickers:
        raise ValueError("Das Aktienuniversum ist leer. Bitte zuerst das Aktienuniversum laden.")
    cached = {row.ticker: row for row in stock_assessments.list_all_snapshots()}
    try:
        revisions = stock_assessments.input_revisions()
    except stock_assessments.StockAssessmentRepositoryUnavailable:
        revisions = {}  # Legacy schema: retain full, safe input comparison.
    started = monotonic()
    today = date.today()
    expected_date = expected_us_market_session().date.isoformat()
    engine_version = hashlib.sha256(
        Path(assessment.__file__).read_bytes()
        + Path(__file__).read_bytes()
        + Path(__file__).with_name("stocks.py").read_bytes()
    ).hexdigest()
    writes = []
    missing = []
    errors = []
    reused = 0
    calculated = 0
    current_job = jobs.get_job(source_job_id) if source_job_id else None
    base_progress = min(90, max(5, current_job.progress)) if current_job else 5

    for offset in range(0, len(tickers), BATCH_SIZE):
        if source_job_id:
            raise_if_cancelled(source_job_id)
            jobs.update_progress(
                source_job_id,
                progress=min(95, base_progress + int((95 - base_progress) * offset / len(tickers))),
                step=f"Aktien bewerten {offset}/{len(tickers)}",
                message=f"{calculated} neu berechnet, {reused} unverändert, {len(missing)} ohne ausreichende Kurse.",
            )
        # Read each dependency once per bounded batch. Database failures abort publication.
        batch = tickers[offset:offset + BATCH_SIZE]
        revision_keys = {
            ticker: input_fingerprint({"revision": revisions[ticker]}, engine_version=engine_version, today=today)
            for ticker in batch if ticker in revisions
        }
        unchanged = {
            ticker for ticker in batch if ticker in cached and ticker in revision_keys
            and cached[ticker].item_json.get("_dependency_revision") == revision_keys[ticker]
        }
        for ticker in unchanged:
            item = dict(cached[ticker].item_json)
            item["prices_stale"] = item["as_of"] < expected_date
            writes.append(StockAssessmentSnapshotWrite(
                ticker=ticker, name=item["name"], as_of=date.fromisoformat(item["as_of"]),
                overall_score=item["overall_score"], technical_score=item["technical_score"], item_json=item,
            ))
            reused += 1
        changed = [ticker for ticker in batch if ticker not in unchanged]
        inputs_batch = _load_assessment_inputs(changed, strict=True) if changed else []
        for ticker, rs_row, inputs in inputs_batch:
            fingerprint = input_fingerprint(inputs, engine_version=engine_version, today=today)
            previous = cached.get(ticker)
            if previous and previous.item_json.get("_input_fingerprint") == fingerprint:
                item = dict(previous.item_json)
                reused += 1
            else:
                try:
                    result = assessment.compute_stock_assessment(ticker, **inputs)
                    calculated += 1
                    if result.source != "database":
                        missing.append(ticker)
                        continue
                    item = _to_ranking_item(result, rs_row.name if rs_row else ticker).model_dump(mode="json")
                    item["checks"] = [asdict(check) for check in result.checks]
                    item["fundamentals_available"] = result.fundamentals_available
                    item["rs_line_available"] = inputs["rs_context"].get("ema21") is not None
                    item["institutional_available"] = bool(inputs["institutional_context"])
                    item["_input_fingerprint"] = fingerprint
                except (ValueError, TypeError, ArithmeticError) as exc:
                    errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"[:200]})
                    continue
            item["prices_stale"] = item["as_of"] < expected_date
            if ticker in revision_keys:
                item["_dependency_revision"] = revision_keys[ticker]
            item["data_quality"] = dependency_quality(inputs["fundamentals_context"], inputs["institutional_context"], inputs["rs_context"])
            item["dependencies_current"] = all(value["status"] == "fresh" for value in item["data_quality"].values())
            writes.append(StockAssessmentSnapshotWrite(
                ticker=ticker, name=item["name"], as_of=date.fromisoformat(item["as_of"]),
                overall_score=item["overall_score"], technical_score=item["technical_score"], item_json=item,
            ))

    if not writes:
        raise ValueError("Keine Aktie bewertbar. Bestehende Bestenliste bleibt erhalten; bitte Kursdaten prüfen.")
    summary = {
        "ok": True, "universe_count": len(tickers), "records_seen": len(tickers),
        "records_written": len(writes), "reused_count": reused, "calculated_count": calculated,
        "missing_count": len(missing), "missing_tickers": missing, "error_count": len(errors),
        "errors": errors[:50], "partial": bool(missing or errors),
        "stale_count": sum(item.item_json["prices_stale"] for item in writes),
        "generated_at": datetime.now(UTC).isoformat(), "duration_seconds": round(monotonic() - started, 2),
        "source_job_id": source_job_id, "as_of": max(item.as_of for item in writes).isoformat(),
    }
    # Compact run statistics accompany every row so publication is one atomic transaction.
    run_summary = {key: value for key, value in summary.items() if key not in {"errors", "missing_tickers"}}
    run_summary["criteria"] = sorted({check["label"] for item in writes for check in item.item_json["checks"]})
    for item in writes:
        item.item_json["_screening"] = run_summary
    if source_job_id:
        raise_if_cancelled(source_job_id)
    stock_assessments.replace_snapshots(writes, source_job_id=source_job_id)
    return summary


def get_screening(filters: StockScreeningFilters, *, export: bool = False) -> dict:
    return stock_assessments.query_screening(filters, expected_date=expected_us_market_session().date, export=export)


def screening_csv(filters: StockScreeningFilters) -> str:
    result = get_screening(filters, export=True)
    labels = result["criteria"]
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Platz", "Ticker", "Name", "Gesamtscore", "Technisch", "Fundamental", "Trend", "Chart", "RS", "Warnungen", "Kursstand", "Kurse veraltet", "Fundamentals vorhanden", "RS-Linie vorhanden", "13F vorhanden", *labels])
    for index, row in enumerate(result["rows"], 1):
        checks = {item["label"]: item for item in row.get("checks", [])}
        values = [index, row["ticker"], row["name"], row["overall_score"], row["technical_score"],
                  row["fundamental_score"] if row.get("fundamentals_available") else "",
                  row["moving_average_score"], row["chart_behavior_score"], row.get("rs_rating"),
                  row["warnings_count"], row["as_of"], row["prices_stale"], row.get("fundamentals_available"),
                  row.get("rs_line_available"), row.get("institutional_available")]
        for label in labels:
            check = checks.get(label)
            values.append(("Erfüllt: " if check["passed"] else "Nicht erfüllt: ") + check["detail"] if check else "Nicht verfügbar")
        writer.writerow([_csv_cell(value) for value in values])
    return output.getvalue()


def _csv_cell(value) -> str:
    text = str(value) if value is not None else ""
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else text
