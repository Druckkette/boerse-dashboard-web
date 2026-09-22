"""Classify historical missing-source rows as waiting, not worker failures.

Revision ID: 0017_report_source_gaps
Revises: 0016_trade_journal_import_links
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_report_source_gaps"
down_revision = "0016_trade_journal_import_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE refresh_work_items
        SET status = 'waiting_source',
            result_json = jsonb_build_object('complete', false, 'reason', error),
            error = '',
            due_at = GREATEST(
                due_at,
                now() + CASE WHEN priority <= 40 THEN interval '2 hours' ELSE interval '1 day' END
            )
        WHERE status = 'error'
          AND (
              (data_group = 'beta' AND error = 'RuntimeError: Provider liefert kein Beta; bestehende Daten bleiben erhalten.')
              OR (data_group = 'statements' AND error = 'RuntimeError: Keine verwertbaren Statements; bestehende Historie bleibt erhalten.')
              OR (data_group = 'assessment' AND error IN (
                  'ValueError: Keine Aktie bewertbar. Bestehende Bestenliste bleibt erhalten; bitte Kursdaten prüfen.',
                  'Keine bewertbaren Kursdaten.'
              ))
          )
    """))
    # Apply the same baseline backoff to already checked universe rows. A new
    # filing changes the revision and immediately requeues the affected ticker.
    op.execute(sa.text("""
        UPDATE refresh_work_items
        SET due_at = GREATEST(
            due_at,
            checked_at + CASE
                WHEN attempts >= 4 THEN interval '14 days'
                WHEN attempts = 3 THEN interval '7 days'
                WHEN attempts = 2 THEN interval '3 days'
                ELSE interval '1 day'
            END
        )
        WHERE status = 'waiting_source'
          AND revision = 'baseline'
          AND priority > 40
          AND checked_at IS NOT NULL
    """))


def downgrade() -> None:
    # Corrected classifications cannot safely be distinguished from newer rows.
    pass
