from __future__ import annotations

import base64
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.schemas import UserProfile
from app.services.image_utils import decode_image
from app.services.traditional import TraditionalVisionService


def group_for(path: Path) -> str:
    match = re.search(r"餐(\d+)", path.stem)
    if not match:
        return "other"
    number = int(match.group(1))
    if number in {1, 2, 3, 4, 5, 6, 11}:
        return "school_mixed"
    if 7 <= number <= 9:
        return "yolo_friendly"
    return "other"


def main() -> None:
    sample_dir = ROOT / "data" / "samples"
    report_dir = ROOT / "reports" / "traditional_eval"
    overlay_dir = report_dir / "overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    images = sorted(
        (item for item in sample_dir.glob("餐*.jpg") if item.stem != "餐盘"),
        key=lambda item: int(re.search(r"餐(\d+)", item.stem).group(1)),
    )
    if not images:
        raise SystemExit("No numbered sample images found.")

    service = TraditionalVisionService()
    profile = UserProfile(weight_kg=65, goal="fat_loss", context="post_workout")
    rows: list[dict] = []
    details: list[dict] = []
    durations: dict[str, list[int]] = defaultdict(list)

    for image_path in images:
        image = decode_image(image_path.read_bytes())
        result = service.assess(image, profile)
        group = group_for(image_path)
        durations[group].append(result.duration_ms)
        if result.overlay_image_base64:
            overlay_path = overlay_dir / f"{image_path.stem}_overlay.png"
            overlay_path.write_bytes(base64.b64decode(result.overlay_image_base64))
        row = {
            "group": group,
            "image": image_path.name,
            "height": image.shape[0],
            "width": image.shape[1],
            "status": result.status,
            "detection_count": len(result.foods),
            "foods": " | ".join(f"{food.name}({food.confidence:.2f})" for food in result.foods),
            "calories": result.totals.calories,
            "protein_g": result.totals.protein_g,
            "carbs_g": result.totals.carbs_g,
            "fat_g": result.totals.fat_g,
            "duration_ms": result.duration_ms,
            "warnings": " | ".join(result.warnings),
        }
        rows.append(row)
        detail = result.model_dump(mode="json")
        detail["overlay_image_base64"] = None
        details.append(
            {
                "group": group,
                "image": image_path.name,
                "result": detail,
            }
        )
        print(
            f"{image_path.name} [{group}] foods={row['foods'] or 'NONE'} "
            f"kcal={result.totals.calories} time={result.duration_ms}ms"
        )

    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "per_image.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (report_dir / "results.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary_lines = ["# 传统方案批量评测", "", "## 分组汇总", ""]
    summary_lines.append("| 分组 | 图片数 | 有识别结果 | 平均识别数 | 平均耗时 |")
    summary_lines.append("|---|---:|---:|---:|---:|")
    for group in sorted(durations):
        group_rows = [row for row in rows if row["group"] == group]
        detected = sum(1 for row in group_rows if row["detection_count"] > 0)
        avg_count = sum(row["detection_count"] for row in group_rows) / len(group_rows)
        avg_time = sum(durations[group]) / len(durations[group]) / 1000
        summary_lines.append(
            f"| {group} | {len(group_rows)} | {detected} | {avg_count:.2f} | {avg_time:.2f}s |"
        )
    summary_lines.extend(
        [
            "",
            "## 逐图结果",
            "",
            "| 图片 | 分组 | 识别数 | 食物 | 热量 | 耗时 |",
            "|---|---|---:|---|---:|---:|",
        ]
    )
    for row in rows:
        summary_lines.append(
            f"| {row['image']} | {row['group']} | {row['detection_count']} | "
            f"{row['foods'] or '无'} | {row['calories']} | {row['duration_ms'] / 1000:.2f}s |"
        )
    (report_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    print(f"REPORT={report_dir}")


if __name__ == "__main__":
    main()