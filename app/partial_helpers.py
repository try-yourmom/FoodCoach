from __future__ import annotations

from app.catalog import FoodRecord
from app.nutrition import calculate_nutrition, provisional_verdict
from app.schemas import FoodItem


def build_food(record: FoodRecord, grams: float, name: str | None = None) -> FoodItem:
    nutrition = calculate_nutrition(record, grams)
    display_name = name or record.name
    return FoodItem(
        name=display_name,
        confidence=0.9,
        bbox=[10, 10, 100, 100],
        mask_area_ratio=0.1,
        estimated_grams=[round(grams * 0.8, 1), round(grams * 1.2, 1)],
        nutrition=nutrition,
        verdict=provisional_verdict(display_name, nutrition),
        source_id=record.food_id,
    )