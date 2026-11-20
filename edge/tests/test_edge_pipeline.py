from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from pipeline.redactor import BoundingBox, redact_frame_in_ram
from pipeline.runner import EdgePipelineNode, TrackedPassInput
from pipeline.voter import FrameObservation, MultiFramePlateVoter
from sync.offline_queue import OfflineEventQueue


def test_multiframe_voter_eliminates_single_frame_ocr_noise():
    voter = MultiFramePlateVoter()
    res = voter.vote(
        [
            FrameObservation("M-A8 1234", confidence=0.71, sharpness_score=0.6),
            FrameObservation("M-AB 1234", confidence=0.95, sharpness_score=0.95),
            FrameObservation("M-AB 1234", confidence=0.94, sharpness_score=0.92),
            FrameObservation("M-AB 1234", confidence=0.91, sharpness_score=0.88),
        ]
    )
    assert res.plate_normalized == "MAB1234"
    assert res.plate_display == "M-AB 1234"
    assert res.confidence > 0.85
    assert res.best_frame_index == 1


def test_dsgvo_in_ram_redactor_destroys_upper_windshield_and_face_detail():
    # Create a sharp checkerboard pattern in the upper windshield/face area
    img = Image.new("RGB", (320, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    for x in range(0, 320, 8):
        for y in range(0, 100, 8):
            if (x // 8 + y // 8) % 2 == 0:
                draw.rectangle([x, y, x + 7, y + 7], fill=(0, 0, 0))
    # Lower plate region stays sharp blue/white
    draw.rectangle([100, 140, 220, 180], fill=(10, 40, 160))

    redacted_bytes = redact_frame_in_ram(
        img,
        face_or_person_boxes=[BoundingBox(20, 20, 80, 90)],
        blur_upper_windshield=True,
    )
    with Image.open(BytesIO(redacted_bytes)) as out:
        # Sharp black/white extremes in upper zone must be destroyed by pixelation + blur
        px = out.getpixel((4, 4))
        assert 40 < px[0] < 215, f"Expected blurred mid-tone pixel, got {px}"
        # Lower plate bumper area remains intact
        lower_px = out.getpixel((160, 160))
        assert lower_px[2] > 120


def test_offline_sqlite_wal_queue_recovers_after_network_outage(tmp_path: Path):
    queue = OfflineEventQueue(tmp_path / "edge_buffer.sqlite")
    node = EdgePipelineNode(queue)

    frame = Image.new("RGB", (320, 200), color=(60, 80, 100))
    payload = node.process_pass(
        TrackedPassInput(
            lane_code="DE-DEMO-01-IN-1",
            direction="ENTRY",
            frames=[frame, frame],
            observations=[
                FrameObservation("B-EV 404E", 0.96),
                FrameObservation("B-EV 404E", 0.98),
            ],
            plate_box=BoundingBox(90, 130, 230, 175),
        )
    )
    assert payload["already_redacted"] is True
    assert queue.pending_count() == 1

    # 1. Simulate internet outage (503) -> event stays safely queued
    def fail_handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "offline"})

    res_fail = queue.flush(
        endpoint_url="https://api.parkvektor.example/api/v1/ingest/edge",
        hmac_secret="test-secret",
        client=httpx.Client(transport=httpx.MockTransport(fail_handler)),
    )
    assert res_fail["sent"] == 0
    assert res_fail["remaining"] == 1

    # 2. Connectivity returns -> event delivered with valid HMAC signature & cleared from queue
    seen_sigs: list[str] = []

    def ok_handler(req: httpx.Request) -> httpx.Response:
        seen_sigs.append(req.headers.get("X-ParkVektor-Signature", ""))
        return httpx.Response(200, json={"action": "SESSION_OPENED"})

    res_ok = queue.flush(
        endpoint_url="https://api.parkvektor.example/api/v1/ingest/edge",
        hmac_secret="test-secret",
        client=httpx.Client(transport=httpx.MockTransport(ok_handler)),
    )
    assert res_ok["sent"] == 1
    assert res_ok["remaining"] == 0
    assert seen_sigs[0].startswith("sha256=")
