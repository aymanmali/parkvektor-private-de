import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime

from PIL import Image, ImageDraw

from pipeline.redactor import BoundingBox


class RTSPFrameSource:
    """
    Production RTSP / ONVIF / MP4 frame reader built on OpenCV (FFmpeg TCP transport).
    Includes automatic reconnect with exponential backoff and FPS throttling so a Jetson
    Orin Nano / x86 Mini-PC maintains steady 10-15 FPS per lane without CPU starvation.
    """

    def __init__(
        self,
        rtsp_url: str,
        *,
        target_fps: float = 10.0,
        max_reconnect_delay_s: float = 30.0,
        is_file: bool = False,
    ) -> None:
        self.rtsp_url = rtsp_url
        self.target_fps = max(0.5, target_fps)
        self.max_reconnect_delay_s = max_reconnect_delay_s
        self.is_file = is_file

    def frames(self, *, max_frames: int | None = None) -> Iterator[tuple[Image.Image, datetime]]:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "opencv-python-headless is required for RTSP/video ingestion. "
                "Install via: uv pip install -r requirements-jetson-ml.txt"
            ) from exc

        # Force reliable TCP framing for IP LPR cameras (Axis, Hikvision, Dahua, ARH)
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp|stimeout;5000000")
        min_interval = 1.0 / self.target_fps
        backoff = 1.0
        emitted = 0

        while True:
            cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                if self.is_file:
                    return
                time.sleep(backoff)
                backoff = min(self.max_reconnect_delay_s, backoff * 2.0)
                continue

            backoff = 1.0
            last_emit = 0.0
            try:
                while True:
                    ok, bgr = cap.read()
                    if not ok or bgr is None:
                        if self.is_file:
                            return
                        break  # Trigger RTSP reconnect

                    now_mono = time.monotonic()
                    if (now_mono - last_emit) < min_interval:
                        continue
                    last_emit = now_mono

                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    yield Image.fromarray(rgb), datetime.now(UTC)
                    emitted += 1
                    if max_frames is not None and emitted >= max_frames:
                        return
            finally:
                cap.release()


class SyntheticFrameSource:
    """
    Hardware-free frame generator for local demos & CI smoke tests.
    Synthesizes realistic German vehicle pass sequences (with plate crop & upper windshield region).
    """

    def __init__(self, plates: list[str], *, frames_per_pass: int = 4) -> None:
        self.plates = plates
        self.frames_per_pass = frames_per_pass

    def frames(self) -> Iterator[tuple[Image.Image, datetime, str, BoundingBox]]:
        for plate in self.plates:
            for step in range(self.frames_per_pass):
                img = Image.new("RGB", (640, 360), color=(38, 46, 62))
                draw = ImageDraw.Draw(img)
                # Simulated windshield/driver zone (upper half)
                draw.rectangle([140, 40, 500, 175], fill=(90, 110, 130))
                # Simulated bumper + German plate shifting slightly across lane frames
                x_shift = step * 8
                box = BoundingBox(210 + x_shift, 235, 410 + x_shift, 285)
                draw.rectangle([box.x1, box.y1, box.x2, box.y2], fill=(248, 249, 252), outline=(15, 20, 30), width=2)
                draw.rectangle([box.x1 + 2, box.y1 + 2, box.x1 + 24, box.y2 - 2], fill=(0, 51, 153))
                draw.text((box.x1 + 36, box.y1 + 18), plate, fill=(10, 14, 20))
                yield img, datetime.now(UTC), plate, box
            # Emit 3 empty gap frames so tracker cleanly finalizes the vehicle pass
            empty = Image.new("RGB", (640, 360), color=(32, 38, 50))
            for _ in range(3):
                yield empty, datetime.now(UTC), "", BoundingBox(0, 0, 0, 0)
