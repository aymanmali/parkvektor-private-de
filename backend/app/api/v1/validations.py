from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.plates_de import parse_plate
from app.domain.tariffs import calculate_tariff
from app.models.entities import (
    MerchantAccount,
    ParkingSession,
    SessionValidation,
    Site,
    TariffPlan,
)

router = APIRouter(prefix="/merchants", tags=["Mall Tenant Validations"])


class MerchantValidateRequest(BaseModel):
    plate_raw: str = Field(min_length=2, max_length=40)
    bonus_minutes: int | None = Field(default=None, ge=0, le=1440)
    full_free: bool = False
    voucher_code: str | None = Field(default=None, max_length=64)


class MerchantValidationResponse(BaseModel):
    validation_id: str
    merchant_name: str
    session_id: str
    plate_display: str
    bonus_minutes_applied: int
    full_free: bool
    previous_fee_cents: int
    new_fee_cents: int
    session_status: str


def _get_merchant(db: Session, token: str | None) -> MerchantAccount:
    if not token:
        raise HTTPException(status_code=401, detail="Missing X-Merchant-Token")
    merchant = db.scalars(
        select(MerchantAccount).where(
            MerchantAccount.api_token == token,
            MerchantAccount.is_active.is_(True),
        )
    ).first()
    if merchant is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive X-Merchant-Token")
    return merchant


@router.post("/validate", response_model=MerchantValidationResponse)
def apply_merchant_validation(
    req: MerchantValidateRequest,
    x_merchant_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MerchantValidationResponse:
    """
    Mall tenant validation endpoint (e.g. Kino-Welt Multiplex +2h free or VIP 100% free).
    Updates active or PayLater sessions live and recalculates fees immediately.
    """
    merchant = _get_merchant(db, x_merchant_token)
    parsed = parse_plate(req.plate_raw)

    session = db.scalars(
        select(ParkingSession)
        .where(
            ParkingSession.site_id == merchant.site_id,
            ParkingSession.plate_normalized == parsed.normalized,
            ParkingSession.status.in_(["ACTIVE", "AWAITING_PAYMENT"]),
        )
        .order_by(ParkingSession.entry_at.desc())
    ).first()
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="No active or payable parking session found for this plate at this site",
        )

    site = db.get(Site, session.site_id)
    plan = db.get(TariffPlan, session.tariff_plan_id)
    if site is None or plan is None:
        raise HTTPException(status_code=404, detail="Site or tariff plan missing")

    eval_exit = session.exit_at or datetime.now(UTC)
    before_tariff = calculate_tariff(
        entry_at=session.entry_at,
        exit_at=eval_exit,
        site=site,
        plan=plan,
        is_whitelisted=session.is_whitelisted,
        validated_minutes=session.validated_minutes,
        validated_full_free=session.validated_full_free,
    )

    bonus = merchant.default_bonus_minutes if req.bonus_minutes is None else req.bonus_minutes
    validation = SessionValidation(
        session_id=session.id,
        merchant_id=merchant.id,
        bonus_minutes=bonus,
        full_free=req.full_free,
        voucher_code=req.voucher_code,
    )
    db.add(validation)

    session.validated_minutes += bonus
    if req.full_free:
        session.validated_full_free = True

    after_tariff = calculate_tariff(
        entry_at=session.entry_at,
        exit_at=eval_exit,
        site=site,
        plan=plan,
        is_whitelisted=session.is_whitelisted,
        validated_minutes=session.validated_minutes,
        validated_full_free=session.validated_full_free,
    )
    session.calculated_fee_cents = after_tariff.gross_cents
    if session.exit_at is not None and after_tariff.gross_cents == 0 and session.status == "AWAITING_PAYMENT":
        session.status = "COMPLETED_FREE"

    db.commit()
    db.refresh(validation)

    return MerchantValidationResponse(
        validation_id=validation.id,
        merchant_name=merchant.name,
        session_id=session.id,
        plate_display=session.plate_display or parsed.display,
        bonus_minutes_applied=bonus,
        full_free=req.full_free,
        previous_fee_cents=before_tariff.gross_cents,
        new_fee_cents=after_tariff.gross_cents,
        session_status=session.status,
    )


@router.get("/recent")
def list_recent_validations(
    x_merchant_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    merchant = _get_merchant(db, x_merchant_token)
    rows = db.scalars(
        select(SessionValidation)
        .where(SessionValidation.merchant_id == merchant.id)
        .order_by(SessionValidation.created_at.desc())
        .limit(25)
    ).all()
    items = []
    for r in rows:
        sess = db.get(ParkingSession, r.session_id)
        items.append(
            {
                "id": r.id,
                "session_id": r.session_id,
                "plate_display": sess.plate_display if sess else None,
                "bonus_minutes": r.bonus_minutes,
                "full_free": r.full_free,
                "voucher_code": r.voucher_code,
                "created_at": r.created_at.isoformat(),
            }
        )
    return {
        "merchant_name": merchant.name,
        "default_bonus_minutes": merchant.default_bonus_minutes,
        "validations": items,
    }
