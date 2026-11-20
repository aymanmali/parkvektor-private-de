from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFilter


@dataclass(frozen=True)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    def clamped(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            max(0, min(self.x1, width)),
            max(0, min(self.y1, height)),
            max(0, min(self.x2, width)),
            max(0, min(self.y2, height)),
        )


def _irreversible_blur_box(img: Image.Image, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    if bw < 2 or bh < 2:
        return
    region = img.crop((x1, y1, x2, y2))
    # Strong downscale pixelation + Gaussian blur makes facial/text recovery mathematically infeasible
    small = region.resize((max(1, bw // 16), max(1, bh // 16)), Image.Resampling.BILINEAR)
    pixelated = small.resize((bw, bh), Image.Resampling.NEAREST)
    blurred = pixelated.filter(ImageFilter.GaussianBlur(radius=5))
    img.paste(blurred, (x1, y1, x2, y2))


def redact_frame_in_ram(
    image: Image.Image,
    *,
    face_or_person_boxes: list[BoundingBox] | None = None,
    bystander_plate_boxes: list[BoundingBox] | None = None,
    blur_upper_windshield: bool = True,
) -> bytes:
    """
    DSGVO Privacy-by-Design Edge Redactor:
    Applies irreversible blurring IN MEMORY before a single byte is encoded or written to disk.
    1. Blurs all detected faces/pedestrians.
    2. Blurs all non-target bystander license plates.
    3. Optionally blurs the upper 55% windshield/cabin region so driver/passengers are never identifiable.
    """
    rgb = image.convert("RGB").copy()
    w, h = rgb.size

    if blur_upper_windshield:
        _irreversible_blur_box(rgb, (0, 0, w, int(h * 0.55)))

    for box in face_or_person_boxes or []:
        _irreversible_blur_box(rgb, box.clamped(w, h))

    for box in bystander_plate_boxes or []:
        _irreversible_blur_box(rgb, box.clamped(w, h))

    out = BytesIO()
    rgb.save(out, format="JPEG", quality=82, optimize=True)
    return out.getvalue()


def extract_plate_crop_jpeg(image: Image.Image, plate_box: BoundingBox) -> bytes:
    rgb = image.convert("RGB")
    w, h = rgb.size
    crop = rgb.crop(plate_box.clamped(w, h))
    out = BytesIO()
    crop.save(out, format="JPEG", quality=90)
    return out.getvalue()
