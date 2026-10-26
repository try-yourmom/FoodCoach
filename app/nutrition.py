from __future__ import annotations

from app.catalog import FoodRecord
from app.schemas import FoodVerdict, MealTotals, NutritionEstimate


def calculate_nutrition(record: FoodRecord, grams: float) -> NutritionEstimate:
    ratio = max(0.0, grams) / 100.0
    return NutritionEstimate(
        calories=round(record.calories_per_100g * ratio),
        protein_g=round(record.protein_g_per_100g * ratio, 1),
        carbs_g=round(record.carbs_g_per_100g * ratio, 1),
        fat_g=round(record.fat_g_per_100g * ratio, 1),
        note="按食物参考值估算，实际值受烹饪用油和分量影响",
    )


def total_nutrition(items: list) -> MealTotals:
    return MealTotals(
        calories=round(sum(item.nutrition.calories for item in items)),
        protein_g=round(sum(item.nutrition.protein_g for item in items), 1),
        carbs_g=round(sum(item.nutrition.carbs_g for item in items), 1),
        fat_g=round(sum(item.nutrition.fat_g for item in items), 1),
    )


def provisional_verdict(name: str, nutrition: NutritionEstimate) -> FoodVerdict:
    kcal_from_carbs = nutrition.carbs_g * 4
    kcal_total = max(1, nutrition.calories)
    carb_share = kcal_from_carbs / kcal_total
    return FoodVerdict(
        calorie_status="待整餐判断",
        protein_status="充足" if nutrition.protein_g >= 10 else "偏少",
        carb_ratio="偏高" if carb_share >= 0.65 else "适中",
        summary=f"{name}约提供 {nutrition.calories} kcal。",
    )