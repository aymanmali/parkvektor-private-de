import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.crypto import decrypt_pii, encrypt_pii
from app.models.entities import DSGVOPurgeAuditLog, ParkingSession, Violation


def _sign(body_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


def test_pii_envelope_encryption_roundtrip():
    token = encrypt_pii("Erika Mustermann, Musterweg 10, Musterstadt", "secret-key-1")
    assert token.startswith("enc:v1:")
    assert "Erika" not in token
    assert decrypt_pii(token, "secret-key-1") == "Erika Mustermann, Musterweg 10, Musterstadt"


def test_autopay_wallet_automatic_drive_out_charge_and_invoice(test_context):
    client = test_context["client"]
    lane_secret = test_context["lane_secret"]

    # 1. Enroll driver vehicle in AutoPay with DSGVO consent
    r_reg = client.post(
        "/api/v1/autopay/register",
        json={
            "email": "anna.schmidt@example.de",
            "plate_raw": "M-AU 700E",
            "dsgvo_consent_accepted": True,
        },
    )
    assert r_reg.status_code == 201, r_reg.text
    assert r_reg.json()["vehicles"][0]["plate_normalized"] == "MAU700E"

    # 2. Vehicle enters & exits 5h 30m later on a Wednesday -> automatically charged €7.00 via AutoPay!
    t_in = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    t_out = t_in + timedelta(hours=5, minutes=30)

    entry_raw = json.dumps(
        {
            "idempotency_key": "ap-entry-1",
            "lane_code": "DE-DEMO-01-IN-1",
            "direction": "ENTRY",
            "plate_raw": "M-AU 700E",
            "ocr_confidence": 0.99,
            "captured_at": t_in.isoformat(),
        }
    ).encode("utf-8")
    r_in = client.post(
        "/api/v1/ingest/edge",
        content=entry_raw,
        headers={"Content-Type": "application/json", "X-ParkVektor-Signature": _sign(entry_raw, lane_secret)},
    )
    assert r_in.status_code == 200

    r_out = client.post(
        "/api/v1/ingest/webhook/generic",
        json={
            "idempotency_key": "ap-exit-1",
            "lane_code": "DE-DEMO-01-OUT-1",
            "direction": "EXIT",
            "plate_raw": "M-AU 700E",
            "ocr_confidence": 0.99,
            "captured_at": t_out.isoformat(),
            "already_redacted": True,
        },
        headers={"X-Lane-Token": lane_secret},
    )
    assert r_out.status_code == 200, r_out.text
    assert r_out.json()["action"] == "SESSION_AUTOPAY_CHARGED"
    assert r_out.json()["calculated_fee_cents"] == 700

    # 3. Verify invoice appears in AutoPay account & PDF downloads cleanly
    r_acc = client.get("/api/v1/autopay/account", params={"email": "anna.schmidt@example.de"})
    assert r_acc.status_code == 200
    invoices = r_acc.json()["recent_invoices"]
    assert len(invoices) == 1
    assert invoices[0]["gross_cents"] == 700
    r_pdf = client.get(invoices[0]["pdf_url"])
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF-")


def test_mall_tenant_validation_reduces_fee_to_zero(test_context):
    client = test_context["client"]

    # Seeded M-PV 2026E has 5h35m weekday stay (€7.00 due). Applying +120m cinema validation -> €0.00 COMPLETED_FREE!
    r_val = client.post(
        "/api/v1/merchants/validate",
        json={"plate_raw": "M-PV 2026E", "bonus_minutes": 120, "voucher_code": "CINE-2026-881"},
        headers={"X-Merchant-Token": "demo-merchant-kinowelt-token"},
    )
    assert r_val.status_code == 200, r_val.text
    data = r_val.json()
    assert data["previous_fee_cents"] == 700
    assert data["new_fee_cents"] == 0
    assert data["session_status"] == "COMPLETED_FREE"

    r_recent = client.get(
        "/api/v1/merchants/recent",
        headers={"X-Merchant-Token": "demo-merchant-kinowelt-token"},
    )
    assert r_recent.status_code == 200
    assert len(r_recent.json()["validations"]) == 1


def test_qa_approve_kba_lookup_notice_pdf_and_csv_batch(test_context):
    client = test_context["client"]
    admin_headers = test_context["admin_headers"]

    # Find seeded QA_QUEUE violation (N-OV 404)
    r_list = client.get("/api/v1/admin/violations", params={"status": "QA_QUEUE"}, headers=admin_headers)
    assert r_list.status_code == 200
    qa_items = r_list.json()
    assert len(qa_items) >= 1
    vid = qa_items[0]["id"]

    # 1. QA Approve
    r_qa = client.post(
        f"/api/v1/admin/violations/{vid}/qa",
        json={"decision": "APPROVE", "reviewer": "A. Weber", "notes": "Kennzeichen eindeutig"},
        headers=admin_headers,
    )
    assert r_qa.status_code == 200
    assert r_qa.json()["status"] == "APPROVED"

    # 2. Export German KBA § 39 StVG CSV batch
    r_csv = client.get("/api/v1/admin/violations/kba-batch.csv", headers=admin_headers)
    assert r_csv.status_code == 200
    assert "Aktenzeichen;Kennzeichen;Land" in r_csv.text
    assert "NOV404" in r_csv.text

    # 3. Execute Mock KBA § 39 StVG lookup -> encrypts keeper PII & transitions to NOTICE_SENT
    r_kba = client.post(
        f"/api/v1/admin/violations/{vid}/kba-lookup",
        json={"provider": "mock_kba"},
        headers=admin_headers,
    )
    assert r_kba.status_code == 200
    assert r_kba.json()["status"] == "NOTICE_SENT"
    assert r_kba.json()["keeper_name"] is not None

    # 4. Download German Zahlungsaufforderung PDF notice
    r_pdf = client.get(f"/api/v1/admin/violations/{vid}/notice.pdf", headers=admin_headers)
    assert r_pdf.status_code == 200
    assert r_pdf.content.startswith(b"%PDF-")


def test_qa_reject_triggers_immediate_dsgvo_purge(test_context):
    client = test_context["client"]
    admin_headers = test_context["admin_headers"]
    SessionCls = test_context["session_factory"]

    r_list = client.get("/api/v1/admin/violations", params={"status": "QA_QUEUE"}, headers=admin_headers)
    vid = r_list.json()[0]["id"]
    sid = r_list.json()[0]["session_id"]

    r_rej = client.post(
        f"/api/v1/admin/violations/{vid}/qa",
        json={"decision": "REJECT", "reviewer": "A. Weber", "notes": "OCR unlesbar"},
        headers=admin_headers,
    )
    assert r_rej.status_code == 200
    assert r_rej.json()["status"] == "CANCELLED"

    with SessionCls() as db:
        sess = db.get(ParkingSession, sid)
        assert sess.status == "PURGED"
        assert sess.plate_normalized is None
        audit = db.scalars(
            select(DSGVOPurgeAuditLog).where(DSGVOPurgeAuditLog.session_uuid == sid)
        ).first()
        assert audit is not None
        assert audit.purge_reason == "QA_REJECTED"


def test_driver_dispute_fahrerbenennung_and_operator_accept_purges_pii(test_context):
    client = test_context["client"]
    admin_headers = test_context["admin_headers"]
    SessionCls = test_context["session_factory"]

    # Seeded NOTICE_SENT violation is F-WD 999
    r_list = client.get("/api/v1/admin/violations", params={"status": "NOTICE_SENT"}, headers=admin_headers)
    assert r_list.status_code == 200
    notice_v = r_list.json()[0]
    case_no = notice_v["case_number"]
    vid = notice_v["id"]

    # 1. Privacy gate: wrong plate must fail with 404
    r_bad = client.get("/api/v1/public/disputes/case", params={"case_number": case_no, "plate": "B-ZZ 1"})
    assert r_bad.status_code == 404

    # 2. Valid case + plate lookup succeeds
    r_case = client.get("/api/v1/public/disputes/case", params={"case_number": case_no, "plate": "F-WD 999"})
    assert r_case.status_code == 200
    assert r_case.json()["penalty_cents"] == 3500

    # 3. Submit Widerspruch with BGH Fahrerbenennung (NOT_DRIVER)
    r_sub = client.post(
        "/api/v1/public/disputes/submit",
        json={
            "case_number": case_no,
            "plate_raw": "F-WD 999",
            "reason": "NOT_DRIVER",
            "explanation": "Fahrzeug war an Kollegen verliehen.",
            "nominated_driver_name": "Lukas Meyer",
            "nominated_driver_address": "Berliner Allee 12, 40212 Düsseldorf",
        },
    )
    assert r_sub.status_code == 201, r_sub.text
    dispute_id = r_sub.json()["dispute_id"]
    assert r_sub.json()["violation_status"] == "DISPUTED"

    # 4. Operator accepts dispute -> cancels violation & purges keeper PII + session PII
    r_res = client.post(
        f"/api/v1/admin/disputes/{dispute_id}/resolve",
        json={"decision": "ACCEPT_CANCEL"},
        headers=admin_headers,
    )
    assert r_res.status_code == 200
    assert r_res.json()["violation_status"] == "CANCELLED"

    with SessionCls() as db:
        v_after = db.get(Violation, vid)
        assert v_after.keeper_name_encrypted is None
        assert v_after.keeper_address_encrypted is None
        sess_after = db.get(ParkingSession, v_after.session_id)
        assert sess_after.status == "PURGED"
        assert sess_after.plate_normalized is None
