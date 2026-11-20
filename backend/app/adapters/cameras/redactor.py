import base64
from io import BytesIO

from PIL import Image, ImageFilter


def decode_and_redact_context_image(image_b64: str, *, already_redacted: bool) -> bytes:
    """
    Server-side DSGVO fallback redactor for Smart ANPR camera webhooks that cannot
    mask windshields/passengers on-device. Blurs the upper 60% of the vehicle frame
    (windshield / driver / bystander zone) irreversibly in memory while keeping the
    lower bumper/plate context verifiable.
    """
    raw_bytes = base64.b64decode(image_b64)
    if already_redacted:
        return raw_bytes

    with Image.open(BytesIO(raw_bytes)) as img:
        rgb = img.convert("RGB")
        w, h = rgb.size
        # Blur upper 60% (windshield, driver/passenger faces, pedestrians behind car)
        upper_box = (0, 0, w, int(h * 0.60))
        region = rgb.crop(upper_box)
        # Strong pixelation + Gaussian blur makes face reconstruction impossible
        small = region.resize((max(1, w // 24), max(1, int(h * 0.60) // 24)), Image.Resampling.BILINEAR)
        pixelated = small.resize(region.size, Image.Resampling.NEAREST)
        blurred = pixelated.filter(ImageFilter.GaussianBlur(radius=6))
        rgb.paste(blurred, upper_box)

        out = BytesIO()
        rgb.save(out, format="JPEG", quality=82, optimize=True)
        return out.getvalue()


def decode_plate_crop(image_b64: str) -> bytes:
    return base64.b64decode(image_b64)
