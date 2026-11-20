from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.domain.matcher import process_camera_pass
from app.domain.violations import escalate_overdue_sessions, execute_kba_lookup, review_violation_qa
from app.models.entities import (
    AutoPayVehicle,
    DriverAccount,
    Lane,
    MerchantAccount,
    Organization,
    Site,
    TariffPlan,
    Violation,
    Whitelist,
)


def _last_weekday_morning(now: datetime) -> datetime:
    """Return a guaranteed weekday (Mon-Fri) 08:30 UTC timestamp within the last 3 days."""
    candidate = now.replace(hour=8, minute=30, second=0, microsecond=0)
    if candidate > now - timedelta(hours=6):
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:  # skip Sat/Sun
        candidate -= timedelta(days=1)
    return candidate


def seed_demo_data(db: Session) -> dict[str, str]:
    """Idempotently seed a German barrierless mall demo garage in Musterstadt."""
    existing = db.scalars(select(Site).where(Site.site_code == "DE-DEMO-01")).first()
    if existing is not None:
        return {"status": "already_seeded", "site_code": existing.site_code}

    settings = get_settings()
    now = datetime.now(UTC)

    org = Organization(
        legal_name="ParkVektor Muster-Betrieb GmbH (Demo)",
        street_address="Musterstraße 10",
        postal_code="80000",
        city="Musterstadt",
        country="DE",
        vat_id="DE349812745",
        tax_number="143/168/20419",
        dpo_email="datenschutz@parkvektor-de.example",
        support_email="support@parkvektor-de.example",
    )
    db.add(org)
    db.flush()

    site = Site(
        organization_id=org.id,
        site_code="DE-DEMO-01",
        name="Süd-Galerie Muster-Parkhaus (Demo)",
        address="Galerieplatz 1, 80000 Musterstadt",
        timezone="Europe/Berlin",
        total_spaces=320,
        privacy_notice_url="https://parkvektor-de.example/datenschutz/de-demo-01",
        compliant_purge_hours=24,
        paid_purge_hours=24,
        pay_later_grace_hours=48,
        drive_through_grace_minutes=15,
    )
    db.add(site)
    db.flush()

    tariff = TariffPlan(
        site_id=site.id,
        name="Mall Premium Tarif (4h Mo-Fr frei, Wochenende frei)",
        currency="EUR",
        vat_rate_bps=1900,
        weekday_free_minutes=240,       # 4 hours free Mon-Fri (barrierless mall tariff)
        weekend_all_day_free=True,      # Sat-Sun all day free
        weekend_free_minutes=1440,
        hourly_tiers_cents=[300, 400, 500],  # 5th hr €3, 6th hr €4, €5/hr after
        daily_max_cents=2500,           # €25/day cap
        violation_penalty_cents=3500,   # €35 Vertragsstrafe
    )
    db.add(tariff)

    entry_lane = Lane(
        site_id=site.id,
        lane_code="DE-DEMO-01-IN-1",
        name="Einfahrt Nord (Edge AI)",
        direction="ENTRY",
        capture_mode="EDGE_RTSP",
        camera_vendor="edge_ai",
        requires_server_redaction=False,
        hmac_secret=settings.default_edge_hmac_secret,
        last_heartbeat_at=now,
    )
    exit_lane = Lane(
        site_id=site.id,
        lane_code="DE-DEMO-01-OUT-1",
        name="Ausfahrt Süd (Axis Smart ANPR)",
        direction="EXIT",
        capture_mode="SMART_WEBHOOK",
        camera_vendor="axis",
        requires_server_redaction=True,
        hmac_secret=settings.default_edge_hmac_secret,
        last_heartbeat_at=now,
    )
    db.add_all([entry_lane, exit_lane])

    wl = Whitelist(
        site_id=site.id,
        plate_normalized="HHAB12H",
        label="Center-Management Dauerparker",
        valid_from=now - timedelta(days=30),
    )
    merchant = MerchantAccount(
        site_id=site.id,
        name="Kino-Welt Muster-Multiplex (Demo)",
        default_bonus_minutes=120,
        api_token="demo-merchant-kinowelt-token",
    )
    db.add_all([wl, merchant])
    db.commit()

    # Seed realistic live demo sessions across key operational states
    weekday_start = _last_weekday_morning(now)

    # 1. Payable PayLater session (5h 35m weekday => 4h free + 2 billable hrs = €7.00 incl. 19% MwSt.)
    process_camera_pass(
        db,
        site=site,
        lane=entry_lane,
        idempotency_key="seed-mpf-in",
        direction="ENTRY",
        plate_raw="M-PV 2026E",
        ocr_confidence=0.99,
        captured_at=weekday_start,
        vendor="edge_ai",
    )
    process_camera_pass(
        db,
        site=site,
        lane=exit_lane,
        idempotency_key="seed-mpf-out",
        direction="EXIT",
        plate_raw="M-PV 2026E",
        ocr_confidence=0.98,
        captured_at=weekday_start + timedelta(hours=5, minutes=35),
        vendor="axis",
    )

    # 2. Currently parked ACTIVE vehicle inside the mall (entered 75 min ago)
    process_camera_pass(
        db,
        site=site,
        lane=entry_lane,
        idempotency_key="seed-bxy-in",
        direction="ENTRY",
        plate_raw="B-XY 420",
        ocr_confidence=0.97,
        captured_at=now - timedelta(minutes=75),
        vendor="edge_ai",
    )

    # 3. Compliant free exit (stayed 2h 10m weekday => €0, ready for DSGVO Auto-Purge)
    # Uses real German umlaut Unterscheidungszeichen: GÖ (Göttingen)
    process_camera_pass(
        db,
        site=site,
        lane=entry_lane,
        idempotency_key="seed-free-in",
        direction="ENTRY",
        plate_raw="GÖ-AB 901",
        ocr_confidence=0.96,
        captured_at=now - timedelta(hours=28),
        vendor="edge_ai",
    )
    process_camera_pass(
        db,
        site=site,
        lane=exit_lane,
        idempotency_key="seed-free-out",
        direction="EXIT",
        plate_raw="GÖ-AB 901",
        ocr_confidence=0.96,
        captured_at=now - timedelta(hours=25, minutes=50),
        vendor="axis",
    )

    # 4. OCR Fuzzy Reconciliation pair (Entry: K-DO 881 -> Exit misread as K-D0 881)
    process_camera_pass(
        db,
        site=site,
        lane=entry_lane,
        idempotency_key="seed-fuzzy-in",
        direction="ENTRY",
        plate_raw="K-DO 881",
        ocr_confidence=0.95,
        captured_at=weekday_start + timedelta(minutes=15),
        vendor="edge_ai",
    )
    process_camera_pass(
        db,
        site=site,
        lane=exit_lane,
        idempotency_key="seed-fuzzy-out",
        direction="EXIT",
        plate_raw="K-D0 881",
        ocr_confidence=0.79,
        captured_at=weekday_start + timedelta(hours=5, minutes=10),
        vendor="axis",
    )

    # 5. Pre-enrolled AutoPay driver & vehicle (M-AP 100E) for frictionless drive-out demo
    demo_driver = DriverAccount(
        email="demo-driver@parkvektor-de.example",
        stripe_customer_id="cus_mock_demo001",
        consent_accepted_at=now - timedelta(days=5),
    )
    db.add(demo_driver)
    db.flush()
    db.add(
        AutoPayVehicle(
            driver_account_id=demo_driver.id,
            plate_normalized="MAP100E",
            is_active=True,
        )
    )
    db.commit()

    # 6. Overdue unpaid stay (>48h past exit) -> escalates into QA_QUEUE (N-OV 404)
    old_weekday = weekday_start - timedelta(days=7)
    while old_weekday.weekday() >= 5:
        old_weekday -= timedelta(days=1)

    process_camera_pass(
        db,
        site=site,
        lane=entry_lane,
        idempotency_key="seed-overdue-qa-in",
        direction="ENTRY",
        plate_raw="N-OV 404",
        ocr_confidence=0.96,
        captured_at=old_weekday,
        vendor="edge_ai",
    )
    process_camera_pass(
        db,
        site=site,
        lane=exit_lane,
        idempotency_key="seed-overdue-qa-out",
        direction="EXIT",
        plate_raw="N-OV 404",
        ocr_confidence=0.97,
        captured_at=old_weekday + timedelta(hours=6, minutes=10),
        vendor="axis",
    )

    # 7. Overdue violation already QA-approved + KBA resolved -> NOTICE_SENT for Widerspruchsportal demo (F-WD 999)
    process_camera_pass(
        db,
        site=site,
        lane=entry_lane,
        idempotency_key="seed-notice-in",
        direction="ENTRY",
        plate_raw="F-WD 999",
        ocr_confidence=0.98,
        captured_at=old_weekday + timedelta(minutes=30),
        vendor="edge_ai",
    )
    out_notice = process_camera_pass(
        db,
        site=site,
        lane=exit_lane,
        idempotency_key="seed-notice-out",
        direction="EXIT",
        plate_raw="F-WD 999",
        ocr_confidence=0.98,
        captured_at=old_weekday + timedelta(hours=5, minutes=45),
        vendor="axis",
    )

    escalate_overdue_sessions(db)
    if out_notice.session is not None:
        v_notice = db.scalars(
            select(Violation).where(Violation.session_id == out_notice.session.id)
        ).first()
        if v_notice is not None:
            from app.adapters.storage.factory import get_storage_adapter

            review_violation_qa(
                db,
                get_storage_adapter(),
                violation=v_notice,
                decision="APPROVE",
                reviewer="Seed QA",
                notes="Klar lesbares Kennzeichen",
            )
            execute_kba_lookup(db, violation=v_notice, provider_name="mock_kba")

    return {"status": "seeded", "site_code": site.site_code}


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        result = seed_demo_data(db)
        print(f"[ParkVektor Seed] {result}")


if __name__ == "__main__":
    main()
