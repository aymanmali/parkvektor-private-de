#!/usr/bin/env python3
"""
ParkVektor Private DE — Camera & Vehicle Pass Simulator.

Synthesizes realistic German EU-style license plate crops & blurred context frames and replays
hybrid ingestion events (HMAC-signed Edge AI + Smart Camera Webhooks: Axis / Hikvision / ARH)
against a running ParkVektor backend.
"""
import argparse
import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import httpx
from PIL import Image, ImageDraw


def make_german_plate_image_b64(plate_text: str) -> str:
    img = Image.new("RGB", (260, 64), color=(248, 249, 252))
    draw = ImageDraw.Draw(img)
    # Blue EU Euroband with "D"
    draw.rectangle([2, 2, 32, 61], fill=(0, 51, 153))
    draw.text((13, 38), "D", fill=(255, 255, 255))
    draw.rectangle([2, 2, 257, 61], outline=(20, 24, 32), width=2)
    draw.text((46, 24), plate_text, fill=(15, 18, 24))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def make_blurred_context_b64() -> str:
    img = Image.new("RGB", (360, 200), color=(42, 52, 68))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 360, 110], fill=(95, 102, 114))  # blurred windshield region
    draw.rectangle([105, 138, 255, 178], fill=(240, 242, 248))  # bumper plate
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=82)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def send_edge_pass(
    client: httpx.Client,
    *,
    base_url: str,
    lane_code: str,
    direction: str,
    plate: str,
    captured_at: datetime,
    hmac_secret: str,
) -> dict:
    payload = {
        "idempotency_key": f"sim-{uuid.uuid4().hex[:14]}",
        "lane_code": lane_code,
        "direction": direction,
        "plate_raw": plate,
        "ocr_confidence": 0.97,
        "captured_at": captured_at.isoformat(),
        "plate_crop_b64": make_german_plate_image_b64(plate),
        "context_blurred_b64": make_blurred_context_b64(),
        "already_redacted": True,
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = "sha256=" + hmac.new(hmac_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    resp = client.post(
        f"{base_url.rstrip('/')}/api/v1/ingest/edge",
        content=raw,
        headers={"Content-Type": "application/json", "X-ParkVektor-Signature": sig},
    )
    resp.raise_for_status()
    return resp.json()


def send_axis_webhook(
    client: httpx.Client,
    *,
    base_url: str,
    lane_code: str,
    direction: str,
    plate: str,
    captured_at: datetime,
    lane_token: str,
) -> dict:
    payload = {
        "packetCounter": f"axis-{uuid.uuid4().hex[:12]}",
        "sensorProviderID": lane_code,
        "carMoveDirection": "IN" if direction == "ENTRY" else "OUT",
        "plateUTF8": plate,
        "carMoveConfidence": 96,
        "capture_timestamp": captured_at.isoformat(),
        "plateImage": make_german_plate_image_b64(plate),
        "overviewImage": make_blurred_context_b64(),
        "privacyMasked": False,
    }
    resp = client.post(
        f"{base_url.rstrip('/')}/api/v1/ingest/webhook/axis",
        json=payload,
        headers={"X-Lane-Token": lane_token},
    )
    resp.raise_for_status()
    return resp.json()


def run_mall_demo(base_url: str, secret: str) -> None:
    # Use a guaranteed weekday morning so progressive overtime triggers predictably
    now = datetime.now(UTC)
    weekday_base = now.replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=1)
    while weekday_base.weekday() >= 5:
        weekday_base -= timedelta(days=1)

    with httpx.Client(timeout=15.0) as client:
        print("1) Edge AI ENTRY: M-AI 8080E (EV plate, 5h25m weekday stay)")
        r1 = send_edge_pass(
            client,
            base_url=base_url,
            lane_code="DE-DEMO-01-IN-1",
            direction="ENTRY",
            plate="M-AI 8080E",
            captured_at=weekday_base,
            hmac_secret=secret,
        )
        print("   ->", r1)

        print("2) Axis Smart Webhook EXIT: M-AI 8080E -> triggers €7.00 PayLater balance")
        r2 = send_axis_webhook(
            client,
            base_url=base_url,
            lane_code="DE-DEMO-01-OUT-1",
            direction="EXIT",
            plate="M-AI 8080E",
            captured_at=weekday_base + timedelta(hours=5, minutes=25),
            lane_token=secret,
        )
        print("   ->", r2)

        print("3) Drive-through grace (<15 min): F-AB 321 (free exit -> DSGVO purge eligible)")
        send_edge_pass(
            client,
            base_url=base_url,
            lane_code="DE-DEMO-01-IN-1",
            direction="ENTRY",
            plate="F-AB 321",
            captured_at=now - timedelta(minutes=10),
            hmac_secret=secret,
        )
        r3 = send_axis_webhook(
            client,
            base_url=base_url,
            lane_code="DE-DEMO-01-OUT-1",
            direction="EXIT",
            plate="F-AB 321",
            captured_at=now,
            lane_token=secret,
        )
        print("   ->", r3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate German ANPR passes against ParkVektor Private DE")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--secret", default="dev-lane-secret-change-in-prod")
    parser.add_argument("--scenario", default="mall-demo", choices=["mall-demo"])
    args = parser.parse_args()
    run_mall_demo(args.base_url, args.secret)


if __name__ == "__main__":
    main()
