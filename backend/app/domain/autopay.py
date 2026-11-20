import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.storage.base import ObjectStorageAdapter
from app.domain.invoices import issue_invoice_for_payment
from app.domain.tariffs import split_german_vat
from app.models.entities import (
    AutoPayVehicle,
    DriverAccount,
    Organization,
    ParkingSession,
    Payment,
    Site,
    TariffPlan,
)


def try_autopay_settle_on_exit(
    db: Session,
    storage: ObjectStorageAdapter | None,
    *,
    session: ParkingSession,
    site: Site,
    plan: TariffPlan,
    gross_cents: int,
) -> Payment | None:
    """
    Frictionless Drive-Out AutoPay hook:
    If the exiting vehicle's plate is enrolled in an active DriverAccount AutoPay wallet,
    automatically charges the balance, settles the session to PAID, and issues the decoupled
    German 19% MwSt. PDF invoice with zero manual driver interaction.
    """
    if gross_cents <= 0 or not session.plate_normalized:
        return None

    vehicle = db.scalars(
        select(AutoPayVehicle).where(
            AutoPayVehicle.plate_normalized == session.plate_normalized,
            AutoPayVehicle.is_active.is_(True),
        )
    ).first()
    if vehicle is None:
        return None

    driver = db.get(DriverAccount, vehicle.driver_account_id)
    if driver is None:
        return None

    now = datetime.now(UTC)
    net_cents, vat_cents = split_german_vat(gross_cents, plan.vat_rate_bps)
    payment = Payment(
        id=str(uuid.uuid4()),
        session_id=session.id,
        driver_account_id=driver.id,
        provider="autopay_wallet",
        provider_ref=f"ap_{uuid.uuid4().hex[:16]}",
        method="AUTOPAY",
        status="SUCCEEDED",
        gross_cents=gross_cents,
        net_cents=net_cents,
        vat_cents=vat_cents,
        vat_rate_bps=plan.vat_rate_bps,
        currency=plan.currency,
        locale="de",
        settled_at=now,
    )
    db.add(payment)
    db.flush()

    session.paid_cents += gross_cents
    session.paid_at = now
    session.status = "PAID"

    if storage is not None:
        org = db.get(Organization, site.organization_id)
        if org is not None:
            issue_invoice_for_payment(
                db,
                storage,
                payment=payment,
                session=session,
                site=site,
                org=org,
            )

    return payment
