from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage.base import ObjectStorageAdapter
from app.domain.autopay import try_autopay_settle_on_exit
from app.domain.plates_de import ocr_weighted_distance, parse_plate
from app.domain.tariffs import calculate_tariff
from app.models.entities import CameraEvent, Lane, ParkingSession, Site, TariffPlan, Whitelist

DEBOUNCE_SECONDS = 60
MAX_FUZZY_DISTANCE = 1.0


@dataclass(frozen=True)
class MatchOutcome:
    event: CameraEvent
    session: ParkingSession | None
    action: str
    calculated_fee_cents: int


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _is_plate_whitelisted(db: Session, site_id: str, plate_normalized: str, at_time: datetime) -> bool:
    stmt = select(Whitelist).where(
        Whitelist.site_id == site_id,
        Whitelist.plate_normalized == plate_normalized,
        Whitelist.is_active.is_(True),
    )
    entries = db.scalars(stmt).all()
    for wl in entries:
        v_from = _ensure_utc(wl.valid_from)
        v_to = _ensure_utc(wl.valid_to) if wl.valid_to else None
        if v_from <= at_time and (v_to is None or at_time <= v_to):
            return True
    return False


def _get_active_tariff(db: Session, site_id: str) -> TariffPlan:
    plan = db.scalars(
        select(TariffPlan)
        .where(TariffPlan.site_id == site_id, TariffPlan.is_active.is_(True))
        .order_by(TariffPlan.created_at.desc())
    ).first()
    if plan is None:
        raise ValueError(f"No active tariff plan configured for site {site_id}")
    return plan


def process_camera_pass(
    db: Session,
    *,
    site: Site,
    lane: Lane,
    idempotency_key: str,
    direction: str,
    plate_raw: str,
    ocr_confidence: float,
    captured_at: datetime,
    vendor: str,
    plate_crop_s3_key: str | None = None,
    context_blurred_s3_key: str | None = None,
    storage: ObjectStorageAdapter | None = None,
) -> MatchOutcome:
    """
    Core entry/exit session state machine:
    1. Idempotency check (safe against Edge SQLite retries)
    2. German/EU plate normalization
    3. Lane debounce check (ignores duplicate frames within 60s)
    4. ENTRY -> opens ACTIVE session
    5. EXIT -> exact match OR OCR-aware fuzzy match -> calculates tariff / PayLater deadline
    """
    captured_utc = _ensure_utc(captured_at)
    parsed = parse_plate(plate_raw)

    # 1. Exact idempotency check
    existing_event = db.scalars(
        select(CameraEvent).where(CameraEvent.idempotency_key == idempotency_key)
    ).first()
    if existing_event is not None:
        existing_session = db.scalars(
            select(ParkingSession).where(
                (ParkingSession.entry_event_id == existing_event.id)
                | (ParkingSession.exit_event_id == existing_event.id)
            )
        ).first()
        return MatchOutcome(
            event=existing_event,
            session=existing_session,
            action="DUPLICATE_IGNORED",
            calculated_fee_cents=existing_session.calculated_fee_cents if existing_session else 0,
        )

    # 2. Lane debounce: same plate, same lane, within DEBOUNCE_SECONDS
    debounce_cutoff = captured_utc - timedelta(seconds=DEBOUNCE_SECONDS)
    recent = db.scalars(
        select(CameraEvent)
        .where(
            CameraEvent.lane_id == lane.id,
            CameraEvent.plate_normalized == parsed.normalized,
            CameraEvent.captured_at >= debounce_cutoff,
            CameraEvent.captured_at <= captured_utc + timedelta(seconds=5),
        )
        .order_by(CameraEvent.captured_at.desc())
    ).first()
    if recent is not None:
        return MatchOutcome(
            event=recent,
            session=None,
            action="DUPLICATE_IGNORED",
            calculated_fee_cents=0,
        )

    # Persist ephemeral camera event
    event = CameraEvent(
        idempotency_key=idempotency_key,
        site_id=site.id,
        lane_id=lane.id,
        direction=direction,
        plate_raw=plate_raw,
        plate_normalized=parsed.normalized,
        plate_country=parsed.country,
        plate_type=parsed.plate_type,
        ocr_confidence=ocr_confidence,
        vendor=vendor,
        plate_crop_s3_key=plate_crop_s3_key,
        context_blurred_s3_key=context_blurred_s3_key,
        captured_at=captured_utc,
    )
    db.add(event)
    db.flush()

    if direction == "ENTRY":
        plan = _get_active_tariff(db, site.id)
        whitelisted = _is_plate_whitelisted(db, site.id, parsed.normalized, captured_utc)
        session = ParkingSession(
            site_id=site.id,
            tariff_plan_id=plan.id,
            entry_event_id=event.id,
            plate_normalized=parsed.normalized,
            plate_display=parsed.display,
            plate_country=parsed.country,
            plate_type=parsed.plate_type,
            is_whitelisted=whitelisted,
            entry_at=captured_utc,
            status="ACTIVE",
            currency=plan.currency,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return MatchOutcome(
            event=event,
            session=session,
            action="SESSION_OPENED",
            calculated_fee_cents=0,
        )

    # EXIT flow: try exact ACTIVE session match first
    active_session = db.scalars(
        select(ParkingSession)
        .where(
            ParkingSession.site_id == site.id,
            ParkingSession.plate_normalized == parsed.normalized,
            ParkingSession.status == "ACTIVE",
        )
        .order_by(ParkingSession.entry_at.desc())
    ).first()

    fuzzy_matched = False
    if active_session is None:
        # OCR-aware fuzzy match across open ACTIVE sessions on the same site
        candidates = db.scalars(
            select(ParkingSession)
            .where(
                ParkingSession.site_id == site.id,
                ParkingSession.status == "ACTIVE",
                ParkingSession.plate_normalized.is_not(None),
            )
            .order_by(ParkingSession.entry_at.desc())
        ).all()
        best_session: ParkingSession | None = None
        best_dist = MAX_FUZZY_DISTANCE + 0.01
        for cand in candidates:
            if not cand.plate_normalized:
                continue
            dist = ocr_weighted_distance(cand.plate_normalized, parsed.normalized)
            if dist <= MAX_FUZZY_DISTANCE and dist < best_dist:
                best_dist = dist
                best_session = cand
        if best_session is not None:
            active_session = best_session
            fuzzy_matched = True

    if active_session is None:
        db.commit()
        return MatchOutcome(
            event=event,
            session=None,
            action="ORPHAN_EXIT",
            calculated_fee_cents=0,
        )

    plan = db.get(TariffPlan, active_session.tariff_plan_id) or _get_active_tariff(db, site.id)
    tariff = calculate_tariff(
        entry_at=active_session.entry_at,
        exit_at=captured_utc,
        site=site,
        plan=plan,
        is_whitelisted=active_session.is_whitelisted,
        validated_minutes=active_session.validated_minutes,
        validated_full_free=active_session.validated_full_free,
    )

    active_session.exit_event_id = event.id
    active_session.exit_at = captured_utc
    active_session.duration_minutes = tariff.duration_minutes
    active_session.calculated_fee_cents = tariff.gross_cents

    if fuzzy_matched:
        active_session.fuzzy_candidate_plate = parsed.display
        active_session.status = "RECONCILIATION_NEEDED"
        action = "FUZZY_RECONCILIATION"
    elif tariff.gross_cents == 0:
        active_session.status = "COMPLETED_FREE"
        action = "SESSION_CLOSED_FREE"
    elif active_session.paid_cents >= tariff.gross_cents:
        active_session.status = "PAID"
        action = "SESSION_PAID"
    else:
        remaining = max(0, tariff.gross_cents - active_session.paid_cents)
        autopay_payment = try_autopay_settle_on_exit(
            db,
            storage,
            session=active_session,
            site=site,
            plan=plan,
            gross_cents=remaining,
        )
        if autopay_payment is not None:
            action = "SESSION_AUTOPAY_CHARGED"
        else:
            active_session.status = "AWAITING_PAYMENT"
            active_session.pay_later_deadline_at = captured_utc + timedelta(
                hours=site.pay_later_grace_hours
            )
            action = "SESSION_AWAITING_PAYMENT"

    db.commit()
    db.refresh(active_session)
    return MatchOutcome(
        event=event,
        session=active_session,
        action=action,
        calculated_fee_cents=tariff.gross_cents,
    )
