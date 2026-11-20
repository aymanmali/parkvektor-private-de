from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage.base import ObjectStorageAdapter
from app.adapters.storage.factory import get_storage_adapter
from app.api.v1.deps import require_admin_key
from app.db.session import get_db
from app.domain.plates_de import parse_plate
from app.domain.retention import purge_session_pii
from app.models.entities import Dispute, ParkingSession, Site, Violation

router = APIRouter(tags=["Widerspruchsportal (Disputes)"])


class DisputeSubmitRequest(BaseModel):
    case_number: str = Field(min_length=4, max_length=40)
    plate_raw: str = Field(min_length=2, max_length=40)
    reason: str = Field(pattern="^(PAID_ELSEWHERE|RECEIPT_UPLOADED|NOT_DRIVER|CAMERA_ERROR|OTHER)$")
    explanation: str | None = Field(default=None, max_length=2000)
    nominated_driver_name: str | None = Field(default=None, max_length=200)
    nominated_driver_address: str | None = Field(default=None, max_length=500)


class DisputePayRequest(BaseModel):
    case_number: str
    plate_raw: str


class AdminResolveDisputeRequest(BaseModel):
    decision: str = Field(pattern="^(ACCEPT_CANCEL|REJECT_UPHOLD)$")


def _lookup_verified_case(db: Session, case_number: str, plate_raw: str) -> tuple[Violation, ParkingSession]:
    """Require both Case Number AND Plate match to protect driver privacy."""
    parsed = parse_plate(plate_raw)
    violation = db.scalars(
        select(Violation).where(Violation.case_number == case_number.strip().upper())
    ).first()
    if violation is None:
        raise HTTPException(status_code=404, detail="Case not found or plate mismatch")
    sess = db.get(ParkingSession, violation.session_id)
    if sess is None or sess.plate_normalized != parsed.normalized:
        raise HTTPException(status_code=404, detail="Case not found or plate mismatch")
    return violation, sess


@router.get("/public/disputes/case")
def lookup_dispute_case(
    case_number: str = Query(..., min_length=4),
    plate: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
) -> dict:
    violation, sess = _lookup_verified_case(db, case_number, plate)
    site = db.get(Site, sess.site_id)
    disputes = db.scalars(
        select(Dispute).where(Dispute.violation_id == violation.id).order_by(Dispute.created_at.desc())
    ).all()
    return {
        "violation_id": violation.id,
        "case_number": violation.case_number,
        "status": violation.status,
        "site_name": site.name if site else "Unknown",
        "site_address": site.address if site else "",
        "plate_display": sess.plate_display,
        "plate_country": sess.plate_country,
        "entry_at": sess.entry_at.isoformat(),
        "exit_at": sess.exit_at.isoformat() if sess.exit_at else None,
        "duration_minutes": sess.duration_minutes,
        "unpaid_fee_cents": max(0, sess.calculated_fee_cents - sess.paid_cents),
        "penalty_cents": violation.penalty_cents,
        "currency": sess.currency,
        "disputes": [
            {
                "id": d.id,
                "reason": d.reason,
                "status": d.status,
                "explanation": d.explanation,
                "nominated_driver_name": d.nominated_driver_name,
                "created_at": d.created_at.isoformat(),
            }
            for d in disputes
        ],
    }


@router.post("/public/disputes/submit", status_code=201)
def submit_dispute(req: DisputeSubmitRequest, db: Session = Depends(get_db)) -> dict:
    """
    Driver Widerspruch submission supporting BGH sekundäre Darlegungslast
    (keeper may nominate the actual driver when reason == NOT_DRIVER).
    """
    violation, _sess = _lookup_verified_case(db, req.case_number, req.plate_raw)
    if violation.status in {"PAID", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="This violation case is already closed")

    if req.reason == "NOT_DRIVER" and not (req.nominated_driver_name and req.nominated_driver_address):
        raise HTTPException(
            status_code=400,
            detail="Under BGH secondary burden of proof (sekundäre Darlegungslast), please provide the driver's name and address.",
        )

    dispute = Dispute(
        violation_id=violation.id,
        reason=req.reason,
        explanation=req.explanation,
        nominated_driver_name=req.nominated_driver_name,
        nominated_driver_address=req.nominated_driver_address,
        status="OPEN",
    )
    violation.status = "DISPUTED"
    db.add(dispute)
    db.commit()
    db.refresh(dispute)
    return {
        "dispute_id": dispute.id,
        "case_number": violation.case_number,
        "violation_status": violation.status,
        "dispute_status": dispute.status,
    }


@router.post("/public/disputes/pay")
def settle_violation_penalty(
    req: DisputePayRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> dict:
    """Settle Vertragsstrafe directly and purge encrypted KBA keeper PII upon closure."""
    violation, sess = _lookup_verified_case(db, req.case_number, req.plate_raw)
    if violation.status in {"PAID", "CANCELLED"}:
        raise HTTPException(status_code=409, detail="Violation case already settled")

    now = datetime.now(UTC)
    violation.status = "PAID"
    # Immediately wipe encrypted KBA keeper PII upon settlement
    violation.keeper_name_encrypted = None
    violation.keeper_address_encrypted = None
    sess.paid_cents += violation.penalty_cents
    sess.paid_at = now
    purge_session_pii(db, storage, sess, purge_reason="VIOLATION_SETTLED", now=now)
    db.commit()
    return {
        "case_number": violation.case_number,
        "status": "PAID",
        "keeper_pii_purged": True,
    }


@router.get("/admin/disputes", dependencies=[Depends(require_admin_key)])
def list_admin_disputes(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Dispute).order_by(Dispute.created_at.desc()).limit(50)).all()
    out = []
    for d in rows:
        v = db.get(Violation, d.violation_id)
        sess = db.get(ParkingSession, v.session_id) if v else None
        out.append(
            {
                "id": d.id,
                "violation_id": d.violation_id,
                "case_number": v.case_number if v else "-",
                "plate_display": sess.plate_display if sess else None,
                "reason": d.reason,
                "explanation": d.explanation,
                "nominated_driver_name": d.nominated_driver_name,
                "nominated_driver_address": d.nominated_driver_address,
                "status": d.status,
                "created_at": d.created_at.isoformat(),
            }
        )
    return out


@router.post("/admin/disputes/{dispute_id}/resolve", dependencies=[Depends(require_admin_key)])
def resolve_dispute(
    dispute_id: str,
    req: AdminResolveDisputeRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> dict:
    dispute = db.get(Dispute, dispute_id)
    if dispute is None:
        raise HTTPException(status_code=404, detail="Dispute not found")
    violation = db.get(Violation, dispute.violation_id)
    if violation is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    sess = db.get(ParkingSession, violation.session_id)

    now = datetime.now(UTC)
    if req.decision == "ACCEPT_CANCEL":
        dispute.status = "ACCEPTED"
        violation.status = "CANCELLED"
        violation.keeper_name_encrypted = None
        violation.keeper_address_encrypted = None
        if sess is not None and sess.pii_purged_at is None:
            purge_session_pii(db, storage, sess, purge_reason="DISPUTE_ACCEPTED", now=now)
    else:
        dispute.status = "REJECTED"
        violation.status = "NOTICE_SENT"

    db.commit()
    return {
        "dispute_id": dispute.id,
        "dispute_status": dispute.status,
        "violation_status": violation.status,
    }
