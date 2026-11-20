from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
from PIL import Image

from pipeline.redactor import BoundingBox


class OnnxSessionLike(Protocol):
    """Minimal protocol matching onnxruntime.InferenceSession for clean testability."""

    def get_inputs(self) -> list[Any]: ...
    def run(self, output_names: list[str] | None, input_feed: dict[str, np.ndarray]) -> list[np.ndarray]: ...


@dataclass(frozen=True)
class Detection:
    box: BoundingBox
    confidence: float
    class_id: int
    label: str


def create_onnx_session(model_path: str) -> OnnxSessionLike:
    """Load an ONNX model prioritizing Jetson TensorRT -> CUDA -> CPU execution providers."""
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError(
            "onnxruntime is required for live ONNX inference. "
            "Install via: uv pip install -r requirements-jetson-ml.txt"
        ) from exc

    available = set(ort.get_available_providers())
    preferred = [
        p
        for p in ("TensorrtExecutionProvider", "CUDAExecutionProvider", "CoreMLExecutionProvider", "CPUExecutionProvider")
        if p in available
    ]
    return ort.InferenceSession(model_path, providers=preferred or ["CPUExecutionProvider"])


def letterbox_image(
    image: Image.Image,
    *,
    input_size: int = 640,
    pad_color: tuple[int, int, int] = (114, 114, 114),
) -> tuple[np.ndarray, float, tuple[int, int]]:
    """
    Aspect-ratio preserving YOLO letterbox preprocessing.
    Returns (NCHW float32 tensor in [0, 1], scale_ratio, (pad_x, pad_y)).
    """
    rgb = image.convert("RGB")
    orig_w, orig_h = rgb.size
    scale = min(input_size / orig_w, input_size / orig_h)
    new_w, new_h = max(1, int(round(orig_w * scale))), max(1, int(round(orig_h * scale)))
    resized = rgb.resize((new_w, new_h), Image.Resampling.BILINEAR)

    canvas = Image.new("RGB", (input_size, input_size), pad_color)
    pad_x = (input_size - new_w) // 2
    pad_y = (input_size - new_h) // 2
    canvas.paste(resized, (pad_x, pad_y))

    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    chw = np.transpose(arr, (2, 0, 1))
    return np.expand_dims(chw, axis=0), scale, (pad_x, pad_y)


def nms_boxes(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float = 0.45) -> list[int]:
    """Vectorized NumPy Non-Maximum Suppression on [x1, y1, x2, y2] boxes."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = scores.argsort()[::-1]

    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0, inter / union, 0.0)
        order = rest[iou <= iou_threshold]
    return keep


class OnnxYoloDetector:
    """
    Production ONNX YOLO detector supporting YOLOv8/v11 ([1, 4+C, N]) and YOLOv5 ([1, N, 5+C]).
    Used for both license-plate localization and DSGVO face/person detection.
    """

    def __init__(
        self,
        session: OnnxSessionLike,
        *,
        class_names: dict[int, str],
        input_size: int = 640,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        target_class_ids: set[int] | None = None,
    ) -> None:
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.class_names = class_names
        self.input_size = input_size
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.target_class_ids = target_class_ids

    @classmethod
    def from_file(
        cls,
        model_path: str,
        *,
        class_names: dict[int, str],
        input_size: int = 640,
        conf_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        target_class_ids: set[int] | None = None,
    ) -> "OnnxYoloDetector":
        return cls(
            create_onnx_session(model_path),
            class_names=class_names,
            input_size=input_size,
            conf_threshold=conf_threshold,
            iou_threshold=iou_threshold,
            target_class_ids=target_class_ids,
        )

    def detect(self, image: Image.Image) -> list[Detection]:
        orig_w, orig_h = image.size
        tensor, scale, (pad_x, pad_y) = letterbox_image(image, input_size=self.input_size)
        raw_out = self.session.run(None, {self.input_name: tensor})[0]
        preds = self._normalize_yolo_output(raw_out, num_classes=max(1, len(self.class_names)))
        if preds.size == 0:
            return []

        cx, cy, bw, bh = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
        class_scores = preds[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confs = class_scores[np.arange(len(preds)), class_ids]

        mask = confs >= self.conf_threshold
        if self.target_class_ids is not None:
            mask &= np.isin(class_ids, list(self.target_class_ids))
        if not np.any(mask):
            return []

        cx, cy, bw, bh = cx[mask], cy[mask], bw[mask], bh[mask]
        confs, class_ids = confs[mask], class_ids[mask]

        # Convert center-xywh in letterbox coordinates back to original pixel xyxy
        x1 = np.clip((cx - bw / 2.0 - pad_x) / scale, 0, orig_w)
        y1 = np.clip((cy - bh / 2.0 - pad_y) / scale, 0, orig_h)
        x2 = np.clip((cx + bw / 2.0 - pad_x) / scale, 0, orig_w)
        y2 = np.clip((cy + bh / 2.0 - pad_y) / scale, 0, orig_h)
        boxes = np.stack([x1, y1, x2, y2], axis=1)

        keep = nms_boxes(boxes, confs, iou_threshold=self.iou_threshold)
        results: list[Detection] = []
        for idx in keep:
            cid = int(class_ids[idx])
            bx = BoundingBox(
                x1=int(round(boxes[idx, 0])),
                y1=int(round(boxes[idx, 1])),
                x2=int(round(boxes[idx, 2])),
                y2=int(round(boxes[idx, 3])),
            )
            if (bx.x2 - bx.x1) < 4 or (bx.y2 - bx.y1) < 4:
                continue
            results.append(
                Detection(
                    box=bx,
                    confidence=float(confs[idx]),
                    class_id=cid,
                    label=self.class_names.get(cid, str(cid)),
                )
            )
        return results

    @staticmethod
    def _normalize_yolo_output(raw: np.ndarray, *, num_classes: int = 1) -> np.ndarray:
        arr = np.asarray(raw, dtype=np.float32)
        if arr.ndim == 3:
            arr = arr[0]
        if arr.ndim != 2:
            return np.empty((0, 5), dtype=np.float32)
        v8_cols = 4 + num_classes
        v5_cols = 5 + num_classes
        # YOLOv8/v11 exports [4+C, N] (e.g. [5, 8400] or [84, 8400])
        if arr.shape[0] == v8_cols and arr.shape[1] != v8_cols and arr.shape[1] != v5_cols:
            return arr.T
        if arr.shape[0] < arr.shape[1] and arr.shape[0] <= 128:
            return arr.T
        # YOLOv5 exports [N, 5+C] with objectness at column 4 -> multiply obj * cls
        if arr.shape[1] == v5_cols:
            obj = arr[:, 4:5]
            cls = arr[:, 5:] * obj
            return np.concatenate([arr[:, :4], cls], axis=1)
        return arr
