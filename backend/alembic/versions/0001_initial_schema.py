"""Initial DSGVO-compliant schema for parkvektor-private-de

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-19 20:50:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("street_address", sa.String(200), nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("vat_id", sa.String(50), nullable=False),
        sa.Column("tax_number", sa.String(50), nullable=True),
        sa.Column("dpo_email", sa.String(200), nullable=False),
        sa.Column("support_email", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("site_code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("total_spaces", sa.Integer, nullable=False),
        sa.Column("privacy_notice_url", sa.String(300), nullable=False),
        sa.Column("compliant_purge_hours", sa.Integer, nullable=False),
        sa.Column("paid_purge_hours", sa.Integer, nullable=False),
        sa.Column("pay_later_grace_hours", sa.Integer, nullable=False),
        sa.Column("drive_through_grace_minutes", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sites_site_code", "sites", ["site_code"])

    op.create_table(
        "lanes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lane_code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("capture_mode", sa.String(30), nullable=False),
        sa.Column("camera_vendor", sa.String(40), nullable=False),
        sa.Column("requires_server_redaction", sa.Boolean, nullable=False),
        sa.Column("hmac_secret", sa.String(128), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False),
    )
    op.create_index("ix_lanes_site_id", "lanes", ["site_id"])
    op.create_index("ix_lanes_lane_code", "lanes", ["lane_code"])

    op.create_table(
        "tariff_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("vat_rate_bps", sa.Integer, nullable=False),
        sa.Column("weekday_free_minutes", sa.Integer, nullable=False),
        sa.Column("weekend_all_day_free", sa.Boolean, nullable=False),
        sa.Column("weekend_free_minutes", sa.Integer, nullable=False),
        sa.Column("hourly_tiers_cents", sa.JSON, nullable=False),
        sa.Column("daily_max_cents", sa.Integer, nullable=False),
        sa.Column("violation_penalty_cents", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "whitelists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plate_normalized", sa.String(32), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False),
    )
    op.create_index("ix_whitelists_plate", "whitelists", ["plate_normalized"])

    op.create_table(
        "camera_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lane_id", sa.String(36), sa.ForeignKey("lanes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("plate_raw", sa.String(40), nullable=True),
        sa.Column("plate_normalized", sa.String(32), nullable=True),
        sa.Column("plate_country", sa.String(8), nullable=False),
        sa.Column("plate_type", sa.String(24), nullable=False),
        sa.Column("ocr_confidence", sa.Float, nullable=False),
        sa.Column("vendor", sa.String(40), nullable=False),
        sa.Column("plate_crop_s3_key", sa.String(300), nullable=True),
        sa.Column("context_blurred_s3_key", sa.String(300), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_camera_events_site_captured", "camera_events", ["site_id", "captured_at"])

    op.create_table(
        "parking_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tariff_plan_id", sa.String(36), sa.ForeignKey("tariff_plans.id"), nullable=False),
        sa.Column("entry_event_id", sa.String(36), sa.ForeignKey("camera_events.id"), nullable=False),
        sa.Column("exit_event_id", sa.String(36), sa.ForeignKey("camera_events.id"), nullable=True),
        sa.Column("plate_normalized", sa.String(32), nullable=True),
        sa.Column("plate_display", sa.String(32), nullable=True),
        sa.Column("plate_country", sa.String(8), nullable=False),
        sa.Column("plate_type", sa.String(24), nullable=False),
        sa.Column("fuzzy_candidate_plate", sa.String(32), nullable=True),
        sa.Column("is_whitelisted", sa.Boolean, nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("validated_minutes", sa.Integer, nullable=False),
        sa.Column("validated_full_free", sa.Boolean, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("calculated_fee_cents", sa.Integer, nullable=False),
        sa.Column("paid_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("pay_later_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pii_purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_site_status", "parking_sessions", ["site_id", "status"])
    op.create_index("ix_sessions_plate_status", "parking_sessions", ["plate_normalized", "status"])

    op.create_table(
        "merchant_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("default_bonus_minutes", sa.Integer, nullable=False),
        sa.Column("api_token", sa.String(128), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False),
    )

    op.create_table(
        "session_validations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("parking_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("merchant_accounts.id"), nullable=False),
        sa.Column("bonus_minutes", sa.Integer, nullable=False),
        sa.Column("full_free", sa.Boolean, nullable=False),
        sa.Column("voucher_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "driver_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(120), nullable=True),
        sa.Column("consent_accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "autopay_vehicles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("driver_account_id", sa.String(36), sa.ForeignKey("driver_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plate_normalized", sa.String(32), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("parking_sessions.id"), nullable=False),
        sa.Column("driver_account_id", sa.String(36), sa.ForeignKey("driver_accounts.id"), nullable=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_ref", sa.String(120), nullable=False, unique=True),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("gross_cents", sa.Integer, nullable=False),
        sa.Column("net_cents", sa.Integer, nullable=False),
        sa.Column("vat_cents", sa.Integer, nullable=False),
        sa.Column("vat_rate_bps", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invoice_number", sa.String(40), nullable=False, unique=True),
        sa.Column("payment_id", sa.String(36), sa.ForeignKey("payments.id"), nullable=False, unique=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("site_name_snapshot", sa.String(200), nullable=False),
        sa.Column("issuer_legal_name", sa.String(200), nullable=False),
        sa.Column("issuer_vat_id", sa.String(50), nullable=False),
        sa.Column("parking_entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parking_exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=False),
        sa.Column("gross_cents", sa.Integer, nullable=False),
        sa.Column("net_cents", sa.Integer, nullable=False),
        sa.Column("vat_cents", sa.Integer, nullable=False),
        sa.Column("vat_rate_bps", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("pdf_s3_key", sa.String(300), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "violations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("case_number", sa.String(40), nullable=False, unique=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("parking_sessions.id"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("penalty_cents", sa.Integer, nullable=False),
        sa.Column("kba_provider", sa.String(40), nullable=True),
        sa.Column("kba_request_ref", sa.String(120), nullable=True),
        sa.Column("keeper_name_encrypted", sa.Text, nullable=True),
        sa.Column("keeper_address_encrypted", sa.Text, nullable=True),
        sa.Column("qa_reviewer", sa.String(120), nullable=True),
        sa.Column("qa_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qa_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "disputes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("violation_id", sa.String(36), sa.ForeignKey("violations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("nominated_driver_name", sa.String(200), nullable=True),
        sa.Column("nominated_driver_address", sa.Text, nullable=True),
        sa.Column("evidence_s3_key", sa.String(300), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "dsgvo_purge_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_uuid", sa.String(36), nullable=False),
        sa.Column("site_id", sa.String(36), nullable=False),
        sa.Column("purge_reason", sa.String(64), nullable=False),
        sa.Column("s3_objects_deleted", sa.Integer, nullable=False),
        sa.Column("events_anonymized", sa.Integer, nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "daily_site_analytics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date, nullable=False),
        sa.Column("total_sessions_purged", sa.Integer, nullable=False),
        sa.Column("free_sessions_count", sa.Integer, nullable=False),
        sa.Column("paid_sessions_count", sa.Integer, nullable=False),
        sa.Column("total_revenue_cents", sa.Integer, nullable=False),
        sa.Column("total_duration_minutes", sa.Integer, nullable=False),
        sa.UniqueConstraint("site_id", "day", name="uq_daily_analytics_site_day"),
    )


def downgrade() -> None:
    for table in [
        "daily_site_analytics",
        "dsgvo_purge_audit_log",
        "disputes",
        "violations",
        "invoices",
        "payments",
        "autopay_vehicles",
        "driver_accounts",
        "session_validations",
        "merchant_accounts",
        "parking_sessions",
        "camera_events",
        "whitelists",
        "tariff_plans",
        "lanes",
        "sites",
        "organizations",
    ]:
        op.drop_table(table)
