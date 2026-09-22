"""Finish checked non-periodic filings with sufficient cached history.

Revision ID: 0018_nonperiod_filing_checks
Revises: 0017_report_source_gaps
"""

from datetime import date

from alembic import op
import sqlalchemy as sa


revision = "0018_nonperiod_filing_checks"
down_revision = "0017_report_source_gaps"
branch_labels = None
depends_on = None


_HISTORY_KEYS = (
    "eps_quarter_history",
    "annual_eps_history",
    "revenue_quarter_history",
    "annual_revenue_history",
)
_FALLBACK_KEYS = (
    "eps_growth",
    "annual_eps_growth",
    "revenue_growth",
    "annual_revenue_growth",
)
_CURRENT_FIELDS = (
    "eps_current_quarter", "eps_current_year", "revenue_current_quarter",
    "revenue_current_year", "current",
)
_PREVIOUS_FIELDS = (
    "eps_same_quarter_last_year", "eps_previous_year", "revenue_same_quarter_last_year",
    "revenue_previous_year", "previous", "prior",
)
_GROWTH_FIELDS = ("eps_growth_yoy_pct", "revenue_growth_yoy_pct", "growth_pct")


def _first_present(item: dict, keys: tuple[str, ...]):
    return next((item[key] for key in keys if item.get(key) is not None), None)


def _has_required_history(metadata: dict) -> bool:
    enrichment = metadata.get("enrichment") or {}
    if not isinstance(enrichment, dict):
        enrichment = {}
    for key, fallback in zip(_HISTORY_KEYS, _FALLBACK_KEYS, strict=True):
        candidates = (metadata.get(key), enrichment.get(key), metadata.get(fallback), enrichment.get(fallback))
        history = next((value for value in candidates if isinstance(value, list) and value), [])
        usable = 0
        for item in history[:3]:
            if not isinstance(item, dict):
                continue
            current = _first_present(item, _CURRENT_FIELDS)
            previous = _first_present(item, _PREVIOUS_FIELDS)
            growth = _first_present(item, _GROWTH_FIELDS)
            if growth is not None or (current is not None and previous is not None):
                usable += 1
        if usable < 3:
            return False
    return True


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT w.key, w.checked_at, w.payload_json, f.id AS snapshot_id, f.metadata_json
        FROM refresh_work_items w
        LEFT JOIN LATERAL (
            SELECT id, metadata_json FROM fundamental_snapshots f
            WHERE f.ticker = w.ticker ORDER BY as_of DESC LIMIT 1
        ) f ON true
        WHERE w.data_group = 'statements' AND w.status = 'waiting_source'
          AND w.payload_json->>'form' IN (
              '8-K', '8-K/A', '6-K', '6-K/A', '10-Q/A', '10-K/A', '20-F/A', '40-F/A'
          )
          AND coalesce(w.payload_json->>'expected_period', '') = ''
          AND w.checked_at IS NOT NULL
          AND w.result_json->>'reason' = 'Erwartete Periode oder Historie fehlt noch.'
    """)).mappings().all()
    for row in rows:
        filed = row["payload_json"].get("event_date")
        try:
            filed_date = date.fromisoformat(filed)
        except (TypeError, ValueError):
            continue
        if row["checked_at"].date() < filed_date or not _has_required_history(row["metadata_json"] or {}):
            continue
        updated = connection.execute(sa.text("""
            UPDATE refresh_work_items
            SET status = 'current', due_at = now() + interval '14 days',
                result_json = jsonb_set(
                    jsonb_set(result_json, '{complete}', 'true'::jsonb, true),
                    '{reason}', to_jsonb('Nicht-periodische SEC-Meldung geprüft; Historie vollständig.'::text), true
                )
            WHERE key = :key AND status = 'waiting_source'
        """), {"key": row["key"]})
        if updated.rowcount and row["snapshot_id"] is not None:
            connection.execute(sa.text("""
                UPDATE fundamental_snapshots
                SET metadata_json = jsonb_set(
                    jsonb_set(metadata_json, '{report_refresh,complete}', 'true'::jsonb, true),
                    '{report_refresh,status}', to_jsonb('current'::text), true
                )
                WHERE id = :snapshot_id
            """), {"snapshot_id": row["snapshot_id"]})


def downgrade() -> None:
    # A checked filing should not be made pending again without a new event.
    pass
