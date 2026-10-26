from __future__ import annotations

import math

from app.catalog import FoodRecord


def estimate_portion(
    record: FoodRecord,
    mask_area_ratio: float | None,
    plate_diameter_cm: float,
    plate_image_coverage: float = 0.65,
) -> tuple[list[float], float]:
    """Estimate grams from mask area with explicit, reproducible assumptions."""
    ratio = max(0.0, mask_area_ratio or 0.0)
    plate_coverage = min(0.95, max(0.2, plate_image_coverage))
    plate_area_cm2 = math.pi * (plate_diameter_cm / 2) ** 2
    food_area_cm2 = plate_area_cm2 * ratio / plate_coverage
    grams = food_area_cm2 * record.thickness_cm * record.density_g_per_cm3

    # Keep impossible area/segmentation failures from producing absurd output.
    lower_limit = max(3.0, record.min_grams * 0.25)
    upper_limit = max(record.max_grams * 1.5, record.default_grams * 3)
    grams = min(upper_limit, max(lower_limit, grams))
    return [round(grams * 0.7, 1), round(grams * 1.3, 1)], round(grams, 1)