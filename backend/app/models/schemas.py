from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EdgeIngestRequest(BaseModel):
    idempotency_key: str = Field(min_length=4, max_length=100)
    lane_code: str = Field(min_length=2, max_length=50)
    direction: str = Field(pattern="^(ENTRY|EXIT)$")
    plate_raw: str = Field(min_length=2, max_length=40)
    ocr_confidence: float = Field(ge=0.0, le=1.0)
    captured_at: datetime
    plate_crop_b64: str | None = None
    context_blurred_b64: str | None = None
    already_redacted: bool = True


class IngestResponse(BaseModel):
    event_id: str
    session_id: str | None = None
    action: str  # SESSION_OPENED | SESSION_CLOSED_FREE | SESSION_AWAITING_PAYMENT | SESSION_PAID | FUZZY_RECONCILIATION | DUPLICATE_IGNORED | ORPHAN_EXIT
    plate_normalized: str
    plate_display: str
    plate_country: str
    plate_type: str
    calculated_fee_cents: int = 0
    currency: str = "EUR"


class HeartbeatRequest(BaseModel):
    lane_code: str
    status: str = "OK"
    fps: float | None = None
    queued_offline_events: int = 0


class TariffBreakdownDTO(BaseModel):
    duration_minutes: int
    drive_through_free: bool
    is_whitelisted: bool
    free_minutes_applied: int
    validated_minutes_applied: int
    billable_minutes: int
    billable_hours: int
    gross_cents: int
    net_cents: int
    vat_cents: int
    vat_rate_percent: float
    currency: str = "EUR"
    reason_code: str


class SessionLookupResponse(BaseModel):
    found: bool
    session_id: str | None = None
    site_code: str | None = None
    site_name: str | None = None
    plate_masked: str | None = None
    plate_display: str | None = None
    plate_country: str | None = None
    status: str | None = None
    entry_at: datetime | None = None
    exit_at: datetime | None = None
    pay_later_deadline_at: datetime | None = None
    amount_due_cents: int = 0
    paid_cents: int = 0
    currency: str = "EUR"
    invoice_number: str | None = None
    breakdown: TariffBreakdownDTO | None = None


class CheckoutRequest(BaseModel):
    session_id: str
    locale: str = Field(default="de", pattern="^(de|en)$")
    payment_method: str = Field(default="CARD")


class CheckoutResponse(BaseModel):
    payment_id: str
    provider: str
    provider_ref: str
    checkout_url: str
    gross_cents: int
    net_cents: int
    vat_cents: int
    currency: str = "EUR"
    requires_mock_confirm: bool = False


class MockConfirmRequest(BaseModel):
    payment_id: str
    method: str = "APPLE_PAY"


class PaymentSettledResponse(BaseModel):
    payment_id: str
    session_id: str
    status: str
    invoice_number: str
    invoice_pdf_url: str
    gross_cents: int
    net_cents: int
    vat_cents: int
    currency: str = "EUR"


class LaneStatusDTO(BaseModel):
    lane_code: str
    name: str
    direction: str
    capture_mode: str
    camera_vendor: str
    last_heartbeat_at: datetime | None
    online: bool


class AdminOverviewResponse(BaseModel):
    site_id: str
    site_code: str
    site_name: str
    total_spaces: int
    active_vehicles: int
    occupancy_percent: float
    reconciliation_needed_count: int
    awaiting_payment_count: int
    total_revenue_cents: int
    total_purged_sessions: int
    lanes: list[LaneStatusDTO]


class AdminSessionDTO(BaseModel):
    id: str
    site_code: str
    plate_display: str | None
    plate_country: str
    plate_type: str
    fuzzy_candidate_plate: str | None
    status: str
    is_whitelisted: bool
    entry_at: datetime
    exit_at: datetime | None
    duration_minutes: int
    calculated_fee_cents: int
    paid_cents: int
    pii_purged_at: datetime | None


class ReconcileSessionRequest(BaseModel):
    confirmed_plate: str
    action: str = Field(pattern="^(APPROVE_PAIR|MARK_FREE|KEEP_AWAITING_PAYMENT)$")


class SimulatePassRequest(BaseModel):
    lane_code: str
    direction: str = Field(pattern="^(ENTRY|EXIT)$")
    plate_raw: str
    vendor: str = Field(default="edge_ai", pattern="^(edge_ai|axis|hikvision|arh|generic)$")
    minutes_ago: int = Field(default=0, ge=0, le=10080)
    ocr_confidence: float = Field(default=0.97, ge=0.1, le=1.0)


class PurgeRunRequest(BaseModel):
    force_immediate: bool = False


class PurgeRunResponse(BaseModel):
    sessions_purged: int
    s3_objects_deleted: int
    events_anonymized: int
    ran_at: datetime


class DSGVOPurgeAuditDTO(BaseModel):
    id: str
    session_uuid: str
    site_id: str
    purge_reason: str
    s3_objects_deleted: int
    events_anonymized: int
    purged_at: datetime


class SiteCreateRequest(BaseModel):
    site_code: str = Field(min_length=3, max_length=50)
    name: str = Field(min_length=2, max_length=200)
    address: str = Field(min_length=5, max_length=300)
    total_spaces: int = Field(default=200, ge=1, le=50000)
    privacy_notice_url: str = "https://parkvektor.de/datenschutz"
    weekday_free_minutes: int = Field(default=240, ge=0)
    weekend_all_day_free: bool = True
    hourly_tiers_cents: list[int] = Field(default_factory=lambda: [300, 400, 500])
    daily_max_cents: int = Field(default=2500, ge=0)
    violation_penalty_cents: int = Field(default=3500, ge=0)


class SitePublicInfoResponse(BaseModel):
    site_code: str
    name: str
    address: str
    privacy_notice_url: str
    weekday_free_minutes: int
    weekend_all_day_free: bool
    drive_through_grace_minutes: int
    pay_later_grace_hours: int
    hourly_tiers_cents: list[int]
    daily_max_cents: int
    vat_rate_percent: float


class DSGVOExportResponse(BaseModel):
    plate_normalized: str
    exported_at: datetime
    active_or_retained_sessions: list[dict[str, Any]]
    note: str
