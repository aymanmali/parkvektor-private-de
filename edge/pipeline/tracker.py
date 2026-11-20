from dataclasses import dataclass, field
from datetime import UTC, datetime

from PIL import Image

from pipeline.redactor import BoundingBox
from pipeline.runner import TrackedPassInput
from pipeline.voter import FrameObservation


def box_iou(a: BoundingBox, b: BoundingBox) -> float:
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(1, (a.x2 - a.x1) * (a.y2 - a.y1))
    area_b = max(1, (b.x2 - b.x1) * (b.y2 - b.y1))
    return inter / float(area_a + area_b - inter)


@dataclass
class FramePlateObservation:
    plate_box: BoundingBox
    plate_text: str
    confidence: float
    sharpness_score: float


@dataclass
class _ActiveTrack:
    track_id: int
    last_box: BoundingBox
    missed_frames: int = 0
    frames: list[Image.Image] = field(default_factory=list)
    observations: list[FrameObservation] = field(default_factory=list)
    face_boxes_per_frame: list[list[BoundingBox]] = field(default_factory=list)
    bystander_boxes_per_frame: list[list[BoundingBox]] = field(default_factory=list)
    first_seen_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PlateTrackAggregator:
    """
    Lightweight IoU multi-frame vehicle pass tracker.
    Groups consecutive detections of the same vehicle crossing a garage lane, automatically
    collects secondary/bystander plates for DSGVO redaction, and emits exactly ONE finalized
    TrackedPassInput once the vehicle exits the camera FOV (or reaches max_frames_per_track).
    """

    def __init__(
        self,
        *,
        lane_code: str,
        direction: str,
        iou_threshold: float = 0.25,
        min_frames: int = 2,
        max_missed_frames: int = 3,
        max_frames_per_track: int = 8,
    ) -> None:
        self.lane_code = lane_code
        self.direction = direction
        self.iou_threshold = iou_threshold
        self.min_frames = min_frames
        self.max_missed_frames = max_missed_frames
        self.max_frames_per_track = max_frames_per_track
        self._next_id = 1
        self._tracks: dict[int, _ActiveTrack] = {}

    def update(
        self,
        frame: Image.Image,
        plate_observations: list[FramePlateObservation],
        *,
        face_or_person_boxes: list[BoundingBox] | None = None,
        captured_at: datetime | None = None,
    ) -> list[TrackedPassInput]:
        now = captured_at or datetime.now(UTC)
        faces = face_or_person_boxes or []
        matched_tracks: set[int] = set()
        emitted: list[TrackedPassInput] = []

        all_plate_boxes = [obs.plate_box for obs in plate_observations]

        for idx, obs in enumerate(plate_observations):
            bystanders = [b for j, b in enumerate(all_plate_boxes) if j != idx]
            best_tid: int | None = None
            best_iou = self.iou_threshold
            for tid, tr in self._tracks.items():
                if tid in matched_tracks:
                    continue
                score = box_iou(tr.last_box, obs.plate_box)
                if score >= best_iou:
                    best_iou = score
                    best_tid = tid

            if best_tid is None:
                tid = self._next_id
                self._next_id += 1
                tr = _ActiveTrack(track_id=tid, last_box=obs.plate_box, first_seen_at=now)
                self._tracks[tid] = tr
                best_tid = tid
            else:
                tr = self._tracks[best_tid]
                tr.last_box = obs.plate_box
                tr.missed_frames = 0

            matched_tracks.add(best_tid)
            tr.frames.append(frame)
            tr.observations.append(
                FrameObservation(
                    plate_text=obs.plate_text,
                    confidence=obs.confidence,
                    sharpness_score=obs.sharpness_score,
                )
            )
            tr.face_boxes_per_frame.append(faces)
            tr.bystander_boxes_per_frame.append(bystanders)

            if len(tr.observations) >= self.max_frames_per_track:
                emitted.append(self._finalize_track(tr))
                del self._tracks[best_tid]

        # Age unmatched tracks & flush those that left the camera view
        for tid in list(self._tracks.keys()):
            if tid in matched_tracks:
                continue
            tr = self._tracks[tid]
            tr.missed_frames += 1
            if tr.missed_frames >= self.max_missed_frames:
                if len(tr.observations) >= self.min_frames:
                    emitted.append(self._finalize_track(tr))
                del self._tracks[tid]

        return emitted

    def flush_all(self) -> list[TrackedPassInput]:
        """Flush all remaining valid tracks (used on clean daemon shutdown / video EOF)."""
        out: list[TrackedPassInput] = []
        for tr in list(self._tracks.values()):
            if len(tr.observations) >= self.min_frames:
                out.append(self._finalize_track(tr))
        self._tracks.clear()
        return out

    def _finalize_track(self, tr: _ActiveTrack) -> TrackedPassInput:
        # Pick sharpest observation index for representative face/bystander redaction boxes
        best_idx = max(range(len(tr.observations)), key=lambda i: tr.observations[i].confidence * tr.observations[i].sharpness_score)
        return TrackedPassInput(
            lane_code=self.lane_code,
            direction=self.direction,
            frames=tr.frames,
            observations=tr.observations,
            plate_box=tr.last_box,
            face_boxes=tr.face_boxes_per_frame[best_idx],
            bystander_plate_boxes=tr.bystander_boxes_per_frame[best_idx],
            captured_at=tr.first_seen_at,
        )
