import re
from dataclasses import dataclass

import numpy as np
from PIL import Image

from pipeline.onnx_yolo import OnnxSessionLike, create_onnx_session
from plates.de_eu import normalize_edge_plate

# Default EU/German FE-Schrift alphabet (0-9, A-Z, German umlauts, padding/blank '_')
EU_DE_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ_"

_TO_LETTER = {"0": "O", "1": "I", "2": "Z", "4": "A", "5": "S", "6": "G", "8": "B"}
_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "A": "4", "S": "5", "G": "6", "B": "8"}

# Structured German plate split: [district 1-3] [sep] [letters 1-2] [sep] [digits 1-4] [optional E/H]
_SEPARATED_DE = re.compile(r"^([A-ZÄÖÜ0-9]{1,3})[\s\-]+([A-Z0-9]{1,2})[\s\-]*([A-Z0-9]{1,4})([EH])?$")


@dataclass(frozen=True)
class OCRPrediction:
    text_raw: str
    text_corrected: str
    confidence: float
    sharpness_score: float


def compute_sharpness_score(crop: Image.Image) -> float:
    """
    Estimate plate crop sharpness via 2D discrete Laplacian variance (normalized to [0.1, 2.0]).
    Motion-blurred frames receive low weight inside MultiFramePlateVoter.
    """
    gray = np.asarray(crop.convert("L"), dtype=np.float32)
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.5
    lap = (
        -4.0 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
    )
    variance = float(np.var(lap))
    # Typical crisp plate crops have variance ~150-800+; blurry frames < 40
    return round(float(np.clip(variance / 250.0, 0.1, 2.0)), 3)


def apply_german_positional_ocr_fix(raw_text: str) -> str:
    """
    StVZO / FE-Schrift positional OCR correction:
    - District & middle letter groups strictly contain letters (convert stray 0->O, 8->B, 1->I).
    - Numeric block strictly contains digits (convert stray O->0, B->8, I->1, S->5).
    - Preserves EV ('E') and Historic ('H') suffixes untouched.
    """
    cleaned = re.sub(r"\s+", " ", raw_text.strip().upper())
    m = _SEPARATED_DE.match(cleaned)
    if not m:
        return normalize_edge_plate(cleaned).display

    dist, mid, digits, suffix = m.groups()
    fixed_dist = "".join(_TO_LETTER.get(ch, ch) for ch in dist)
    fixed_mid = "".join(_TO_LETTER.get(ch, ch) for ch in mid)
    fixed_digits = "".join(_TO_DIGIT.get(ch, ch) for ch in digits)
    suffix = suffix or ""
    candidate = f"{fixed_dist}-{fixed_mid} {fixed_digits}{suffix}"
    return normalize_edge_plate(candidate).display


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=-1, keepdims=True)
    exps = np.exp(shifted)
    return exps / np.sum(exps, axis=-1, keepdims=True)


class OnnxPlateOCR:
    """
    Production ONNX EU/German license plate OCR engine supporting:
    - `slot` mode (e.g. fast-plate-ocr european-plates-mobile-vit-v2: [1, max_slots, vocab])
    - `ctc` mode (e.g. PaddleOCR / CRNN sequence decoder: [1, timesteps, vocab] with blank collapse)
    """

    def __init__(
        self,
        session: OnnxSessionLike,
        *,
        alphabet: str = EU_DE_ALPHABET,
        mode: str = "slot",  # "slot" | "ctc"
        input_width: int = 128,
        input_height: int = 64,
        blank_char: str = "_",
        nchw: bool = False,
    ) -> None:
        self.session = session
        self.input_name = session.get_inputs()[0].name
        self.alphabet = alphabet
        self.mode = mode
        self.input_width = input_width
        self.input_height = input_height
        self.blank_char = blank_char
        self.nchw = nchw

    @classmethod
    def from_file(cls, model_path: str, **kwargs) -> "OnnxPlateOCR":
        return cls(create_onnx_session(model_path), **kwargs)

    def _preprocess(self, crop: Image.Image) -> np.ndarray:
        rgb = crop.convert("RGB").resize((self.input_width, self.input_height), Image.Resampling.BILINEAR)
        arr = np.asarray(rgb, dtype=np.float32) / 255.0
        if self.nchw:
            arr = np.transpose(arr, (2, 0, 1))
        return np.expand_dims(arr, axis=0)

    def read_plate(self, plate_crop: Image.Image) -> OCRPrediction:
        sharpness = compute_sharpness_score(plate_crop)
        inp = self._preprocess(plate_crop)
        raw_logits = np.asarray(self.session.run(None, {self.input_name: inp})[0], dtype=np.float32)

        # Normalize to [slots/timesteps, vocab]
        if raw_logits.ndim == 3:
            logits = raw_logits[0]
        elif raw_logits.ndim == 2:
            # Some fast-plate-ocr exports flatten [1, slots * vocab] -> reshape cleanly
            vocab_len = len(self.alphabet)
            if raw_logits.shape[0] == 1 and raw_logits.shape[1] % vocab_len == 0:
                logits = raw_logits.reshape(-1, vocab_len)
            else:
                logits = raw_logits
        else:
            return OCRPrediction("", "", 0.0, sharpness)

        probs = _softmax(logits)
        indices = np.argmax(probs, axis=-1)
        max_probs = probs[np.arange(len(indices)), indices]

        chars: list[str] = []
        char_confs: list[float] = []
        prev_idx: int | None = None
        blank_idx = self.alphabet.find(self.blank_char)

        for idx, prob in zip(indices.tolist(), max_probs.tolist(), strict=True):
            if idx >= len(self.alphabet):
                continue
            if self.mode == "ctc":
                if idx != blank_idx and idx != prev_idx:
                    chars.append(self.alphabet[idx])
                    char_confs.append(prob)
                prev_idx = idx
            else:
                ch = self.alphabet[idx]
                if ch != self.blank_char:
                    chars.append(ch)
                    char_confs.append(prob)

        raw_text = "".join(chars).strip()
        corrected = apply_german_positional_ocr_fix(raw_text) if raw_text else ""
        mean_conf = float(np.mean(char_confs)) if char_confs else 0.0
        return OCRPrediction(
            text_raw=raw_text,
            text_corrected=corrected,
            confidence=round(min(max(mean_conf, 0.0), 1.0), 4),
            sharpness_score=sharpness,
        )
