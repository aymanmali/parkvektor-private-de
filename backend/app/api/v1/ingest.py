import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.cameras.parsers import parse_vendor_webhook, verify_hmac_signature
from app.adapters.cameras.redactor import decode_and_redact_context_image, decode_plate_crop
from app.adapters.storage.base import ObjectStorageAdapter
from app.adapters.storage.factory import get_storage_adapter
from app.db.session import get_db
from app.domain.matcher import process_camera_pass
from app.models.entities import Lane, Site
from app.models.schemas import EdgeIngestRequest, HeartbeatRequest, IngestResponse

router = APIRouter(prefix="/ingest", tags=["Camera Ingestion"])


def _store_event_images(
    storage: ObjectStorageAdapter,
    *,
    site_code: str,
    idempotency_key: str,
    plate_crop_b64: str | None,
    context_image_b64: str | None,
    already_redacted: bool,
    force_server_redaction: bool,
) -> tuple[str | None, str | None]:
    crop_key: str | None = None
    context_key: str | None = None
    safe_id = idempotency_key.replace("/", "_")[:48] or uuid.uuid4().hex

    if plate_crop_b64:
        crop_bytes = decode_plate_crop(plate_crop_b64)
        crop_key = f"ephemeral/{site_code}/{safe_id}_plate.jpg"
        storage.put_bytes(crop_key, crop_bytes, content_type="image/jpeg")

    if context_image_b64:
        is_redacted = already_redacted and not force_server_redaction
        ctx_bytes = decode_and_redact_context_image(context_image_b64, already_redacted=is_redacted)
        context_key = f"ephemeral/{site_code}/{safe_id}_ctx_blurred.jpg"
        storage.put_bytes(context_key, ctx_bytes, content_type="image/jpeg")

    return crop_key, context_key


@router.post("/edge", response_model=IngestResponse)
async def ingest_edge_event(
    request: Request,
    x_parkvektor_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> IngestResponse:
    """Ingest HMAC-SHA256 signed plate pass from our standalone Edge AI Node."""
    raw_body = await request.body()
    try:
        payload = EdgeIngestRequest.model_validate_json(raw_body)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    lane = db.scalars(
        select(Lane).where(Lane.lane_code == payload.lane_code, Lane.is_active.is_(True))
    ).first()
    if lane is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive lane_code")

    if not verify_hmac_signature(raw_body, lane.hmac_secret, x_parkvektor_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid X-ParkVektor-Signature")

    site = db.get(Site, lane.site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    lane.last_heartbeat_at = datetime.now(UTC)
    crop_key, ctx_key = _store_event_images(
        storage,
        site_code=site.site_code,
        idempotency_key=payload.idempotency_key,
        plate_crop_b64=payload.plate_crop_b64,
        context_image_b64=payload.context_blurred_b64,
        already_redacted=payload.already_redacted,
        force_server_redaction=lane.requires_server_redaction,
    )

    outcome = process_camera_pass(
        db,
        site=site,
        lane=lane,
        idempotency_key=payload.idempotency_key,
        direction=payload.direction,
        plate_raw=payload.plate_raw,
        ocr_confidence=payload.ocr_confidence,
        captured_at=payload.captured_at,
        vendor=lane.camera_vendor,
        plate_crop_s3_key=crop_key,
        context_blurred_s3_key=ctx_key,
        storage=storage,
    )
    return IngestResponse(
        event_id=outcome.event.id,
        session_id=outcome.session.id if outcome.session else None,
        action=outcome.action,
        plate_normalized=outcome.event.plate_normalized or "",
        plate_display=(outcome.session.plate_display if outcome.session and outcome.session.plate_display else outcome.event.plate_raw or ""),
        plate_country=outcome.event.plate_country,
        plate_type=outcome.event.plate_type,
        calculated_fee_cents=outcome.calculated_fee_cents,
        currency=outcome.session.currency if outcome.session else "EUR",
    )


@router.post("/webhook/{vendor}", response_model=IngestResponse)
async def ingest_smart_camera_webhook(
    vendor: str,
    request: Request,
    x_parkvektor_signature: str | None = Header(default=None),
    x_lane_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    storage: ObjectStorageAdapter = Depends(get_storage_adapter),
) -> IngestResponse:
    """
    Ingest Smart ANPR camera webhooks (Axis LPV, Adaptive Recognition Vidar/Carmen,
    Hikvision ISAPI JSON bridge, or Generic JSON). Authenticates via either HMAC signature
    or X-Lane-Token matching the lane's configured secret.
    """
    raw_body = await request.body()
    try:
        raw_json = json.loads(raw_body.decode("utf-8"))
        canonical = parse_vendor_webhook(vendor, raw_json)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    lane = db.scalars(
        select(Lane).where(Lane.lane_code == canonical.lane_code, Lane.is_active.is_(True))
    ).first()
    if lane is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive lane_code")

    authorized = verify_hmac_signature(raw_body, lane.hmac_secret, x_parkvektor_signature) or (
        x_lane_token is not None and x_lane_token == lane.hmac_secret
    )
    if not authorized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid camera credentials (X-ParkVektor-Signature or X-Lane-Token)",
        )

    site = db.get(Site, lane.site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")

    lane.last_heartbeat_at = datetime.now(UTC)
    crop_key, ctx_key = _store_event_images(
        storage,
        site_code=site.site_code,
        idempotency_key=canonical.idempotency_key,
        plate_crop_b64=canonical.plate_crop_b64,
        context_image_b64=canonical.context_image_b64,
        already_redacted=canonical.already_redacted,
        force_server_redaction=lane.requires_server_redaction or (not canonical.already_redacted),
    )

    outcome = process_camera_pass(
        db,
        site=site,
        lane=lane,
        idempotency_key=canonical.idempotency_key,
        direction=canonical.direction,
        plate_raw=canonical.plate_raw,
        ocr_confidence=canonical.ocr_confidence,
        captured_at=canonical.captured_at,
        vendor=canonical.vendor,
        plate_crop_s3_key=crop_key,
        context_blurred_s3_key=ctx_key,
        storage=storage,
    )
    return IngestResponse(
        event_id=outcome.event.id,
        session_id=outcome.session.id if outcome.session else None,
        action=outcome.action,
        plate_normalized=outcome.event.plate_normalized or "",
        plate_display=(outcome.session.plate_display if outcome.session and outcome.session.plate_display else outcome.event.plate_raw or ""),
        plate_country=outcome.event.plate_country,
        plate_type=outcome.event.plate_type,
        calculated_fee_cents=outcome.calculated_fee_cents,
        currency=outcome.session.currency if outcome.session else "EUR",
    )


@router.post("/heartbeat")
def lane_heartbeat(
    payload: HeartbeatRequest,
    x_lane_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    lane = db.scalars(select(Lane).where(Lane.lane_code == payload.lane_code)).first()
    if lane is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lane not found")
    if x_lane_token != lane.hmac_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid X-Lane-Token")
    lane.last_heartbeat_at = datetime.now(UTC)
    db.commit()
    return {"status": "ok", "lane_code": lane.lane_code}
