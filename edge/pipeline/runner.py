import base64
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from PIL import Image

from pipeline.redactor import BoundingBox, extract_plate_crop_jpeg, redact_frame_in_ram
from pipeline.voter import FrameObservation, MultiFramePlateVoter
from sync.offline_queue import OfflineEventQueue


@dataclass
class TrackedPassInput:
    lane_code: str
    direction: str  # ENTRY | EXIT
    frames: list[Image.Image]
    observations: list[FrameObservation]
    plate_box: BoundingBox
    face_boxes: list[BoundingBox] | None = None
    bystander_plate_boxes: list[BoundingBox] | None = None
    captured_at: datetime | None = None


class EdgePipelineNode:
    """
    Orchestrates a single tracked vehicle pass:
    1. Multi-frame OCR voting (resolves single-frame noise)
    2. In-RAM DSGVO privacy redaction (faces, windshield, bystander plates)
    3. Enqueues signed payload into SQLite WAL offline ring buffer
    """

    def __init__(self, queue: OfflineEventQueue) -> None:
        self.queue = queue
        self.voter = MultiFramePlateVoter()

    def process_pass(self, pass_in: TrackedPassInput) -> dict:
        voted = self.voter.vote(pass_in.observations)
        best_frame = pass_in.frames[voted.best_frame_index]

        # DSGVO Privacy-by-Design: blur faces/windshield/bystanders in RAM before encoding
        blurred_ctx_bytes = redact_frame_in_ram(
            best_frame,
            face_or_person_boxes=pass_in.face_boxes,
            bystander_plate_boxes=pass_in.bystander_plate_boxes,
            blur_upper_windshield=True,
        )
        plate_crop_bytes = extract_plate_crop_jpeg(best_frame, pass_in.plate_box)

        idem_key = f"edge-{pass_in.lane_code}-{uuid.uuid4().hex[:16]}"
        payload = {
            "idempotency_key": idem_key,
            "lane_code": pass_in.lane_code,
            "direction": pass_in.direction,
            "plate_raw": voted.plate_display,
            "ocr_confidence": voted.confidence,
            "captured_at": (pass_in.captured_at or datetime.now(UTC)).isoformat(),
            "plate_crop_b64": base64.b64encode(plate_crop_bytes).decode("ascii"),
            "context_blurred_b64": base64.b64encode(blurred_ctx_bytes).decode("ascii"),
            "already_redacted": True,
        }
        self.queue.enqueue(idem_key, payload)
        return payload
