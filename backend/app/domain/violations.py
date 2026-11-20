from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.kba.providers import (
    BatchCSVKBAProvider,
    KeeperLookupRequest,
    MockKBAProvider,
)
from app.adapters.storage.base import ObjectStorageAdapter
from app.core.config import get_settings
from app.core.crypto import decrypt_pii, encrypt_pii
from app.domain.retention import purge_session_pii
from app.models.entities import Organization, ParkingSession, Site, TariffPlan, Violation


def _ensure_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _fmt_eur_de(cents: int) -> str:
    return f"{cents / 100.0:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_dt_de(dt: datetime | None, tz_name: str = "Europe/Berlin") -> str:
    if dt is None:
        return "-"
    local = _ensure_utc(dt).astimezone(ZoneInfo(tz_name))
    return local.strftime("%d.%m.%Y %H:%M")


def next_case_number(db: Session, year: int) -> str:
    prefix = f"VF-{year}-"
    count = db.scalar(select(func.count(Violation.id)).where(Violation.case_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:06d}"


@dataclass(frozen=True)
class EscalationSummary:
    escalated_count: int
    case_numbers: list[str]


def escalate_overdue_sessions(
    db: Session,
    *,
    now: datetime | None = None,
) -> EscalationSummary:
    """
    Scan AWAITING_PAYMENT sessions whose PayLater grace window has expired
    and place them into the Human QA Violation Review Queue (QA_QUEUE).
    No fine is ever mailed without human QA confirmation!
    """
    run_time = _ensure_utc(now or datetime.now(UTC))
    candidates = db.scalars(
        select(ParkingSession).where(
            ParkingSession.status == "AWAITING_PAYMENT",
            ParkingSession.pay_later_deadline_at.is_not(None),
        )
    ).all()

    created_cases: list[str] = []
    for sess in candidates:
        deadline = _ensure_utc(sess.pay_later_deadline_at)  # type: ignore[arg-type]
        if run_time < deadline:
            continue

        existing = db.scalars(select(Violation).where(Violation.session_id == sess.id)).first()
        if existing is not None:
            continue

        plan = db.get(TariffPlan, sess.tariff_plan_id)
        penalty_cents = plan.violation_penalty_cents if plan else 3500
        case_no = next_case_number(db, run_time.year)

        violation = Violation(
            case_number=case_no,
            session_id=sess.id,
            status="QA_QUEUE",
            penalty_cents=penalty_cents,
        )
        sess.status = "VIOLATION_PENDING"
        db.add(violation)
        db.flush()
        created_cases.append(case_no)

    db.commit()
    return EscalationSummary(escalated_count=len(created_cases), case_numbers=created_cases)


def review_violation_qa(
    db: Session,
    storage: ObjectStorageAdapter,
    *,
    violation: Violation,
    decision: str,  # APPROVE | REJECT
    reviewer: str,
    notes: str | None = None,
) -> Violation:
    now = datetime.now(UTC)
    sess = db.get(ParkingSession, violation.session_id)
    if sess is None:
        raise ValueError("Linked parking session not found")

    violation.qa_reviewer = reviewer
    violation.qa_reviewed_at = now
    violation.qa_notes = notes

    if decision == "APPROVE":
        violation.status = "APPROVED"
        sess.status = "VIOLATION_CONFIRMED"
    elif decision == "REJECT":
        violation.status = "CANCELLED"
        violation.keeper_name_encrypted = None
        violation.keeper_address_encrypted = None
        # Immediate DSGVO hard-purge of false-positive / rejected violation
        purge_session_pii(db, storage, sess, purge_reason="QA_REJECTED", now=now)
    else:
        raise ValueError(f"Unsupported QA decision: {decision}")

    db.commit()
    db.refresh(violation)
    return violation


def execute_kba_lookup(
    db: Session,
    *,
    violation: Violation,
    provider_name: str = "mock_kba",  # mock_kba | batch_csv_kba
) -> Violation:
    """
    Execute or queue a § 39 Abs. 1 StVG keeper lookup against the German KBA (ZFZR)
    and encrypt keeper PII at rest before persistence.
    """
    if violation.status not in {"APPROVED", "KBA_REQUESTED"}:
        raise ValueError("KBA lookup requires QA-approved violation")

    sess = db.get(ParkingSession, violation.session_id)
    if sess is None or not sess.plate_normalized:
        raise ValueError("Session license plate missing or already purged")
    site = db.get(Site, sess.site_id)
    if site is None:
        raise ValueError("Site not found")

    req = KeeperLookupRequest(
        case_number=violation.case_number,
        plate_normalized=sess.plate_normalized,
        plate_country=sess.plate_country,
        incident_timestamp=_ensure_utc(sess.entry_at),
        site_name=site.name,
    )

    provider = BatchCSVKBAProvider() if provider_name == "batch_csv_kba" else MockKBAProvider()
    res = provider.request_keeper(req)

    secret = get_settings().admin_api_key
    violation.kba_provider = res.provider
    violation.kba_request_ref = res.request_ref

    if res.status == "RESOLVED" and res.keeper_name and res.keeper_address:
        violation.keeper_name_encrypted = encrypt_pii(res.keeper_name, secret)
        violation.keeper_address_encrypted = encrypt_pii(res.keeper_address, secret)
        violation.status = "NOTICE_SENT"
    else:
        violation.status = "KBA_REQUESTED"

    db.commit()
    db.refresh(violation)
    return violation


def render_violation_notice_pdf(
    *,
    violation: Violation,
    session: ParkingSession,
    site: Site,
    org: Organization,
) -> bytes:
    """Generate a German civil-law Vertragsstrafe notice (Zahlungsaufforderung) PDF."""
    settings = get_settings()
    keeper_name = (
        decrypt_pii(violation.keeper_name_encrypted, settings.admin_api_key)
        if violation.keeper_name_encrypted
        else "Fahrzeughalter/in (KBA-Auskunft ausstehend)"
    )
    keeper_addr = (
        decrypt_pii(violation.keeper_address_encrypted, settings.admin_api_key)
        if violation.keeper_address_encrypted
        else "-"
    )

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    nl = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Zahlungsaufforderung - Vertragsstrafe (Parknutzungsvertrag)", **nl)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(90, 95, 105)
    pdf.cell(0, 5.5, f"{org.legal_name} | {org.street_address}, {org.postal_code} {org.city} | USt-IdNr.: {org.vat_id}", **nl)
    pdf.ln(5)

    # Recipient block
    pdf.set_text_color(20, 25, 35)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(0, 6, keeper_name, **nl)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, keeper_addr, **nl)
    pdf.ln(6)

    # Case summary box
    pdf.set_fill_color(244, 246, 250)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(95, 8, f"Aktenzeichen: {violation.case_number}", fill=True)
    pdf.cell(95, 8, f"Kennzeichen: {session.plate_display or '-'}", fill=True, **nl)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 7, f"Standort: {site.name}", fill=True)
    pdf.cell(95, 7, f"Vertragsstrafe: {_fmt_eur_de(violation.penalty_cents)}", fill=True, **nl)
    pdf.ln(6)

    body = (
        f"Sehr geehrte Damen und Herren,\n\n"
        f"fuer das Fahrzeug mit dem amtlichen Kennzeichen {session.plate_display or '-'} wurde am Standort "
        f"{site.name} ({site.address}) ein Parkvorgang vom {_fmt_dt_de(session.entry_at, site.timezone)} "
        f"bis {_fmt_dt_de(session.exit_at, site.timezone)} ({session.duration_minutes} Minuten) erfasst. "
        f"Innerhalb der 48-stuendigen Kulanzfrist nach Ausfahrt wurde kein Zahlungseingang fuer die "
        f"offene Parkgebuehr ({_fmt_eur_de(session.calculated_fee_cents)}) festgestellt.\n\n"
        f"Gemaess unseren gut sichtbar an den Einfahrten ausgehaengten Einstellbedingungen (BGB Realofferte) "
        f"bitten wir um Ausgleich der Vertragsstrafe in Hoehe von {_fmt_eur_de(violation.penalty_cents)} "
        f"binnen 14 Tagen.\n\n"
        f"Online-Zahlung, Beleg-Upload oder Fahrerbenennung (BGH sekundaere Darlegungslast):\n"
        f"{settings.frontend_base_url}/de/dispute?case={violation.case_number}\n\n"
        f"Rechtsgrundlage der Halterermittlung: § 39 Abs. 1 StVG (KBA-Referenz: {violation.kba_request_ref or 'pending'}). "
        f"Datenschutzhinweise nach Art. 13/14 DSGVO: {site.privacy_notice_url} | DSB: {org.dpo_email}"
    )
    pdf.multi_cell(0, 5.5, body)
    return bytes(pdf.output())
