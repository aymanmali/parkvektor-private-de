from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.storage.base import ObjectStorageAdapter
from app.models.entities import Invoice, Organization, ParkingSession, Payment, Site


def _fmt_eur(cents: int, locale: str = "de") -> str:
    euros = cents / 100.0
    if locale == "de":
        return f"{euros:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"EUR {euros:,.2f}"


def _fmt_dt(dt: datetime | None, tz_name: str, locale: str) -> str:
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    local_dt = dt.astimezone(ZoneInfo(tz_name or "Europe/Berlin"))
    return local_dt.strftime("%d.%m.%Y %H:%M") if locale == "de" else local_dt.strftime("%Y-%m-%d %H:%M")


def next_invoice_number(db: Session, year: int) -> str:
    prefix = f"RE-{year}-"
    count = db.scalar(select(func.count(Invoice.id)).where(Invoice.invoice_number.like(f"{prefix}%"))) or 0
    return f"{prefix}{count + 1:06d}"


def render_invoice_pdf_bytes(
    *,
    invoice: Invoice,
    org: Organization,
    site: Site,
    payment: Payment,
    locale: str = "de",
) -> bytes:
    """
    Generate a clean German GoBD / § 14 UStG compliant PDF receipt/invoice.
    Contains NO camera photos or unnecessary personal tracking data so § 147 AO
    8-year retention never conflicts with DSGVO ANPR deletion.
    """
    is_de = locale != "en"
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    nl = {"new_x": XPos.LMARGIN, "new_y": YPos.NEXT}

    # Header
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "ParkVektor" + (" - Parkbeleg / Rechnung" if is_de else " - Parking Receipt / Invoice"), **nl)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 95, 105)
    pdf.cell(0, 6, f"{org.legal_name} | {org.street_address}, {org.postal_code} {org.city}, {org.country}", **nl)
    pdf.cell(0, 6, f"USt-IdNr.: {org.vat_id}" + (f" | St.-Nr.: {org.tax_number}" if org.tax_number else ""), **nl)
    pdf.ln(6)

    # Invoice metadata box
    pdf.set_text_color(20, 25, 35)
    pdf.set_fill_color(244, 246, 250)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(95, 8, ("Rechnungsnummer: " if is_de else "Invoice No.: ") + invoice.invoice_number, fill=True)
    pdf.cell(95, 8, ("Datum: " if is_de else "Issue Date: ") + _fmt_dt(invoice.issued_at, site.timezone, locale), fill=True, **nl)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(95, 7, ("Standort: " if is_de else "Parking Site: ") + invoice.site_name_snapshot, fill=True)
    pdf.cell(95, 7, ("Zahlungsart: " if is_de else "Payment Method: ") + payment.method, fill=True, **nl)
    pdf.ln(8)

    # Parking details
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, "Parkvorgang / Leistungszeitraum" if is_de else "Parking Session Details", **nl)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(60, 7, "Einfahrt:" if is_de else "Entry Time:")
    pdf.cell(0, 7, _fmt_dt(invoice.parking_entry_at, site.timezone, locale), **nl)
    pdf.cell(60, 7, "Ausfahrt / Abrechnung:" if is_de else "Exit / Billing Time:")
    pdf.cell(0, 7, _fmt_dt(invoice.parking_exit_at or invoice.issued_at, site.timezone, locale), **nl)
    pdf.cell(60, 7, "Parkdauer:" if is_de else "Total Duration:")
    hrs, mins = divmod(invoice.duration_minutes, 60)
    pdf.cell(0, 7, f"{hrs} Std. {mins} Min." if is_de else f"{hrs}h {mins}m", **nl)
    pdf.ln(6)

    # Financial table (19% MwSt.)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(30, 41, 59)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(125, 8, "Leistungsbeschreibung" if is_de else "Description", fill=True)
    pdf.cell(65, 8, "Betrag" if is_de else "Amount", align="R", fill=True, **nl)

    pdf.set_text_color(20, 25, 35)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(125, 8, "Parkgebuehr (Netto)" if is_de else "Parking Fee (Net)")
    pdf.cell(65, 8, _fmt_eur(invoice.net_cents, locale), align="R", **nl)
    vat_pct = f"{invoice.vat_rate_bps / 100:.0f}%"
    pdf.cell(125, 8, f"{'Umsatzsteuer (MwSt.)' if is_de else 'German VAT'} {vat_pct}")
    pdf.cell(65, 8, _fmt_eur(invoice.vat_cents, locale), align="R", **nl)

    pdf.set_draw_color(180, 188, 200)
    pdf.line(10, pdf.get_y() + 1, 200, pdf.get_y() + 1)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(125, 9, "Gesamtbetrag (Brutto)" if is_de else "Total Paid (Gross)")
    pdf.cell(65, 9, _fmt_eur(invoice.gross_cents, locale), align="R", **nl)
    pdf.ln(12)

    # Compliance footer
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(100, 110, 125)
    footer_de = (
        "Hinweis nach § 33 UStDV (Kleinbetragsrechnung) & DSGVO: Dieser Beleg enthaelt bewusst keine "
        "Kamerabilder. Kennzeichen- und Bilddaten regelkonformer Parkvorgaenge werden automatisiert "
        f"gemaess DSGVO geloescht. Datenschutz: {org.dpo_email} | Support: {org.support_email}"
    )
    footer_en = (
        "German VAT & GDPR Notice: This receipt intentionally omits camera snapshots. License plate "
        "and image data for settled compliant stays are purged automatically under GDPR Art. 5(1)(e). "
        f"DPO: {org.dpo_email} | Support: {org.support_email}"
    )
    pdf.multi_cell(0, 5, footer_de if is_de else footer_en)
    return bytes(pdf.output())


def issue_invoice_for_payment(
    db: Session,
    storage: ObjectStorageAdapter,
    *,
    payment: Payment,
    session: ParkingSession,
    site: Site,
    org: Organization,
) -> Invoice:
    existing = db.scalars(select(Invoice).where(Invoice.payment_id == payment.id)).first()
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    inv_num = next_invoice_number(db, now.year)
    pdf_key = f"invoices/{now.year}/{inv_num}.pdf"

    invoice = Invoice(
        invoice_number=inv_num,
        payment_id=payment.id,
        site_id=site.id,
        site_name_snapshot=site.name,
        issuer_legal_name=org.legal_name,
        issuer_vat_id=org.vat_id,
        parking_entry_at=session.entry_at,
        parking_exit_at=session.exit_at,
        duration_minutes=session.duration_minutes,
        gross_cents=payment.gross_cents,
        net_cents=payment.net_cents,
        vat_cents=payment.vat_cents,
        vat_rate_bps=payment.vat_rate_bps,
        currency=payment.currency,
        pdf_s3_key=pdf_key,
        issued_at=now,
    )
    db.add(invoice)
    db.flush()

    pdf_bytes = render_invoice_pdf_bytes(
        invoice=invoice,
        org=org,
        site=site,
        payment=payment,
        locale=payment.locale,
    )
    storage.put_bytes(pdf_key, pdf_bytes, content_type="application/pdf")
    return invoice
