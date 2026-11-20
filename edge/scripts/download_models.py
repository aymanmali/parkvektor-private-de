#!/usr/bin/env python3
"""
ParkVektor Edge AI — ONNX Model Preparation & Jetson TensorRT Setup Guide.

Recommended Open-Source Models for German/EU ANPR + DSGVO Privacy Redaction:
  1. License Plate Detector (YOLOv8n / YOLOv11n ONNX, 640x640, single-class plate):
     Export from Ultralytics: `yolo export model=license_plate_detector.pt format=onnx imgsz=640 simplify=True`
  2. DSGVO Face & Person Privacy Detector (YOLOv8n COCO/Face ONNX, 640x640):
     `yolo export model=yolov8n.pt format=onnx imgsz=640 simplify=True`
  3. EU/German FE-Schrift Plate OCR (fast-plate-ocr european-plates-mobile-vit-v2 ONNX):
     https://github.com/ankandrew/fast-plate-ocr (European plates weights, Apache-2.0 / MIT)

On NVIDIA Jetson Orin Nano / AGX Orin:
  Install `onnxruntime-gpu` (JetPack wheel) — `create_onnx_session()` automatically
  selects TensorrtExecutionProvider -> CUDAExecutionProvider -> CPUExecutionProvider.
"""
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def check_models() -> int:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    expected = [
        ("plate_detector.onnx", "YOLOv8n/v11n EU/DE License Plate Detector (640x640)"),
        ("privacy_person_face.onnx", "YOLOv8n Person/Face DSGVO Privacy Detector (640x640)"),
        ("eu_plate_ocr.onnx", "EU/German FE-Schrift Plate OCR (fast-plate-ocr / PaddleOCR)"),
    ]
    missing = 0
    print(f"Checking ONNX weights in: {MODELS_DIR}\n")
    for fname, desc in expected:
        p = MODELS_DIR / fname
        status = "FOUND" if p.is_file() else "MISSING"
        if not p.is_file():
            missing += 1
        print(f"  [{status:7s}] {fname:28s} — {desc}")
    if missing:
        print(
            "\nPlace exported .onnx weights in edge/models/ and run:\n"
            "  uv run python cli.py --mode rtsp --rtsp-url rtsp://... "
            "--yolo-plate-model models/plate_detector.onnx "
            "--yolo-privacy-model models/privacy_person_face.onnx "
            "--ocr-model models/eu_plate_ocr.onnx"
        )
    return 0


if __name__ == "__main__":
    sys.exit(check_models())
