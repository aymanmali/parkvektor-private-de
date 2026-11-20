from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.kba.providers import BatchCSVKBAProvider, KeeperLookupRequest
from app.adapters.storage.base import ObjectStorageAdapter
from app.adapters.storage.factory import get_storage_adapter
from app.api.v1.deps import require_admin_key
from app.core.config import get_settings
from app.core.crypto import decrypt_pii
from app.db.session import get_db
from app.domain.violations import (
    escalate_overdue_sessions,
    execute_kba_lookup,
    render_violation_notice_pdf,
    review_violation_qa,
)
from app.models.entities import Organization, ParkingSession, Site, Violation

router = APIRouter(
    prefix="/admin/violations",
    tags=["Violations, QA & KBA § 39 StVG"],
    dependencies=[Depends(require_admin_key)],
)


class QAReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    reviewer: str = Field(default="Operator QA", min_length=2, max_length=120)
    notes: str | None = None


class KBALookupTriggerRequest(BaseModel):
    provider: str = Field(default="mock_kba", pattern="^(mock_kba|batch_csv_kba)$")


class ViolationAdminDTO(BaseModel):
    id: str
    case_number: str
    session_id: str
    site_name: str
    plate_display: str | None
    plate_country: str
    entry_at: datetime | None
    exit_at: datetime | None
    duration_minutes: int
    unpaid_fee_cents: int
    penalty_cents: int
    status: str
    kba_provider: str | None
    kba_request_ref: str | None
    keeper_name: str | None
    qa_reviewer: str | None
    qa_reviewed_at: datetime | None
    qa_notes: str | None
    created_at: datetime


def _to_dto(db: Session, v: Violation) -> ViolationAdminDTO:
    sess = db.get(ParkingSession, v.session_id)
    site = db.get(Site, sess.site_id) if sess else None
    keeper_name = None
    if v.keeper_name_encrypted:
        try:
            keeper_name = decrypt_pii(v.keeper_name_encrypted, get_settings().admin_api_key)
        except Exception:
            keeper_name = "[encrypted]"
    return ViolationAdminDTO(
        id=v.id,
        case_number=v.case_number,
        session_id=v.session_id,
        site_name=site.name if site else "Unknown",
        plate_display=sess.plate_display if sess else None,
        plate_country=sess.plate_country if sess else "DE",
        entry_at=sess.entry_at if sess else None,
        exit_at=sess.exit_at if sess else None,
        duration_minutes=sess.duration_minutes if sess else 0,
        unpaid_fee_cents=max(0, (sess.calculated_fee_cents - sess.paid_cents)) if sess else 0,
        penalty_cents=v.penalty_cents,
        status=v.status,
        kba_provider=v.kba_provider,
        kba_request_ref=v.kba_request_ref,
        keeper_name=keeper_name,
        qa_reviewer=v.qa_reviewer,
        qa_reviewed_at=v.qa_reviewed_at,
        qa_notes=v.qa_notes,
        created_at=v.created_at,
    )


@router.get("", response_model=list[ViolationAdminDTO])
def list_violations(
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[ViolationAdminDTO]:
    stmt = select(Violation).order_by(Violation.created_at.desc()).limit(100)
    if status_filter:
        stmt = stmt.where(Violation.status == status_filter)
    rows = db.scalars(stmt).all()
    return [_to_dto(db, v) for v in rows]


@router.post("/escalate-overdue")
def trigger_overdue_escalation(db: Session = Depends(get_db)) -> dict:
    summary = escalate_overdue_sessions(db)
    return {
        "escalated_count": summary.escalated_count,
        "case_numbers": summary.case_numbers,
    }


@router.post("/{violation_id}/qa", response_model=ViolationAdminDTO)
def qa_review_violation(
    violation_id: str,
    req: QAReviewRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> ViolationAdminDTO:
    v = db.get(Violation, violation_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    try:
        updated = review_violation_qa(
            db,
            storage,
            violation=v,
            decision=req.decision,
            reviewer=req.reviewer,
            notes=req.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_dto(db, updated)


@router.post("/{violation_id}/kba-lookup", response_model=ViolationAdminDTO)
def trigger_kba_lookup(
    violation_id: str,
    req: KBALookupTriggerRequest,
    db: Session = Depends(get_db),
) -> ViolationAdminDTO:
    v = db.get(Violation, violation_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    try:
        updated = execute_kba_lookup(db, violation=v, provider_name=req.provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_dto(db, updated)


@router.get("/kba-batch.csv")
def export_kba_csv_batch(db: Session = Depends(get_db)) -> Response:
    """Export all APPROVED / KBA_REQUESTED violations as German § 39 StVG CSV for licensed bureaus."""
    rows = db.scalars(
        select(Violation).where(Violation.status.in_(["APPROVED", "KBA_REQUESTED"]))
    ).all()
    requests: list[KeeperLookupRequest] = []
    for v in rows:
        sess = db.get(ParkingSession, v.session_id)
        if sess is None or not sess.plate_normalized:
            continue
        site = db.get(Site, sess.site_id)
        requests.append(
            KeeperLookupRequest(
                case_number=v.case_number,
                plate_normalized=sess.plate_normalized,
                plate_country=sess.plate_country,
                incident_timestamp=sess.entry_at if sess.entry_at.tzinfo else sess.entry_at.replace(tzinfo=UTC),
                site_name=site.name if site else "ParkVektor DE",
            )
        )
    csv_text = BatchCSVKBAProvider.build_csv_batch(requests)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="kba_stvg39_batch.csv"'},
    )


@router.get("/{violation_id}/notice.pdf")
def download_violation_notice_pdf(violation_id: str, db: Session = Depends(get_db)) -> Response:
    v = db.get(Violation, violation_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Violation not found")
    sess = db.get(ParkingSession, v.session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="Session not found")
    site = db.get(Site, sess.site_id)
    org = db.get(Organization, site.organization_id) if site else None
    if site is None or org is None:
        raise HTTPException(status_code=404, detail="Site or organization not found")

    pdf_bytes = render_violation_notice_pdf(violation=v, session=sess, site=site, org=org)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{v.case_number}.pdf"'},
    )
