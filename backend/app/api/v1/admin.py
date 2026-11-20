import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.storage.base import ObjectStorageAdapter
from app.adapters.storage.factory import get_storage_adapter
from app.api.v1.deps import require_admin_key
from app.db.session import get_db
from app.domain.matcher import process_camera_pass
from app.domain.plates_de import parse_plate
from app.domain.retention import erase_plate_art17, run_dsgvo_auto_purge
from app.models.entities import (
    DailySiteAnalytics,
    DSGVOPurgeAuditLog,
    Lane,
    Organization,
    ParkingSession,
    Payment,
    Site,
    TariffPlan,
)
from app.models.schemas import (
    AdminOverviewResponse,
    AdminSessionDTO,
    DSGVOExportResponse,
    DSGVOPurgeAuditDTO,
    IngestResponse,
    LaneStatusDTO,
    PurgeRunRequest,
    PurgeRunResponse,
    ReconcileSessionRequest,
    SimulatePassRequest,
    SiteCreateRequest,
)

router = APIRouter(prefix="/admin", tags=["Operator Admin & DSGVO"], dependencies=[Depends(require_admin_key)])


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


@router.get("/overview", response_model=AdminOverviewResponse)
def get_admin_overview(
    site_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AdminOverviewResponse:
    stmt = select(Site).where(Site.is_active.is_(True))
    if site_code:
        stmt = stmt.where(Site.site_code == site_code)
    site = db.scalars(stmt.order_by(Site.created_at.asc())).first()
    if site is None:
        raise HTTPException(status_code=404, detail="No active site configured")

    active_vehicles = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.site_id == site.id,
            ParkingSession.status == "ACTIVE",
        )
    ) or 0
    reconciliation_needed = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.site_id == site.id,
            ParkingSession.status == "RECONCILIATION_NEEDED",
        )
    ) or 0
    awaiting_payment = db.scalar(
        select(func.count(ParkingSession.id)).where(
            ParkingSession.site_id == site.id,
            ParkingSession.status == "AWAITING_PAYMENT",
        )
    ) or 0
    total_revenue = db.scalar(
        select(func.coalesce(func.sum(Payment.gross_cents), 0))
        .join(ParkingSession, Payment.session_id == ParkingSession.id)
        .where(ParkingSession.site_id == site.id, Payment.status == "SUCCEEDED")
    ) or 0
    total_purged = db.scalar(
        select(func.count(DSGVOPurgeAuditLog.id)).where(DSGVOPurgeAuditLog.site_id == site.id)
    ) or 0

    now = datetime.now(UTC)
    lanes = db.scalars(select(Lane).where(Lane.site_id == site.id).order_by(Lane.lane_code)).all()
    lane_dtos: list[LaneStatusDTO] = []
    for ln in lanes:
        hb = _ensure_utc(ln.last_heartbeat_at)
        online = hb is not None and (now - hb) <= timedelta(minutes=10)
        lane_dtos.append(
            LaneStatusDTO(
                lane_code=ln.lane_code,
                name=ln.name,
                direction=ln.direction,
                capture_mode=ln.capture_mode,
                camera_vendor=ln.camera_vendor,
                last_heartbeat_at=hb,
                online=online,
            )
        )

    occ = round((active_vehicles / max(1, site.total_spaces)) * 100.0, 1)
    return AdminOverviewResponse(
        site_id=site.id,
        site_code=site.site_code,
        site_name=site.name,
        total_spaces=site.total_spaces,
        active_vehicles=active_vehicles,
        occupancy_percent=occ,
        reconciliation_needed_count=reconciliation_needed,
        awaiting_payment_count=awaiting_payment,
        total_revenue_cents=int(total_revenue),
        total_purged_sessions=int(total_purged),
        lanes=lane_dtos,
    )


@router.get("/sites")
def list_sites(db: Session = Depends(get_db)) -> list[dict]:
    sites = db.scalars(select(Site).order_by(Site.created_at.asc())).all()
    return [
        {
            "id": s.id,
            "site_code": s.site_code,
            "name": s.name,
            "address": s.address,
            "total_spaces": s.total_spaces,
            "compliant_purge_hours": s.compliant_purge_hours,
            "pay_later_grace_hours": s.pay_later_grace_hours,
        }
        for s in sites
    ]


@router.post("/sites", status_code=201)
def create_site(req: SiteCreateRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    org = db.scalars(select(Organization).order_by(Organization.created_at.asc())).first()
    if org is None:
        raise HTTPException(status_code=400, detail="Organization not seeded")

    site = Site(
        organization_id=org.id,
        site_code=req.site_code.upper(),
        name=req.name,
        address=req.address,
        total_spaces=req.total_spaces,
        privacy_notice_url=req.privacy_notice_url,
    )
    db.add(site)
    db.flush()

    tariff = TariffPlan(
        site_id=site.id,
        name="Standard Mall Tariff DE",
        weekday_free_minutes=req.weekday_free_minutes,
        weekend_all_day_free=req.weekend_all_day_free,
        hourly_tiers_cents=req.hourly_tiers_cents,
        daily_max_cents=req.daily_max_cents,
        violation_penalty_cents=req.violation_penalty_cents,
    )
    db.add(tariff)
    db.commit()
    return {"id": site.id, "site_code": site.site_code}


@router.get("/sessions", response_model=list[AdminSessionDTO])
def list_sessions(
    site_code: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[AdminSessionDTO]:
    sites_map = {s.id: s.site_code for s in db.scalars(select(Site)).all()}
    stmt = select(ParkingSession).order_by(ParkingSession.entry_at.desc()).limit(limit)
    if site_code:
        target_ids = [sid for sid, sc in sites_map.items() if sc == site_code]
        stmt = stmt.where(ParkingSession.site_id.in_(target_ids))
    if status_filter:
        stmt = stmt.where(ParkingSession.status == status_filter)

    rows = db.scalars(stmt).all()
    return [
        AdminSessionDTO(
            id=r.id,
            site_code=sites_map.get(r.site_id, "UNKNOWN"),
            plate_display=r.plate_display,
            plate_country=r.plate_country,
            plate_type=r.plate_type,
            fuzzy_candidate_plate=r.fuzzy_candidate_plate,
            status=r.status,
            is_whitelisted=r.is_whitelisted,
            entry_at=r.entry_at,
            exit_at=r.exit_at,
            duration_minutes=r.duration_minutes,
            calculated_fee_cents=r.calculated_fee_cents,
            paid_cents=r.paid_cents,
            pii_purged_at=r.pii_purged_at,
        )
        for r in rows
    ]


@router.post("/sessions/{session_id}/reconcile", response_model=AdminSessionDTO)
def reconcile_fuzzy_session(
    session_id: str,
    req: ReconcileSessionRequest,
    db: Session = Depends(get_db),
) -> AdminSessionDTO:
    """Operator QA reconciliation for OCR-fuzzy entry/exit pairs (prevents unfair fines)."""
    sess = db.get(ParkingSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    site = db.get(Site, sess.site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    parsed = parse_plate(req.confirmed_plate)
    sess.plate_normalized = parsed.normalized
    sess.plate_display = parsed.display
    sess.fuzzy_candidate_plate = None

    if req.action == "MARK_FREE":
        sess.calculated_fee_cents = 0
        sess.status = "COMPLETED_FREE"
    elif req.action == "APPROVE_PAIR":
        if sess.calculated_fee_cents == 0:
            sess.status = "COMPLETED_FREE"
        else:
            sess.status = "AWAITING_PAYMENT"
            if sess.pay_later_deadline_at is None:
                ref = _ensure_utc(sess.exit_at) or datetime.now(UTC)
                sess.pay_later_deadline_at = ref + timedelta(hours=site.pay_later_grace_hours)
    else:
        sess.status = "AWAITING_PAYMENT"

    db.commit()
    db.refresh(sess)
    return AdminSessionDTO(
        id=sess.id,
        site_code=site.site_code,
        plate_display=sess.plate_display,
        plate_country=sess.plate_country,
        plate_type=sess.plate_type,
        fuzzy_candidate_plate=sess.fuzzy_candidate_plate,
        status=sess.status,
        is_whitelisted=sess.is_whitelisted,
        entry_at=sess.entry_at,
        exit_at=sess.exit_at,
        duration_minutes=sess.duration_minutes,
        calculated_fee_cents=sess.calculated_fee_cents,
        paid_cents=sess.paid_cents,
        pii_purged_at=sess.pii_purged_at,
    )


@router.post("/simulate-pass", response_model=IngestResponse)
def simulate_camera_pass(
    req: SimulatePassRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> IngestResponse:
    """Operator-triggered vehicle pass simulator for live demos & pilot verification."""
    lane = db.scalars(select(Lane).where(Lane.lane_code == req.lane_code)).first()
    if lane is None:
        raise HTTPException(status_code=404, detail="Lane not found")
    site = db.get(Site, lane.site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")

    captured_at = datetime.now(UTC) - timedelta(minutes=req.minutes_ago)
    lane.last_heartbeat_at = datetime.now(UTC)
    outcome = process_camera_pass(
        db,
        site=site,
        lane=lane,
        idempotency_key=f"sim-{uuid.uuid4().hex}",
        direction=req.direction,
        plate_raw=req.plate_raw,
        ocr_confidence=req.ocr_confidence,
        captured_at=captured_at,
        vendor=req.vendor,
        storage=storage,
    )
    return IngestResponse(
        event_id=outcome.event.id,
        session_id=outcome.session.id if outcome.session else None,
        action=outcome.action,
        plate_normalized=outcome.event.plate_normalized or "",
        plate_display=(
            outcome.session.plate_display
            if outcome.session and outcome.session.plate_display
            else outcome.event.plate_raw or ""
        ),
        plate_country=outcome.event.plate_country,
        plate_type=outcome.event.plate_type,
        calculated_fee_cents=outcome.calculated_fee_cents,
        currency=outcome.session.currency if outcome.session else "EUR",
    )


@router.get("/dsgvo/audit-log", response_model=list[DSGVOPurgeAuditDTO])
def list_dsgvo_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[DSGVOPurgeAuditDTO]:
    rows = db.scalars(
        select(DSGVOPurgeAuditLog).order_by(DSGVOPurgeAuditLog.purged_at.desc()).limit(limit)
    ).all()
    return [
        DSGVOPurgeAuditDTO(
            id=r.id,
            session_uuid=r.session_uuid,
            site_id=r.site_id,
            purge_reason=r.purge_reason,
            s3_objects_deleted=r.s3_objects_deleted,
            events_anonymized=r.events_anonymized,
            purged_at=r.purged_at,
        )
        for r in rows
    ]


@router.get("/dsgvo/analytics")
def list_anonymized_analytics(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(DailySiteAnalytics).order_by(DailySiteAnalytics.day.desc()).limit(30)).all()
    return [
        {
            "site_id": r.site_id,
            "day": r.day.isoformat(),
            "total_sessions_purged": r.total_sessions_purged,
            "free_sessions_count": r.free_sessions_count,
            "paid_sessions_count": r.paid_sessions_count,
            "total_revenue_cents": r.total_revenue_cents,
            "total_duration_minutes": r.total_duration_minutes,
        }
        for r in rows
    ]


@router.post("/dsgvo/run-purge", response_model=PurgeRunResponse)
def trigger_dsgvo_purge(
    req: PurgeRunRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> PurgeRunResponse:
    summary = run_dsgvo_auto_purge(db, storage, force_immediate=req.force_immediate)
    return PurgeRunResponse(
        sessions_purged=summary.sessions_purged,
        s3_objects_deleted=summary.s3_objects_deleted,
        events_anonymized=summary.events_anonymized,
        ran_at=summary.ran_at,
    )


@router.get("/dsgvo/export", response_model=DSGVOExportResponse)
def export_subject_data_art15(
    plate: str = Query(..., min_length=2, max_length=40),
    db: Session = Depends(get_db),
) -> DSGVOExportResponse:
    """GDPR Art. 15 right-of-access data export for a given license plate."""
    parsed = parse_plate(plate)
    rows = db.scalars(
        select(ParkingSession)
        .where(ParkingSession.plate_normalized == parsed.normalized)
        .order_by(ParkingSession.entry_at.desc())
    ).all()
    return DSGVOExportResponse(
        plate_normalized=parsed.normalized,
        exported_at=datetime.now(UTC),
        active_or_retained_sessions=[
            {
                "session_id": r.id,
                "status": r.status,
                "entry_at": r.entry_at.isoformat(),
                "exit_at": r.exit_at.isoformat() if r.exit_at else None,
                "duration_minutes": r.duration_minutes,
                "calculated_fee_cents": r.calculated_fee_cents,
                "paid_cents": r.paid_cents,
            }
            for r in rows
        ],
        note=(
            "Previously settled compliant sessions have already been irreversibly anonymized "
            "pursuant to GDPR Art. 5(1)(e) and cannot be linked back to this license plate."
        ),
    )


@router.delete("/dsgvo/erase")
def erase_subject_data_art17(
    plate: str = Query(..., min_length=2, max_length=40),
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> dict[str, int | str]:
    """GDPR Art. 17 right-to-erasure handler respecting Art. 17(3) active legal claims."""
    parsed = parse_plate(plate)
    result = erase_plate_art17(db, storage, parsed.normalized)
    return {"plate_normalized": parsed.normalized, **result}
