from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name = "FoodCoach PlateLens"
    app_version = "0.1.0"

    def __init__(self) -> None:
        self.project_root = PROJECT_ROOT
        self.data_dir = PROJECT_ROOT / "data"
        self.nutrition_path = self.data_dir / "nutrition.csv"
        self.sample_dir = self.data_dir / "samples"
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///instance/foodcoach.db")
        self.uploads_dir = self._resolve_path(os.getenv("UPLOAD_DIR", "uploads"))
        self.redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
        self.queue_name = os.getenv("QUEUE_NAME", "foodcoach-assessments").strip()
        self.job_timeout_seconds = int(os.getenv("JOB_TIMEOUT_SECONDS", "900"))
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-only-change-me").strip()
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256").strip()
        self.jwt_expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

        self.yolo_model_path = self._resolve_path(
            os.getenv("YOLO_MODEL", "models/yolov8s-worldv2.pt")
        )
        self.sam_model_path = self._resolve_path(
            os.getenv("SAM_MODEL", "models/mobile_sam.pt")
        )
        self.device = os.getenv("DEVICE", "auto").strip().lower()
        self.detection_confidence = float(os.getenv("DETECTION_CONFIDENCE", "0.20"))
        self.detection_image_size = int(os.getenv("DETECTION_IMAGE_SIZE", "640"))

        self.vlm_api_key = (
            os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("VLM_API_KEY")
            or ""
        ).strip()
        self.vlm_base_url = os.getenv(
            "VLM_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ).strip()
        self.vlm_model = os.getenv("VLM_MODEL", "qwen3.8-omni-flash").strip()
        self.vlm_timeout_seconds = float(os.getenv("VLM_TIMEOUT_SECONDS", "90"))
        self.vlm_allow_mock = _as_bool(os.getenv("VLM_ALLOW_MOCK"), False)

        self.max_upload_mb = float(os.getenv("MAX_UPLOAD_MB", "12"))
        self.max_image_side = int(os.getenv("MAX_IMAGE_SIDE", "1280"))

    def _resolve_path(self, raw: str) -> Path:
        path = Path(raw)
        return path if path.is_absolute() else self.project_root / path

    @property
    def vlm_configured(self) -> bool:
        return bool(self.vlm_api_key)

    def resolved_device(self):
        if self.device in {"cpu", "cuda:0"}:
            return self.device
        if self.device != "auto":
            return self.device
        try:
            import torch

            return 0 if torch.cuda.is_available() else "cpu"
        except (ImportError, OSError, RuntimeError):
            return "cpu"


settings = Settings()
