from __future__ import annotations

import base64
import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


class InvalidImageError(ValueError):
    pass


def decode_image(raw: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            return np.asarray(image)
    except Exception as exc:
        raise InvalidImageError("无法读取图片，请上传 JPG、PNG 或 WebP 格式。") from exc


def resize_for_upload(image: np.ndarray, max_side: int = 1280) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(1.0, max_side / max(height, width))
    if scale == 1.0:
        return image
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def image_to_jpeg_bytes(image: np.ndarray, quality: int = 86) -> bytes:
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("图片编码失败")
    return encoded.tobytes()


def image_to_data_url(image: np.ndarray, max_side: int = 1280) -> str:
    payload = base64.b64encode(image_to_jpeg_bytes(resize_for_upload(image, max_side))).decode("ascii")
    return f"data:image/jpeg;base64,{payload}"


def image_file_to_data_url(path: Path, max_side: int = 1280) -> str:
    return image_to_data_url(decode_image(path.read_bytes()), max_side=max_side)


def image_to_base64_png(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("图片编码失败")
    return base64.b64encode(encoded.tobytes()).decode("ascii")