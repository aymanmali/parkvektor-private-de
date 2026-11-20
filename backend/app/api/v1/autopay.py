import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.plates_de import parse_plate
from app.models.entities import AutoPayVehicle, DriverAccount, Invoice, Payment

router = APIRouter(prefix="/autopay", tags=["Driver AutoPay Wallet"])


class AutoPayRegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=200)
    plate_raw: str = Field(min_length=2, max_length=40)
    dsgvo_consent_accepted: bool


class AutoPayVehicleDTO(BaseModel):
    id: str
    plate_normalized: str
    is_active: bool
    created_at: datetime


class AutoPayAccountResponse(BaseModel):
    driver_id: str
    email: str
    stripe_customer_id: str | None
    consent_accepted_at: datetime
    vehicles: list[AutoPayVehicleDTO]
    recent_invoices: list[dict]


@router.post("/register", response_model=AutoPayAccountResponse, status_code=201)
def register_autopay_vehicle(
    req: AutoPayRegisterRequest,
    db: Session = Depends(get_db),
) -> AutoPayAccountResponse:
    if not req.dsgvo_consent_accepted:
        raise HTTPException(
            status_code=400,
            detail="Explicit DSGVO Art. 6(1)(a)/(b) consent is required to enroll in AutoPay",
        )
    email = req.email.strip().lower()
    parsed = parse_plate(req.plate_raw)
    if not parsed.valid:
        raise HTTPException(status_code=400, detail="Invalid German/EU license plate format")

    driver = db.scalars(select(DriverAccount).where(DriverAccount.email == email)).first()
    if driver is None:
        driver = DriverAccount(
            email=email,
            stripe_customer_id=f"cus_mock_{uuid.uuid4().hex[:12]}",
            consent_accepted_at=datetime.now(UTC),
        )
        db.add(driver)
        db.flush()

    existing_vehicle = db.scalars(
        select(AutoPayVehicle).where(AutoPayVehicle.plate_normalized == parsed.normalized)
    ).first()
    if existing_vehicle is not None:
        if existing_vehicle.driver_account_id != driver.id and existing_vehicle.is_active:
            raise HTTPException(
                status_code=409,
                detail="This license plate is already actively enrolled under another AutoPay account",
            )
        existing_vehicle.driver_account_id = driver.id
        existing_vehicle.is_active = True
    else:
        db.add(
            AutoPayVehicle(
                driver_account_id=driver.id,
                plate_normalized=parsed.normalized,
                is_active=True,
            )
        )

    db.commit()
    return _build_account_response(db, driver)


@router.get("/account", response_model=AutoPayAccountResponse)
def get_autopay_account(
    email: str = Query(..., min_length=5, max_length=200),
    db: Session = Depends(get_db),
) -> AutoPayAccountResponse:
    driver = db.scalars(select(DriverAccount).where(DriverAccount.email == email.strip().lower())).first()
    if driver is None:
        raise HTTPException(status_code=404, detail="AutoPay account not found")
    return _build_account_response(db, driver)


@router.delete("/vehicles/{vehicle_id}")
def unlink_autopay_vehicle(vehicle_id: str, db: Session = Depends(get_db)) -> dict[str, str]:
    vehicle = db.get(AutoPayVehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="AutoPay vehicle not found")
    db.delete(vehicle)
    db.commit()
    return {"status": "removed", "vehicle_id": vehicle_id}


def _build_account_response(db: Session, driver: DriverAccount) -> AutoPayAccountResponse:
    vehicles = db.scalars(
        select(AutoPayVehicle)
        .where(AutoPayVehicle.driver_account_id == driver.id, AutoPayVehicle.is_active.is_(True))
        .order_by(AutoPayVehicle.created_at.desc())
    ).all()

    payments = db.scalars(
        select(Payment)
        .where(Payment.driver_account_id == driver.id, Payment.status == "SUCCEEDED")
        .order_by(Payment.settled_at.desc())
        .limit(10)
    ).all()
    recent_invoices: list[dict] = []
    for p in payments:
        inv = db.scalars(select(Invoice).where(Invoice.payment_id == p.id)).first()
        if inv is not None:
            recent_invoices.append(
                {
                    "invoice_number": inv.invoice_number,
                    "site_name": inv.site_name_snapshot,
                    "gross_cents": inv.gross_cents,
                    "issued_at": inv.issued_at.isoformat(),
                    "pdf_url": f"/api/v1/public/invoices/{inv.invoice_number}/pdf",
                }
            )

    return AutoPayAccountResponse(
        driver_id=driver.id,
        email=driver.email,
        stripe_customer_id=driver.stripe_customer_id,
        consent_accepted_at=driver.consent_accepted_at,
        vehicles=[
            AutoPayVehicleDTO(
                id=v.id,
                plate_normalized=v.plate_normalized,
                is_active=v.is_active,
                created_at=v.created_at,
            )
            for v in vehicles
        ],
        recent_invoices=recent_invoices,
    )
