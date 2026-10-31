from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.schemas import UserProfile
from app.services.comparison import build_comparison
from app.services.image_utils import decode_image
from app.services.traditional import TraditionalVisionService
from app.services.vlm import VLMService


def main() -> None:
    image_path = ROOT / "data" / "samples" / "healthy_bowl_unsplash.jpg"
    output_path = ROOT / "docs" / "examples" / "example_output.json"
    profile = UserProfile(weight_kg=65, goal="fat_loss", context="post_workout")
    image = decode_image(image_path.read_bytes())
    traditional = TraditionalVisionService().assess(image, profile)
    vlm = VLMService().assess(image, profile)
    traditional.overlay_image_base64 = None
    payload = {
        "input": {
            "image": str(image_path.relative_to(ROOT)).replace("\\", "/"),
            "profile": profile.model_dump(mode="json"),
        },
        "traditional": traditional.model_dump(mode="json"),
        "vlm": vlm.model_dump(mode="json"),
        "comparison": build_comparison(traditional, vlm).model_dump(mode="json"),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()