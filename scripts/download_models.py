from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import settings


def main() -> None:
    settings.yolo_model_path.parent.mkdir(parents=True, exist_ok=True)
    settings.sam_model_path.parent.mkdir(parents=True, exist_ok=True)

    from ultralytics import SAM, YOLO

    print(f"YOLO-World: {settings.yolo_model_path}")
    YOLO(str(settings.yolo_model_path))
    print("YOLO-World loaded.")

    print(f"MobileSAM: {settings.sam_model_path}")
    SAM(str(settings.sam_model_path))
    print("MobileSAM loaded.")


if __name__ == "__main__":
    main()