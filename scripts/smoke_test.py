from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.schemas import UserProfile
from app.services.image_utils import decode_image
from app.services.traditional import TraditionalVisionService


def main() -> None:
    image_path = ROOT / "data" / "samples" / "healthy_bowl_unsplash.jpg"
    result = TraditionalVisionService().assess(
        decode_image(image_path.read_bytes()),
        UserProfile(goal="fat_loss", context="post_workout"),
    )
    print(f"status={result.status}")
    print(f"device={result.metadata.get('device')}")
    print(f"foods={[(food.name, food.confidence) for food in result.foods]}")
    print(f"calories={result.totals.calories}")
    print(f"duration_ms={result.duration_ms}")


if __name__ == "__main__":
    main()