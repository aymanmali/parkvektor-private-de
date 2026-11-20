import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class CanonicalCameraEvent:
    idempotency_key: str
    lane_code: str
    direction: str  # ENTRY | EXIT
    plate_raw: str
    ocr_confidence: float
    captured_at: datetime
    vendor: str
    plate_crop_b64: str | None = None
    context_image_b64: str | None = None
    already_redacted: bool = False


def verify_hmac_signature(raw_body: bytes, secret: str, signature_header: str | None) -> bool:
    """Constant-time HMAC-SHA256 verification for Edge AI nodes & signed webhooks."""
    if not signature_header:
        return False
    provided = signature_header.removeprefix("sha256=").strip()
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def _parse_iso_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _normalize_direction(val: str | None, fallback: str = "ENTRY") -> str:
    if not val:
        return fallback
    v = val.strip().upper()
    if v in {"ENTRY", "IN", "APPROACH", "FORWARD", "ENTER"}:
        return "ENTRY"
    if v in {"EXIT", "OUT", "AWAY", "REVERSE", "LEAVE"}:
        return "EXIT"
    return fallback


def parse_vendor_webhook(vendor: str, payload: dict[str, Any]) -> CanonicalCameraEvent:
    """
    Normalize Smart ANPR camera vendor webhooks (Axis LPV, Adaptive Recognition Carmen/Vidar,
    Hikvision ISAPI JSON bridge, or Generic JSON) into a single CanonicalCameraEvent.
    """
    vendor_key = vendor.strip().lower()

    if vendor_key == "axis":
        # Axis License Plate Verifier JSON push format
        lp = payload.get("plateUnicode") or payload.get("plateUTF8") or payload.get("plateASCII") or ""
        conf = float(payload.get("carMoveConfidence", payload.get("confidence", 0.92)))
        if conf > 1.0:
            conf = conf / 100.0
        return CanonicalCameraEvent(
            idempotency_key=str(payload.get("packetCounter") or payload.get("eventId") or uuid.uuid4()),
            lane_code=str(payload.get("sensorProviderID") or payload.get("lane_code") or ""),
            direction=_normalize_direction(payload.get("carMoveDirection") or payload.get("direction")),
            plate_raw=str(lp),
            ocr_confidence=min(max(conf, 0.0), 1.0),
            captured_at=_parse_iso_dt(payload.get("capture_timestamp") or payload.get("timestamp")),
            vendor="axis",
            plate_crop_b64=payload.get("plateImage"),
            context_image_b64=payload.get("overviewImage"),
            already_redacted=bool(payload.get("privacyMasked", False)),
        )

    if vendor_key == "arh":
        # Adaptive Recognition (Vidar / Carmen) JSON event format
        data = payload.get("data", payload)
        plate_obj = data.get("plate", {}) if isinstance(data.get("plate"), dict) else {}
        lp = plate_obj.get("text") or data.get("plate_text") or ""
        conf = float(plate_obj.get("confidence", data.get("confidence", 0.95)))
        if conf > 1.0:
            conf = conf / 100.0
        return CanonicalCameraEvent(
            idempotency_key=str(data.get("event_id") or payload.get("id") or uuid.uuid4()),
            lane_code=str(data.get("camera_id") or data.get("lane_code") or ""),
            direction=_normalize_direction(data.get("direction")),
            plate_raw=str(lp),
            ocr_confidence=min(max(conf, 0.0), 1.0),
            captured_at=_parse_iso_dt(data.get("timestamp")),
            vendor="arh",
            plate_crop_b64=data.get("plate_crop_b64"),
            context_image_b64=data.get("overview_b64"),
            already_redacted=bool(data.get("already_redacted", False)),
        )

    if vendor_key == "hikvision":
        # Hikvision ISAPI ANPR JSON bridge payload
        anpr = payload.get("ANPR", payload)
        lp = anpr.get("licensePlate") or anpr.get("plate") or ""
        conf = float(anpr.get("confidenceLevel", 92))
        if conf > 1.0:
            conf = conf / 100.0
        return CanonicalCameraEvent(
            idempotency_key=str(payload.get("eventId") or anpr.get("uuid") or uuid.uuid4()),
            lane_code=str(payload.get("channelName") or payload.get("lane_code") or ""),
            direction=_normalize_direction(anpr.get("direction")),
            plate_raw=str(lp),
            ocr_confidence=min(max(conf, 0.0), 1.0),
            captured_at=_parse_iso_dt(payload.get("dateTime") or anpr.get("captureTime")),
            vendor="hikvision",
            plate_crop_b64=anpr.get("platePictureB64"),
            context_image_b64=anpr.get("vehiclePictureB64"),
            already_redacted=bool(payload.get("already_redacted", False)),
        )

    if vendor_key == "generic":
        conf = float(payload.get("ocr_confidence", payload.get("confidence", 0.95)))
        if conf > 1.0:
            conf = conf / 100.0
        return CanonicalCameraEvent(
            idempotency_key=str(payload.get("idempotency_key") or payload.get("event_id") or uuid.uuid4()),
            lane_code=str(payload.get("lane_code") or ""),
            direction=_normalize_direction(payload.get("direction")),
            plate_raw=str(payload.get("plate_raw") or payload.get("plate") or ""),
            ocr_confidence=min(max(conf, 0.0), 1.0),
            captured_at=_parse_iso_dt(payload.get("captured_at") or payload.get("timestamp")),
            vendor="generic",
            plate_crop_b64=payload.get("plate_crop_b64"),
            context_image_b64=payload.get("context_blurred_b64"),
            already_redacted=bool(payload.get("already_redacted", False)),
        )

    raise ValueError(f"Unsupported camera webhook vendor: {vendor}")
