from __future__ import annotations

from dataclasses import dataclass

from app.schemas import (
    FoodItem,
    Goal,
    MealContext,
    MealTotals,
    MealVerdict,
    UserProfile,
)

DISCLAIMER = "仅供学习参考，不构成医疗或营养建议。"


@dataclass(frozen=True)
class TargetEstimate:
    daily_calories: int
    meal_calories: int
    meal_protein_g: float


def estimate_targets(profile: UserProfile) -> TargetEstimate:
    calorie_factor = {
        Goal.FAT_LOSS: 25.0,
        Goal.MAINTAIN: 30.0,
        Goal.MUSCLE_GAIN: 33.0,
    }[profile.goal]
    protein_factor = {
        Goal.FAT_LOSS: 1.8,
        Goal.MAINTAIN: 1.5,
        Goal.MUSCLE_GAIN: 1.8,
    }[profile.goal]
    context_factor = {
        MealContext.PRE_WORKOUT: 0.8,
        MealContext.POST_WORKOUT: 1.15,
        MealContext.REST_DAY: 1.0,
        MealContext.SNACK: 0.5,
    }[profile.context]
    daily_calories = profile.weight_kg * calorie_factor
    meal_calories = daily_calories / 3 * context_factor
    meal_protein = profile.weight_kg * protein_factor / 3 * context_factor
    return TargetEstimate(
        daily_calories=round(daily_calories),
        meal_calories=round(meal_calories),
        meal_protein_g=round(meal_protein, 1),
    )


def evaluate_meal(
    totals: MealTotals,
    profile: UserProfile,
    foods: list[FoodItem],
) -> tuple[MealVerdict, list[str], str, dict]:
    target = estimate_targets(profile)
    calorie_ratio = totals.calories / max(1, target.meal_calories)
    protein_ratio = totals.protein_g / max(1, target.meal_protein_g)
    carb_calories = totals.carbs_g * 4
    carb_share = carb_calories / max(1, totals.calories)

    calorie_status = (
        "超标" if calorie_ratio > 1.15 else "不足" if calorie_ratio < 0.7 else "适中"
    )
    protein_status = (
        "充足" if protein_ratio >= 0.9 else "不足" if protein_ratio < 0.7 else "接近目标"
    )
    carb_limit = 0.55 if profile.goal == Goal.FAT_LOSS else 0.60
    carb_ratio_status = "偏高" if carb_share > carb_limit else "适中"

    dominant = max(foods, key=lambda item: item.nutrition.calories, default=None)
    dominant_text = (
        f"热量主要来自{dominant.name}（约 {dominant.nutrition.calories} kcal）。"
        if dominant
        else "没有识别到支持范围内的食物。"
    )
    summary = (
        f"本餐估算约 {totals.calories} kcal、蛋白质 {totals.protein_g:g} g，"
        f"单餐参考值约 {target.meal_calories} kcal / {target.meal_protein_g:g} g 蛋白质；"
        f"热量{calorie_status}，蛋白质{protein_status}，碳水占比{carb_ratio_status}。"
        f"{dominant_text}"
    )

    advice: list[str] = []
    if not foods:
        advice.append("请换用俯拍、光线均匀且完整包含餐盘的照片后重试。")
    elif calorie_status == "超标":
        advice.append("下一顿主食减半，优先补充蛋白质和蔬菜，不需要通过节食补偿这一餐。")
    elif protein_status == "不足":
        advice.append("下一顿增加一掌心大小的瘦肉、鱼虾、鸡蛋或豆腐。")
    elif carb_ratio_status == "偏高":
        advice.append("下一顿减少约四分之一主食，并增加一份非淀粉类蔬菜。")
    elif calorie_status == "不足" and profile.context != MealContext.SNACK:
        advice.append("若这是正餐，可补充一份蛋白质和少量主食，避免后续过度饥饿。")
    else:
        advice.append("下一顿保持正常节奏，优先蛋白质和蔬菜即可。")

    if len(advice) == 1 and protein_status == "不足" and calorie_status != "超标":
        advice.append("同时保持饮水，不需要用高糖饮料补充能量。")

    long_term_note = (
        "单顿不决定结果，但这一餐的事实需要看见；连续记录一周以上的趋势更有参考价值。"
    )
    metadata = {
        "target": {
            "daily_calories": target.daily_calories,
            "meal_calories": target.meal_calories,
            "meal_protein_g": target.meal_protein_g,
            "estimate_only": True,
        },
        "calorie_ratio": round(calorie_ratio, 3),
        "protein_ratio": round(protein_ratio, 3),
        "carb_calorie_share": round(carb_share, 3),
    }
    verdict = MealVerdict(
        calorie_status=calorie_status,
        protein_status=protein_status,
        carb_ratio=carb_ratio_status,
        summary=summary,
    )
    return verdict, advice, long_term_note, metadata


def enrich_food_verdicts(
    foods: list[FoodItem],
    verdict: MealVerdict,
    profile: UserProfile,
) -> None:
    target = estimate_targets(profile)
    for food in foods:
        carb_share = food.nutrition.carbs_g * 4 / max(1, food.nutrition.calories)
        food.verdict = food.verdict.model_copy(
            update={
                "calorie_status": verdict.calorie_status,
                "protein_status": (
                    "充足"
                    if food.nutrition.protein_g >= target.meal_protein_g * 0.3
                    else "偏少"
                ),
                "carb_ratio": "偏高" if carb_share >= 0.65 else "适中",
                "summary": (
                    f"{food.name}约提供 {food.nutrition.calories} kcal、"
                    f"{food.nutrition.protein_g:g} g 蛋白质；整餐判断见上方结论。"
                ),
            }
        )