from pathlib import Path
from types import SimpleNamespace

import httpx
import numpy as np
from PIL import Image, ImageDraw

from cli import EdgeConfig, run_synthetic_smoke
from pipeline.onnx_ocr import (
    EU_DE_ALPHABET,
    OnnxPlateOCR,
    apply_german_positional_ocr_fix,
    compute_sharpness_score,
)
from pipeline.onnx_yolo import OnnxYoloDetector, letterbox_image
from pipeline.redactor import BoundingBox
from pipeline.tracker import FramePlateObservation, PlateTrackAggregator


class _FakeYoloV8Session:
    """Emits a real YOLOv8 [1, 4+C, N] ONNX tensor with 2 overlapping boxes + 1 distinct box."""

    def get_inputs(self):
        return [SimpleNamespace(name="images")]

    def run(self, _out, _feed):
        # 3 detections in 640x640 letterbox coords: first two overlap heavily (NMS must keep highest conf)
        preds = np.zeros((1, 5, 3), dtype=np.float32)
        # Box 0: center (320, 320), size (120, 40), conf 0.92
        preds[0, :, 0] = [320.0, 320.0, 120.0, 40.0, 0.92]
        # Box 1: near-duplicate of Box 0, conf 0.70 -> suppressed by NMS
        preds[0, :, 1] = [324.0, 321.0, 118.0, 39.0, 0.70]
        # Box 2: separate bystander plate at (100, 400), conf 0.85 -> kept
        preds[0, :, 2] = [100.0, 400.0, 90.0, 30.0, 0.85]
        return [preds]


class _FakeSlotOCRSession:
    """Emits a fixed-slot [1, 10, vocab] logits tensor spelling 'M-PV 2026E'."""

    def __init__(self, target_text: str, mode: str = "slot") -> None:
        self.target_text = target_text
        self.mode = mode

    def get_inputs(self):
        return [SimpleNamespace(name="input")]

    def run(self, _out, _feed):
        vocab = len(EU_DE_ALPHABET)
        seq = self.target_text
        if self.mode == "ctc":
            # Duplicate characters separated by blanks like real CTC output
            expanded = []
            for ch in seq:
                expanded.extend([ch, ch, "_"])
            seq = "".join(expanded)
        logits = np.full((1, len(seq), vocab), -5.0, dtype=np.float32)
        for i, ch in enumerate(seq):
            idx = EU_DE_ALPHABET.find(ch)
            if idx >= 0:
                logits[0, i, idx] = 6.0
        return [logits]


def test_onnx_yolo_letterbox_and_nms_postprocessing():
    img = Image.new("RGB", (1280, 720), color=(40, 50, 60))
    tensor, scale, (pad_x, pad_y) = letterbox_image(img, input_size=640)
    assert tensor.shape == (1, 3, 640, 640)
    assert scale == 0.5
    assert pad_x == 0 and pad_y == 140

    det = OnnxYoloDetector(_FakeYoloV8Session(), class_names={0: "license_plate"})
    results = det.detect(img)
    # Overlapping duplicate must be suppressed -> exactly 2 detections returned
    assert len(results) == 2
    assert results[0].confidence > 0.9
    assert results[0].label == "license_plate"
    # Center y=320 in 640 letterbox with pad_y=140 and scale=0.5 maps back to y=360 in 1280x720
    mid_y = (results[0].box.y1 + results[0].box.y2) / 2
    assert 350 <= mid_y <= 370


def test_onnx_ocr_slot_and_ctc_decoders_and_german_positional_fix():
    crop = Image.new("RGB", (160, 48), color=(250, 250, 250))
    draw = ImageDraw.Draw(crop)
    draw.text((20, 16), "M-PV 2026E", fill=(0, 0, 0))

    ocr_slot = OnnxPlateOCR(_FakeSlotOCRSession("MPV2026E__"), mode="slot")
    pred_slot = ocr_slot.read_plate(crop)
    assert pred_slot.text_raw == "MPV2026E"
    assert pred_slot.text_corrected == "M-PV 2026E"
    assert pred_slot.confidence > 0.99

    ocr_ctc = OnnxPlateOCR(_FakeSlotOCRSession("GÖAB901", mode="ctc"), mode="ctc")
    pred_ctc = ocr_ctc.read_plate(crop)
    assert pred_ctc.text_raw == "GÖAB901"
    assert pred_ctc.text_corrected == "GÖ-AB 901"

    # German StVZO positional fix: digits in letter group -> letters, letters in digit group -> digits
    assert apply_german_positional_ocr_fix("M-A8 1O2E") == "M-AB 102E"
    assert apply_german_positional_ocr_fix("B-XY 8S5") == "B-XY 855"


def test_sharpness_distinguishes_crisp_from_flat_frame():
    flat = Image.new("RGB", (120, 40), color=(128, 128, 128))
    crisp = Image.new("RGB", (120, 40), color=(255, 255, 255))
    draw = ImageDraw.Draw(crisp)
    for x in range(0, 120, 6):
        draw.line([(x, 0), (x, 40)], fill=(0, 0, 0), width=2)
    assert compute_sharpness_score(crisp) > compute_sharpness_score(flat)


def test_iou_tracker_aggregates_frames_and_collects_bystander_plates():
    tracker = PlateTrackAggregator(lane_code="DE-DEMO-01-IN-1", direction="ENTRY", min_frames=2, max_missed_frames=2)
    frame = Image.new("RGB", (640, 360), color=(50, 60, 70))

    # Vehicle A moves slightly across 3 frames while Vehicle B is visible alongside it (bystander)
    for step in range(3):
        emitted = tracker.update(
            frame,
            [
                FramePlateObservation(BoundingBox(200 + step * 5, 200, 320 + step * 5, 240), "M-PV 100E", 0.95, 1.2),
                FramePlateObservation(BoundingBox(420, 210, 520, 245), "B-BY 999", 0.88, 1.0),
            ],
        )
        assert emitted == []

    # Vehicle A & B leave camera FOV -> 2 empty frames trigger clean track flush
    assert tracker.update(frame, []) == []
    flushed = tracker.update(frame, [])
    assert len(flushed) == 2
    # Each flushed track captured the OTHER vehicle's box as a bystander plate to blur!
    assert all(len(t.bystander_plate_boxes or []) == 1 for t in flushed)


def test_synthetic_edge_daemon_end_to_end_signed_upload(tmp_path: Path):
    seen_headers: list[str] = []
    seen_plates: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_headers.append(req.headers.get("X-ParkVektor-Signature", ""))
        import json

        seen_plates.append(json.loads(req.content.decode())["plate_raw"])
        return httpx.Response(200, json={"action": "SESSION_OPENED"})

    cfg = EdgeConfig(queue_db_path=str(tmp_path / "buf.sqlite"))
    res = run_synthetic_smoke(
        cfg,
        ["M-PV 2026E", "GÖ-AB 901"],
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert res["passes_enqueued"] == 2
    assert res["sent"] == 2
    assert res["remaining"] == 0
    assert seen_plates == ["M-PV 2026E", "GÖ-AB 901"]
    assert all(h.startswith("sha256=") for h in seen_headers)
