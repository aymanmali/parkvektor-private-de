import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.models.entities import CameraEvent, DSGVOPurgeAuditLog, Invoice, ParkingSession


def _make_dummy_jpeg_b64() -> str:
    img = Image.new("RGB", (320, 180), color=(45, 75, 115))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _sign(body_bytes: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()


def test_full_barrierless_lifecycle_edge_webhook_checkout_invoice_and_dsgvo_purge(test_context):
    client = test_context["client"]
    storage = test_context["storage"]
    admin_headers = test_context["admin_headers"]
    lane_secret = test_context["lane_secret"]
    SessionCls = test_context["session_factory"]

    img_b64 = _make_dummy_jpeg_b64()
    # Deterministic weekday: Wednesday 2026-11-18 09:00 UTC -> 14:40 UTC (5h40m => €7.00)
    t_in = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    t_out = t_in + timedelta(hours=5, minutes=40)

    # 1. Edge AI ENTRY event with HMAC signature & image crops
    entry_payload = {
        "idempotency_key": "e2e-edge-entry-001",
        "lane_code": "DE-DEMO-01-IN-1",
        "direction": "ENTRY",
        "plate_raw": "D-EV 777E",
        "ocr_confidence": 0.98,
        "captured_at": t_in.isoformat(),
        "plate_crop_b64": img_b64,
        "context_blurred_b64": img_b64,
        "already_redacted": True,
    }
    raw_entry = json.dumps(entry_payload).encode("utf-8")
    r_in = client.post(
        "/api/v1/ingest/edge",
        content=raw_entry,
        headers={
            "Content-Type": "application/json",
            "X-ParkVektor-Signature": _sign(raw_entry, lane_secret),
        },
    )
    assert r_in.status_code == 200, r_in.text
    d_in = r_in.json()
    assert d_in["action"] == "SESSION_OPENED"
    assert d_in["plate_normalized"] == "DEV777E"
    assert d_in["plate_type"] == "EV"
    session_id = d_in["session_id"]

    # 2. Smart ANPR Camera (Axis) EXIT webhook with unredacted overview image -> triggers server blur + fee
    axis_payload = {
        "packetCounter": "e2e-axis-exit-001",
        "sensorProviderID": "DE-DEMO-01-OUT-1",
        "carMoveDirection": "OUT",
        "plateUTF8": "D-EV 777E",
        "carMoveConfidence": 97,
        "capture_timestamp": t_out.isoformat(),
        "plateImage": img_b64,
        "overviewImage": img_b64,
        "privacyMasked": False,
    }
    r_out = client.post(
        "/api/v1/ingest/webhook/axis",
        json=axis_payload,
        headers={"X-Lane-Token": lane_secret},
    )
    assert r_out.status_code == 200, r_out.text
    d_out = r_out.json()
    assert d_out["action"] == "SESSION_AWAITING_PAYMENT"
    assert d_out["calculated_fee_cents"] == 700

    # Verify ephemeral image objects exist on storage prior to DSGVO purge
    with SessionCls() as db:
        sess = db.get(ParkingSession, session_id)
        in_ev = db.get(CameraEvent, sess.entry_event_id)
        out_ev = db.get(CameraEvent, sess.exit_event_id)
        stored_keys = [
            in_ev.plate_crop_s3_key,
            in_ev.context_blurred_s3_key,
            out_ev.plate_crop_s3_key,
            out_ev.context_blurred_s3_key,
        ]
        assert all(k and storage.exists(k) for k in stored_keys)

    # 3. Driver QR Lookup -> Checkout -> Mock Confirm -> German 19% MwSt. PDF Invoice
    r_lookup = client.get("/api/v1/public/sessions/lookup", params={"plate": "d ev 777e"})
    assert r_lookup.status_code == 200
    lk = r_lookup.json()
    assert lk["found"] is True
    assert lk["amount_due_cents"] == 700
    assert lk["breakdown"]["net_cents"] == 588
    assert lk["breakdown"]["vat_cents"] == 112

    r_co = client.post(
        "/api/v1/public/payments/checkout",
        json={"session_id": session_id, "locale": "de", "payment_method": "APPLE_PAY"},
    )
    assert r_co.status_code == 200
    co = r_co.json()
    assert co["requires_mock_confirm"] is True

    r_conf = client.post(
        "/api/v1/public/payments/mock-confirm",
        json={"payment_id": co["payment_id"], "method": "APPLE_PAY"},
    )
    assert r_conf.status_code == 200
    settled = r_conf.json()
    inv_num = settled["invoice_number"]
    assert inv_num.startswith("RE-")

    r_pdf = client.get(settled["invoice_pdf_url"])
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF-")

    # 4. Run DSGVO Auto-Purge -> proves ephemeral images & plates are hard-deleted while § 147 AO invoice survives!
    r_purge = client.post(
        "/api/v1/admin/dsgvo/run-purge",
        json={"force_immediate": True},
        headers=admin_headers,
    )
    assert r_purge.status_code == 200
    purge_data = r_purge.json()
    assert purge_data["sessions_purged"] >= 1
    assert purge_data["s3_objects_deleted"] >= 4

    # Verify physical deletion from object storage
    for key in stored_keys:
        assert not storage.exists(key)

    # Verify plate PII is NULLed in DB, zero-PII audit entry written, and PDF invoice still downloadable!
    with SessionCls() as db:
        sess_after = db.get(ParkingSession, session_id)
        assert sess_after.status == "PURGED"
        assert sess_after.plate_normalized is None
        assert sess_after.plate_display is None
        assert sess_after.pii_purged_at is not None

        audit_row = db.scalars(
            select(DSGVOPurgeAuditLog).where(DSGVOPurgeAuditLog.session_uuid == session_id)
        ).first()
        assert audit_row is not None
        assert audit_row.purge_reason == "PAID_SETTLED"
        assert audit_row.s3_objects_deleted == 4

        inv_row = db.scalars(select(Invoice).where(Invoice.invoice_number == inv_num)).first()
        assert inv_row is not None
        assert storage.exists(inv_row.pdf_s3_key)

    r_pdf_after = client.get(f"/api/v1/public/invoices/{inv_num}/pdf")
    assert r_pdf_after.status_code == 200


def test_fuzzy_reconciliation_and_gdpr_art15_art17(test_context):
    client = test_context["client"]
    admin_headers = test_context["admin_headers"]

    # Seeded fuzzy pair K-DO 881 / K-D0 881 should appear in RECONCILIATION_NEEDED
    r_list = client.get(
        "/api/v1/admin/sessions",
        params={"status": "RECONCILIATION_NEEDED"},
        headers=admin_headers,
    )
    assert r_list.status_code == 200
    fuzzy_rows = r_list.json()
    assert len(fuzzy_rows) == 1
    sid = fuzzy_rows[0]["id"]

    # Reconcile as free/approved
    r_rec = client.post(
        f"/api/v1/admin/sessions/{sid}/reconcile",
        json={"confirmed_plate": "K-DO 881", "action": "MARK_FREE"},
        headers=admin_headers,
    )
    assert r_rec.status_code == 200
    assert r_rec.json()["status"] == "COMPLETED_FREE"

    # Art. 15 Export finds K-DO 881 prior to erasure
    r_exp = client.get("/api/v1/admin/dsgvo/export", params={"plate": "K-DO 881"}, headers=admin_headers)
    assert r_exp.status_code == 200
    assert len(r_exp.json()["active_or_retained_sessions"]) == 1

    # Art. 17 Erasure immediately purges COMPLETED_FREE session
    r_del = client.delete("/api/v1/admin/dsgvo/erase", params={"plate": "K-DO 881"}, headers=admin_headers)
    assert r_del.status_code == 200
    assert r_del.json()["erased_sessions"] == 1

    # Art. 15 Export now returns 0 retained sessions for that plate
    r_exp2 = client.get("/api/v1/admin/dsgvo/export", params={"plate": "K-DO 881"}, headers=admin_headers)
    assert len(r_exp2.json()["active_or_retained_sessions"]) == 0
