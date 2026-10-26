import pytest

from app.catalog import load_catalog
from app.nutrition import calculate_nutrition, total_nutrition
from app.partial_helpers import build_food
from app.rule_engine import estimate_targets, evaluate_meal
from app.schemas import FoodItem, Goal, MealContext, UserProfile


def test_catalog_has_expected_size():
    assert 15 <= len(load_catalog()) <= 20


def test_nutrition_scales_per_100g():
    chicken = next(item for item in load_catalog() if item.food_id == "chicken_breast")
    nutrition = calculate_nutrition(chicken, 200)
    assert nutrition.calories == 330
    assert nutrition.protein_g == 62.0


def test_targets_respond_to_goal_and_context():
    maintain = estimate_targets(UserProfile(weight_kg=70, goal=Goal.MAINTAIN))
    cutting = estimate_targets(UserProfile(weight_kg=70, goal=Goal.FAT_LOSS))
    snack = estimate_targets(UserProfile(weight_kg=70, context=MealContext.SNACK))
    assert cutting.meal_calories < maintain.meal_calories
    assert snack.meal_calories < maintain.meal_calories


def test_high_calorie_meal_is_stated_honestly():
    chicken = next(item for item in load_catalog() if item.food_id == "chicken_breast")
    rice = next(item for item in load_catalog() if item.food_id == "rice")
    foods = [
        build_food(chicken, 300, "鸡胸肉"),
        build_food(rice, 500, "米饭"),
    ]
    totals = total_nutrition(foods)
    profile = UserProfile(weight_kg=60, goal=Goal.FAT_LOSS)
    verdict, advice, note, metadata = evaluate_meal(totals, profile, foods)
    assert verdict.calorie_status == "超标"
    assert "下一顿" in advice[0]
    assert "单顿不决定结果" in note
    assert metadata["target"]["estimate_only"] is True


def test_invalid_bbox_rejected():
    with pytest.raises(ValueError):
        FoodItem(
            name="米饭",
            confidence=0.8,
            bbox=[1, 2, 3],
            nutrition={"calories": 100, "protein_g": 2, "carbs_g": 20, "fat_g": 1},
            verdict={
                "calorie_status": "适中",
                "protein_status": "不足",
                "carb_ratio": "适中",
                "summary": "测试",
            },
        )