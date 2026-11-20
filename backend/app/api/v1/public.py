import uuid
from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.payments.base import PaymentProvider
from app.adapters.payments.factory import get_payment_provider
from app.adapters.storage.base import ObjectStorageAdapter
from app.adapters.storage.factory import get_storage_adapter
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.invoices import issue_invoice_for_payment
from app.domain.plates_de import mask_plate_for_public, parse_plate
from app.domain.tariffs import calculate_tariff, split_german_vat
from app.models.entities import Invoice, Organization, ParkingSession, Payment, Site, TariffPlan
from app.models.schemas import (
    CheckoutRequest,
    CheckoutResponse,
    MockConfirmRequest,
    PaymentSettledResponse,
    SessionLookupResponse,
    SitePublicInfoResponse,
    TariffBreakdownDTO,
)

router = APIRouter(prefix="/public", tags=["Driver Public Checkout"])


def _settle_payment(
    db: Session,
    storage: ObjectStorageAdapter,
    *,
    payment: Payment,
    method: str | None = None,
) -> PaymentSettledResponse:
    now = datetime.now(UTC)
    session = db.get(ParkingSession, payment.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Parking session not found")
    site = db.get(Site, session.site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    org = db.get(Organization, site.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    if payment.status != "SUCCEEDED":
        payment.status = "SUCCEEDED"
        payment.settled_at = now
        if method:
            payment.method = method

        session.paid_cents += payment.gross_cents
        session.paid_at = now
        # If driver paid while still ACTIVE (pre-exit at kiosk/QR) or AWAITING_PAYMENT (PayLater)
        if session.exit_at is not None and session.paid_cents >= session.calculated_fee_cents:
            session.status = "PAID"
        elif session.exit_at is None and session.paid_cents >= session.calculated_fee_cents:
            session.status = "PAID"

    invoice = issue_invoice_for_payment(
        db,
        storage,
        payment=payment,
        session=session,
        site=site,
        org=org,
    )
    db.commit()
    return PaymentSettledResponse(
        payment_id=payment.id,
        session_id=session.id,
        status=payment.status,
        invoice_number=invoice.invoice_number,
        invoice_pdf_url=f"/api/v1/public/invoices/{invoice.invoice_number}/pdf",
        gross_cents=payment.gross_cents,
        net_cents=payment.net_cents,
        vat_cents=payment.vat_cents,
        currency=payment.currency,
    )


@router.get("/sites/{site_code}/info", response_model=SitePublicInfoResponse)
def get_site_public_info(site_code: str, db: Session = Depends(get_db)) -> SitePublicInfoResponse:
    site = db.scalars(select(Site).where(Site.site_code == site_code, Site.is_active.is_(True))).first()
    if site is None:
        raise HTTPException(status_code=404, detail="Site not found")
    plan = db.scalars(
        select(TariffPlan).where(TariffPlan.site_id == site.id, TariffPlan.is_active.is_(True))
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Active tariff not found")
    return SitePublicInfoResponse(
        site_code=site.site_code,
        name=site.name,
        address=site.address,
        privacy_notice_url=site.privacy_notice_url,
        weekday_free_minutes=plan.weekday_free_minutes,
        weekend_all_day_free=plan.weekend_all_day_free,
        drive_through_grace_minutes=site.drive_through_grace_minutes,
        pay_later_grace_hours=site.pay_later_grace_hours,
        hourly_tiers_cents=plan.hourly_tiers_cents,
        daily_max_cents=plan.daily_max_cents,
        vat_rate_percent=plan.vat_rate_bps / 100.0,
    )


@router.get("/sessions/lookup", response_model=SessionLookupResponse)
def lookup_session_by_plate(
    plate: str = Query(..., min_length=2, max_length=40),
    site_code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SessionLookupResponse:
    """
    Privacy-safe driver QR lookup:
    Returns ONLY the single most recent active/payable/recently-paid session for the entered plate.
    Never exposes historical trips or camera photos.
    """
    parsed = parse_plate(plate)
    stmt = (
        select(ParkingSession)
        .where(
            ParkingSession.plate_normalized == parsed.normalized,
            ParkingSession.status.in_(["ACTIVE", "AWAITING_PAYMENT", "COMPLETED_FREE", "PAID"]),
        )
        .order_by(ParkingSession.entry_at.desc())
    )
    if site_code:
        site_obj = db.scalars(select(Site).where(Site.site_code == site_code)).first()
        if site_obj is None:
            return SessionLookupResponse(found=False)
        stmt = stmt.where(ParkingSession.site_id == site_obj.id)

    session = db.scalars(stmt).first()
    if session is None:
        return SessionLookupResponse(found=False)

    site = db.get(Site, session.site_id)
    plan = db.get(TariffPlan, session.tariff_plan_id)
    if site is None or plan is None:
        return SessionLookupResponse(found=False)

    eval_exit = session.exit_at or datetime.now(UTC)
    tariff = calculate_tariff(
        entry_at=session.entry_at,
        exit_at=eval_exit,
        site=site,
        plan=plan,
        is_whitelisted=session.is_whitelisted,
        validated_minutes=session.validated_minutes,
        validated_full_free=session.validated_full_free,
    )
    amount_due = max(0, tariff.gross_cents - session.paid_cents)

    # Check if an invoice already exists for this session
    inv_num: str | None = None
    paid_payment = db.scalars(
        select(Payment)
        .where(Payment.session_id == session.id, Payment.status == "SUCCEEDED")
        .order_by(Payment.settled_at.desc())
    ).first()
    if paid_payment is not None:
        inv = db.scalars(select(Invoice).where(Invoice.payment_id == paid_payment.id)).first()
        if inv is not None:
            inv_num = inv.invoice_number

    disp = session.plate_display or parsed.display
    return SessionLookupResponse(
        found=True,
        session_id=session.id,
        site_code=site.site_code,
        site_name=site.name,
        plate_masked=mask_plate_for_public(disp),
        plate_display=disp,
        plate_country=session.plate_country,
        status=session.status,
        entry_at=session.entry_at,
        exit_at=session.exit_at,
        pay_later_deadline_at=session.pay_later_deadline_at,
        amount_due_cents=amount_due,
        paid_cents=session.paid_cents,
        currency=plan.currency,
        invoice_number=inv_num,
        breakdown=TariffBreakdownDTO(
            duration_minutes=tariff.duration_minutes,
            drive_through_free=tariff.drive_through_free,
            is_whitelisted=tariff.is_whitelisted,
            free_minutes_applied=tariff.free_minutes_applied,
            validated_minutes_applied=tariff.validated_minutes_applied,
            billable_minutes=tariff.billable_minutes,
            billable_hours=tariff.billable_hours,
            gross_cents=tariff.gross_cents,
            net_cents=tariff.net_cents,
            vat_cents=tariff.vat_cents,
            vat_rate_percent=tariff.vat_rate_percent,
            currency=tariff.currency,
            reason_code=tariff.reason_code,
        ),
    )


@router.post("/payments/checkout", response_model=CheckoutResponse)
def create_payment_checkout(
    req: CheckoutRequest,
    db: Session = Depends(get_db),
    provider: PaymentProvider = Depends(get_payment_provider),
) -> CheckoutResponse:
    session = db.get(ParkingSession, req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status == "PURGED":
        raise HTTPException(status_code=409, detail="Session already settled and purged")

    site = db.get(Site, session.site_id)
    plan = db.get(TariffPlan, session.tariff_plan_id)
    if site is None or plan is None:
        raise HTTPException(status_code=404, detail="Site or tariff not found")

    eval_exit = session.exit_at or datetime.now(UTC)
    tariff = calculate_tariff(
        entry_at=session.entry_at,
        exit_at=eval_exit,
        site=site,
        plan=plan,
        is_whitelisted=session.is_whitelisted,
        validated_minutes=session.validated_minutes,
        validated_full_free=session.validated_full_free,
    )
    session.duration_minutes = tariff.duration_minutes
    session.calculated_fee_cents = tariff.gross_cents

    amount_due = max(0, tariff.gross_cents - session.paid_cents)
    if amount_due <= 0:
        raise HTTPException(status_code=400, detail="No balance due for this parking session")

    net_cents, vat_cents = split_german_vat(amount_due, plan.vat_rate_bps)
    payment_id = str(uuid.uuid4())
    settings = get_settings()
    desc = (
        f"Parkgebuehr {site.name}" if req.locale == "de" else f"Parking Fee {site.name}"
    )

    checkout = provider.create_checkout(
        payment_id=payment_id,
        session_id=session.id,
        amount_cents=amount_due,
        currency=plan.currency,
        description=desc,
        success_url=f"{settings.frontend_base_url}/{req.locale}/pay?success=1&session_id={session.id}",
        cancel_url=f"{settings.frontend_base_url}/{req.locale}/pay?cancelled=1",
        locale=req.locale,
    )

    payment = Payment(
        id=payment_id,
        session_id=session.id,
        provider=checkout.provider,
        provider_ref=checkout.provider_ref,
        method=req.payment_method,
        status="PENDING",
        gross_cents=amount_due,
        net_cents=net_cents,
        vat_cents=vat_cents,
        vat_rate_bps=plan.vat_rate_bps,
        currency=plan.currency,
        locale=req.locale,
    )
    db.add(payment)
    db.commit()

    return CheckoutResponse(
        payment_id=payment.id,
        provider=checkout.provider,
        provider_ref=checkout.provider_ref,
        checkout_url=checkout.checkout_url,
        gross_cents=amount_due,
        net_cents=net_cents,
        vat_cents=vat_cents,
        currency=plan.currency,
        requires_mock_confirm=checkout.requires_mock_confirm,
    )


@router.post("/payments/mock-confirm", response_model=PaymentSettledResponse)
def confirm_mock_payment(
    req: MockConfirmRequest,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> PaymentSettledResponse:
    """Confirm a Mock checkout session in development/demo environments."""
    payment = db.get(Payment, req.payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.provider != "mock":
        raise HTTPException(status_code=400, detail="Only mock payments can be confirmed via this endpoint")
    return _settle_payment(db, storage, payment=payment, method=req.method)


@router.post("/payments/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> dict[str, str]:
    settings = get_settings()
    raw_body = await request.body()
    if not settings.stripe_webhook_secret:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe webhook secret not configured")

    try:
        event = stripe.Webhook.construct_event(
            payload=raw_body,
            sig_header=stripe_signature or "",
            secret=settings.stripe_webhook_secret,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Stripe signature: {exc}") from exc

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        provider_ref = obj.get("id")
        payment = db.scalars(select(Payment).where(Payment.provider_ref == provider_ref)).first()
        if payment is not None:
            _settle_payment(db, storage, payment=payment, method="STRIPE")

    return {"received": "true"}


@router.get("/invoices/{invoice_number}/pdf")
def download_invoice_pdf(
    invoice_number: str,
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> Response:
    invoice = db.scalars(select(Invoice).where(Invoice.invoice_number == invoice_number)).first()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pdf_bytes = storage.get_bytes(invoice.pdf_s3_key)
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="Invoice PDF missing in storage")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"'},
    )
