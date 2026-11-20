#!/usr/bin/env python3
"""
ParkVektor Private DE — Production Edge AI ANPR Daemon.

Supports:
  --mode rtsp       : Live IP camera RTSP/ONVIF stream + ONNX YOLO + ONNX EU/DE OCR
  --mode video      : Offline MP4/AVI video replay + ONNX YOLO + ONNX EU/DE OCR
  --mode synthetic  : Hardware-free German plate simulation (end-to-end RAM redaction + HMAC upload)
"""
import argparse
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from pipeline.onnx_ocr import OnnxPlateOCR, compute_sharpness_score
from pipeline.onnx_yolo import OnnxYoloDetector
from pipeline.redactor import BoundingBox
from pipeline.rtsp_source import RTSPFrameSource, SyntheticFrameSource
from pipeline.runner import EdgePipelineNode
from pipeline.tracker import FramePlateObservation, PlateTrackAggregator
from sync.offline_queue import OfflineEventQueue


class EdgeConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARKVEKTOR_EDGE_", extra="ignore")

    api_base_url: str = "http://127.0.0.1:8000"
    lane_code: str = "DE-DEMO-01-IN-1"
    direction: str = "ENTRY"
    hmac_secret: str = "dev-lane-secret-change-in-prod"
    rtsp_url: str = ""
    target_fps: float = 10.0
    yolo_plate_model: str = ""
    yolo_privacy_model: str = ""
    ocr_model: str = ""
    ocr_mode: str = "slot"  # "slot" | "ctc"
    queue_db_path: str = "./edge_offline_buffer.sqlite"


def send_heartbeat(cfg: EdgeConfig, queue: OfflineEventQueue, client: httpx.Client) -> None:
    try:
        client.post(
            f"{cfg.api_base_url.rstrip('/')}/api/v1/ingest/heartbeat",
            json={
                "lane_code": cfg.lane_code,
                "status": "OK",
                "fps": cfg.target_fps,
                "queued_offline_events": queue.pending_count(),
            },
            headers={"X-Lane-Token": cfg.hmac_secret},
            timeout=5.0,
        )
    except Exception:
        pass


def run_synthetic_smoke(
    cfg: EdgeConfig,
    plates: list[str],
    *,
    http_client: httpx.Client | None = None,
) -> dict[str, int]:
    queue = OfflineEventQueue(Path(cfg.queue_db_path))
    node = EdgePipelineNode(queue)
    tracker = PlateTrackAggregator(lane_code=cfg.lane_code, direction=cfg.direction)
    source = SyntheticFrameSource(plates)

    passes_enqueued = 0
    for img, ts, plate_text, box in source.frames():
        obs_list: list[FramePlateObservation] = []
        if plate_text:
            crop = img.crop((box.x1, box.y1, box.x2, box.y2))
            obs_list.append(
                FramePlateObservation(
                    plate_box=box,
                    plate_text=plate_text,
                    confidence=0.96,
                    sharpness_score=compute_sharpness_score(crop),
                )
            )
        completed = tracker.update(img, obs_list, face_or_person_boxes=[BoundingBox(180, 50, 260, 150)], captured_at=ts)
        for tracked_pass in completed:
            node.process_pass(tracked_pass)
            passes_enqueued += 1

    for tracked_pass in tracker.flush_all():
        node.process_pass(tracked_pass)
        passes_enqueued += 1

    flush_res = queue.flush(
        endpoint_url=f"{cfg.api_base_url.rstrip('/')}/api/v1/ingest/edge",
        hmac_secret=cfg.hmac_secret,
        client=http_client,
    )
    return {"passes_enqueued": passes_enqueued, **flush_res}


def run_onnx_stream(cfg: EdgeConfig, *, is_file: bool = False, max_frames: int | None = None) -> None:
    if not cfg.rtsp_url or not cfg.yolo_plate_model or not cfg.ocr_model:
        raise SystemExit(
            "Live RTSP/video mode requires --rtsp-url, --yolo-plate-model, and --ocr-model "
            "(or PARKVEKTOR_EDGE_* env vars). Run scripts/download_models.py for setup."
        )

    plate_det = OnnxYoloDetector.from_file(cfg.yolo_plate_model, class_names={0: "license_plate"})
    privacy_det = (
        OnnxYoloDetector.from_file(cfg.yolo_privacy_model, class_names={0: "person", 1: "face"})
        if cfg.yolo_privacy_model
        else None
    )
    ocr = OnnxPlateOCR.from_file(cfg.ocr_model, mode=cfg.ocr_mode)

    queue = OfflineEventQueue(Path(cfg.queue_db_path))
    node = EdgePipelineNode(queue)
    tracker = PlateTrackAggregator(lane_code=cfg.lane_code, direction=cfg.direction)
    source = RTSPFrameSource(cfg.rtsp_url, target_fps=cfg.target_fps, is_file=is_file)
    endpoint = f"{cfg.api_base_url.rstrip('/')}/api/v1/ingest/edge"

    with httpx.Client(timeout=10.0) as client:
        last_hb = 0.0
        for frame, captured_at in source.frames(max_frames=max_frames):
            plate_dets = plate_det.detect(frame)
            face_boxes = [d.box for d in privacy_det.detect(frame)] if privacy_det else []

            frame_obs: list[FramePlateObservation] = []
            for det in plate_dets:
                crop = frame.crop(det.box.clamped(*frame.size))
                pred = ocr.read_plate(crop)
                if pred.text_corrected:
                    frame_obs.append(
                        FramePlateObservation(
                            plate_box=det.box,
                            plate_text=pred.text_corrected,
                            confidence=min(det.confidence, pred.confidence),
                            sharpness_score=pred.sharpness_score,
                        )
                    )

            for completed in tracker.update(frame, frame_obs, face_or_person_boxes=face_boxes, captured_at=captured_at):
                node.process_pass(completed)
                queue.flush(endpoint_url=endpoint, hmac_secret=cfg.hmac_secret, client=client)

            now_s = datetime.now(UTC).timestamp()
            if now_s - last_hb >= 30.0:
                send_heartbeat(cfg, queue, client)
                last_hb = now_s

        for completed in tracker.flush_all():
            node.process_pass(completed)
        queue.flush(endpoint_url=endpoint, hmac_secret=cfg.hmac_secret, client=client)


def main() -> None:
    parser = argparse.ArgumentParser(description="ParkVektor Private DE Edge AI ANPR Daemon")
    parser.add_argument("--mode", choices=["rtsp", "video", "synthetic"], default="synthetic")
    parser.add_argument("--rtsp-url", default="")
    parser.add_argument("--lane-code", default="")
    parser.add_argument("--direction", choices=["ENTRY", "EXIT"], default="")
    parser.add_argument("--yolo-plate-model", default="")
    parser.add_argument("--yolo-privacy-model", default="")
    parser.add_argument("--ocr-model", default="")
    parser.add_argument("--plates", nargs="*", default=["M-PV 9090E", "B-EV 404E"])
    args = parser.parse_args()

    cfg = EdgeConfig()
    if args.rtsp_url:
        cfg.rtsp_url = args.rtsp_url
    if args.lane_code:
        cfg.lane_code = args.lane_code
    if args.direction:
        cfg.direction = args.direction
    if args.yolo_plate_model:
        cfg.yolo_plate_model = args.yolo_plate_model
    if args.yolo_privacy_model:
        cfg.yolo_privacy_model = args.yolo_privacy_model
    if args.ocr_model:
        cfg.ocr_model = args.ocr_model

    if args.mode == "synthetic":
        res = run_synthetic_smoke(cfg, args.plates)
        print(f"[ParkVektor Edge Synthetic] {res}")
    else:
        run_onnx_stream(cfg, is_file=(args.mode == "video"))


if __name__ == "__main__":
    main()
