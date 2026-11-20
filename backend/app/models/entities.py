import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    street_address: Mapped[str] = mapped_column(String(200), nullable=False)
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(2), default="DE", nullable=False)
    vat_id: Mapped[str] = mapped_column(String(50), nullable=False)  # USt-IdNr.
    tax_number: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Steuernummer
    dpo_email: Mapped[str] = mapped_column(String(200), nullable=False)  # Datenschutzbeauftragter
    support_email: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sites: Mapped[list["Site"]] = relationship(back_populates="organization")


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    site_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Berlin", nullable=False)
    total_spaces: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    privacy_notice_url: Mapped[str] = mapped_column(String(300), nullable=False)
    compliant_purge_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    paid_purge_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    pay_later_grace_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    drive_through_grace_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organization: Mapped["Organization"] = relationship(back_populates="sites")
    lanes: Mapped[list["Lane"]] = relationship(back_populates="site")
    tariff_plans: Mapped[list["TariffPlan"]] = relationship(back_populates="site")


class Lane(Base):
    __tablename__ = "lanes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lane_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # ENTRY | EXIT | BIDIRECTIONAL
    capture_mode: Mapped[str] = mapped_column(
        String(30), default="EDGE_RTSP", nullable=False
    )  # EDGE_RTSP | SMART_WEBHOOK
    camera_vendor: Mapped[str] = mapped_column(
        String(40), default="edge_ai", nullable=False
    )  # edge_ai | axis | hikvision | arh | generic
    requires_server_redaction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hmac_secret: Mapped[str] = mapped_column(String(128), nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    site: Mapped["Site"] = relationship(back_populates="lanes")


class TariffPlan(Base):
    __tablename__ = "tariff_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    vat_rate_bps: Mapped[int] = mapped_column(Integer, default=1900, nullable=False)  # 19.00%
    weekday_free_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)  # 4h free Mon-Fri
    weekend_all_day_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    weekend_free_minutes: Mapped[int] = mapped_column(Integer, default=1440, nullable=False)
    # Ordered hourly tiers in cents after free window; last tier repeats for each subsequent hour
    hourly_tiers_cents: Mapped[list[int]] = mapped_column(
        JSON, default=lambda: [300, 400, 500], nullable=False
    )
    daily_max_cents: Mapped[int] = mapped_column(Integer, default=2500, nullable=False)
    violation_penalty_cents: Mapped[int] = mapped_column(Integer, default=3500, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    site: Mapped["Site"] = relationship(back_populates="tariff_plans")


class Whitelist(Base):
    __tablename__ = "whitelists"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plate_normalized: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class CameraEvent(Base):
    """Ephemeral raw plate pass — plate text and S3 object keys are hard-purged per DSGVO."""

    __tablename__ = "camera_events"
    __table_args__ = (
        Index("ix_camera_events_site_captured", "site_id", "captured_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    lane_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("lanes.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)  # ENTRY | EXIT
    plate_raw: Mapped[str | None] = mapped_column(String(40), nullable=True)
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    plate_country: Mapped[str] = mapped_column(String(8), default="DE", nullable=False)
    plate_type: Mapped[str] = mapped_column(String(24), default="STANDARD", nullable=False)
    ocr_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    vendor: Mapped[str] = mapped_column(String(40), default="edge_ai", nullable=False)
    plate_crop_s3_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    context_blurred_s3_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ParkingSession(Base):
    __tablename__ = "parking_sessions"
    __table_args__ = (
        Index("ix_sessions_site_status", "site_id", "status"),
        Index("ix_sessions_plate_status", "plate_normalized", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    tariff_plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tariff_plans.id"), nullable=False
    )
    entry_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("camera_events.id"), nullable=False
    )
    exit_event_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("camera_events.id"), nullable=True
    )
    # Nulled on DSGVO purge; anonymized duration & fee bucket remain for ops reconciliation
    plate_normalized: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plate_display: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plate_country: Mapped[str] = mapped_column(String(8), default="DE", nullable=False)
    plate_type: Mapped[str] = mapped_column(String(24), default="STANDARD", nullable=False)
    fuzzy_candidate_plate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_whitelisted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validated_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validated_full_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ACTIVE | RECONCILIATION_NEEDED | COMPLETED_FREE | AWAITING_PAYMENT | PAID | VIOLATION_PENDING | VIOLATION_CONFIRMED | PURGED
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    calculated_fee_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    pay_later_deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pii_purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class MerchantAccount(Base):
    __tablename__ = "merchant_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    default_bonus_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    api_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SessionValidation(Base):
    __tablename__ = "session_validations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    merchant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("merchant_accounts.id"), nullable=False
    )
    bonus_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    full_free: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    voucher_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DriverAccount(Base):
    __tablename__ = "driver_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    consent_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AutoPayVehicle(Base):
    __tablename__ = "autopay_vehicles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    driver_account_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("driver_accounts.id", ondelete="CASCADE"), nullable=False
    )
    plate_normalized: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_sessions.id"), nullable=False, index=True
    )
    driver_account_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("driver_accounts.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)  # stripe | mock
    provider_ref: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    method: Mapped[str] = mapped_column(
        String(32), default="CARD", nullable=False
    )  # CARD | SEPA | APPLE_PAY | GOOGLE_PAY | PAYPAL | KIOSK | MOCK
    status: Mapped[str] = mapped_column(
        String(24), default="PENDING", nullable=False
    )  # PENDING | SUCCEEDED | FAILED | REFUNDED
    gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_rate_bps: Mapped[int] = mapped_column(Integer, default=1900, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    locale: Mapped[str] = mapped_column(String(5), default="de", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Invoice(Base):
    """Decoupled GoBD/§ 147 AO accounting record (retained 8 years without camera images)."""

    __tablename__ = "invoices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    payment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payments.id"), unique=True, nullable=False
    )
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id"), nullable=False)
    site_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer_legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer_vat_id: Mapped[str] = mapped_column(String(50), nullable=False)
    parking_entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parking_exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    net_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_rate_bps: Mapped[int] = mapped_column(Integer, default=1900, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    pdf_s3_key: Mapped[str] = mapped_column(String(300), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    case_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("parking_sessions.id"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32), default="QA_QUEUE", nullable=False
    )  # QA_QUEUE | APPROVED | KBA_REQUESTED | NOTICE_SENT | DISPUTED | PAID | CANCELLED | INKASSO
    penalty_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    kba_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    kba_request_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    keeper_name_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    keeper_address_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    qa_reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    qa_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    qa_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    violation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("violations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    nominated_driver_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nominated_driver_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_s3_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="OPEN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DSGVOPurgeAuditLog(Base):
    """Immutable zero-PII audit log proving automated DSGVO Art. 5(1)(e) deletion."""

    __tablename__ = "dsgvo_purge_audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    session_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    site_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    purge_reason: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # COMPLIANT_FREE_EXIT | PAID_SETTLED | ART17_ERASURE | QA_REJECTED
    s3_objects_deleted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    events_anonymized: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    purged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailySiteAnalytics(Base):
    """Fully anonymized long-term analytics aggregated prior to DSGVO PII purge."""

    __tablename__ = "daily_site_analytics"
    __table_args__ = (UniqueConstraint("site_id", "day", name="uq_daily_analytics_site_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
    )
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_sessions_purged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    paid_sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_revenue_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
