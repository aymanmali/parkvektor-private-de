from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage.base import ObjectStorageAdapter
from app.models.entities import (
    CameraEvent,
    DailySiteAnalytics,
    DSGVOPurgeAuditLog,
    ParkingSession,
    Site,
)


@dataclass(frozen=True)
class PurgeSummary:
    sessions_purged: int
    s3_objects_deleted: int
    events_anonymized: int
    ran_at: datetime


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _record_anonymous_analytics(db: Session, session: ParkingSession) -> None:
    day = _ensure_utc(session.exit_at or session.entry_at).date()
    row = db.scalars(
        select(DailySiteAnalytics).where(
            DailySiteAnalytics.site_id == session.site_id,
            DailySiteAnalytics.day == day,
        )
    ).first()
    if row is None:
        row = DailySiteAnalytics(
            site_id=session.site_id,
            day=day,
            total_sessions_purged=0,
            free_sessions_count=0,
            paid_sessions_count=0,
            total_revenue_cents=0,
            total_duration_minutes=0,
        )
        db.add(row)
        db.flush()

    row.total_sessions_purged += 1
    if session.calculated_fee_cents == 0:
        row.free_sessions_count += 1
    else:
        row.paid_sessions_count += 1
        row.total_revenue_cents += session.paid_cents
    row.total_duration_minutes += session.duration_minutes


def purge_session_pii(
    db: Session,
    storage: ObjectStorageAdapter,
    session: ParkingSession,
    *,
    purge_reason: str,
    now: datetime,
) -> tuple[int, int]:
    """
    Irreversibly purge raw license plate & camera snapshot objects for a session.
    Decoupled § 147 AO invoices remain intact with zero camera photos.
    """
    s3_deleted = 0
    events_anonymized = 0

    event_ids = [eid for eid in (session.entry_event_id, session.exit_event_id) if eid]
    for eid in event_ids:
        ev = db.get(CameraEvent, eid)
        if ev is None:
            continue
        for key in (ev.plate_crop_s3_key, ev.context_blurred_s3_key):
            if key:
                if storage.delete_object(key):
                    s3_deleted += 1
        ev.plate_raw = None
        ev.plate_normalized = None
        ev.plate_crop_s3_key = None
        ev.context_blurred_s3_key = None
        ev.purged_at = now
        events_anonymized += 1

    _record_anonymous_analytics(db, session)

    session.plate_normalized = None
    session.plate_display = None
    session.fuzzy_candidate_plate = None
    session.status = "PURGED"
    session.pii_purged_at = now

    # Append zero-PII compliance proof
    audit = DSGVOPurgeAuditLog(
        session_uuid=session.id,
        site_id=session.site_id,
        purge_reason=purge_reason,
        s3_objects_deleted=s3_deleted,
        events_anonymized=events_anonymized,
        purged_at=now,
    )
    db.add(audit)
    return s3_deleted, events_anonymized


def run_dsgvo_auto_purge(
    db: Session,
    storage: ObjectStorageAdapter,
    *,
    now: datetime | None = None,
    force_immediate: bool = False,
) -> PurgeSummary:
    """
    DSGVO Art. 5(1)(e) storage-limitation worker:
    Purges COMPLETED_FREE and PAID sessions once their configured site retention window expires
    (or immediately when force_immediate=True for compliant sessions).
    """
    run_time = _ensure_utc(now or datetime.now(UTC))
    sites_by_id = {s.id: s for s in db.scalars(select(Site)).all()}

    eligible_sessions = db.scalars(
        select(ParkingSession).where(
            ParkingSession.status.in_(["COMPLETED_FREE", "PAID"]),
            ParkingSession.pii_purged_at.is_(None),
        )
    ).all()

    purged_count = 0
    total_s3 = 0
    total_events = 0

    for sess in eligible_sessions:
        site = sites_by_id.get(sess.site_id)
        if site is None:
            continue

        if sess.status == "COMPLETED_FREE":
            ref_time = _ensure_utc(sess.exit_at or sess.updated_at)
            cutoff = ref_time + timedelta(hours=site.compliant_purge_hours)
            reason = "COMPLIANT_FREE_EXIT"
        else:
            ref_time = _ensure_utc(sess.paid_at or sess.exit_at or sess.updated_at)
            cutoff = ref_time + timedelta(hours=site.paid_purge_hours)
            reason = "PAID_SETTLED"

        if force_immediate or run_time >= cutoff:
            s3_del, ev_anon = purge_session_pii(
                db, storage, sess, purge_reason=reason, now=run_time
            )
            purged_count += 1
            total_s3 += s3_del
            total_events += ev_anon

    db.commit()
    return PurgeSummary(
        sessions_purged=purged_count,
        s3_objects_deleted=total_s3,
        events_anonymized=total_events,
        ran_at=run_time,
    )


def erase_plate_art17(
    db: Session,
    storage: ObjectStorageAdapter,
    plate_normalized: str,
) -> dict[str, int]:
    """
    GDPR Art. 17 right-to-erasure handler:
    - Immediately purges COMPLETED_FREE & PAID sessions matching the plate.
    - Retains ACTIVE / AWAITING_PAYMENT / VIOLATION sessions under Art. 17(3)(b)/(e) legal claim exception.
    """
    now = datetime.now(UTC)
    sessions = db.scalars(
        select(ParkingSession).where(
            ParkingSession.plate_normalized == plate_normalized,
            ParkingSession.pii_purged_at.is_(None),
        )
    ).all()

    erased = 0
    retained_legal_hold = 0
    for sess in sessions:
        if sess.status in {"COMPLETED_FREE", "PAID"}:
            purge_session_pii(db, storage, sess, purge_reason="ART17_ERASURE", now=now)
            erased += 1
        else:
            retained_legal_hold += 1

    db.commit()
    return {"erased_sessions": erased, "retained_under_art17_3": retained_legal_hold}
