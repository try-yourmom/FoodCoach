from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import PROJECT_ROOT
from app.schemas import AssessmentBundle, MethodResult, UserProfile, VLMResponsePayload


def export_schemas(output_dir: Path | None = None) -> list[Path]:
    target = output_dir or PROJECT_ROOT / "docs" / "schemas"
    target.mkdir(parents=True, exist_ok=True)
    exports = {
        "assessment_bundle.schema.json": AssessmentBundle.model_json_schema(),
        "method_result.schema.json": MethodResult.model_json_schema(),
        "user_profile.schema.json": UserProfile.model_json_schema(),
        "vlm_response.schema.json": VLMResponsePayload.model_json_schema(),
    }
    written: list[Path] = []
    for filename, schema in exports.items():
        path = target / filename
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for item in export_schemas():
        print(item)