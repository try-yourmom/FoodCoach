from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Goal(str, Enum):
    FAT_LOSS = "fat_loss"
    MUSCLE_GAIN = "muscle_gain"
    MAINTAIN = "maintain"


class MealContext(str, Enum):
    PRE_WORKOUT = "pre_workout"
    POST_WORKOUT = "post_workout"
    REST_DAY = "rest_day"
    SNACK = "snack"


class UserProfile(BaseModel):
    height_cm: float = Field(default=170, ge=100, le=250)
    weight_kg: float = Field(default=65, ge=30, le=300)
    body_fat_pct: float | None = Field(default=None, ge=3, le=60)
    goal: Goal = Goal.MAINTAIN
    context: MealContext = MealContext.REST_DAY
    plate_diameter_cm: float = Field(default=26, ge=15, le=45)


class NutritionEstimate(BaseModel):
    calories: int = Field(ge=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)
    note: str = "估算值"


class FoodVerdict(BaseModel):
    calorie_status: str
    protein_status: str
    carb_ratio: str
    summary: str


class FoodItem(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] | None = None
    mask_area_ratio: float | None = Field(default=None, ge=0, le=1)
    estimated_grams: list[float] | None = None
    nutrition: NutritionEstimate
    verdict: FoodVerdict
    source_id: str | None = None

    @field_validator("bbox")
    @classmethod
    def validate_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("bbox must contain [x, y, width, height]")
        if any(item < 0 for item in value):
            raise ValueError("bbox coordinates must be non-negative")
        return [round(float(item), 2) for item in value]

    @field_validator("estimated_grams")
    @classmethod
    def validate_grams(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 2 or value[0] > value[1]:
            raise ValueError("estimated_grams must be [minimum, maximum]")
        return [round(max(0, float(item)), 1) for item in value]


class MealTotals(BaseModel):
    calories: int = Field(default=0, ge=0)
    protein_g: float = Field(default=0, ge=0)
    carbs_g: float = Field(default=0, ge=0)
    fat_g: float = Field(default=0, ge=0)


class MealVerdict(BaseModel):
    calorie_status: str
    protein_status: str
    carb_ratio: str
    summary: str


class MethodResult(BaseModel):
    method: Literal["traditional", "vlm"]
    status: Literal["ok", "degraded", "error"] = "ok"
    foods: list[FoodItem] = Field(default_factory=list)
    totals: MealTotals = Field(default_factory=MealTotals)
    verdict: MealVerdict
    advice: list[str] = Field(default_factory=list, min_length=1)
    long_term_note: str
    disclaimer: str = "仅供学习参考，不构成医疗或营养建议。"
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)
    overlay_image_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComparisonRow(BaseModel):
    dimension: str
    traditional: str
    vlm: str
    conclusion: str


class ComparisonReport(BaseModel):
    rows: list[ComparisonRow]
    summary: str
    recommended_use: str


class AssessmentBundle(BaseModel):
    request_id: str
    traditional: MethodResult
    vlm: MethodResult
    comparison: ComparisonReport
    profile: UserProfile


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None


class VLMNutritionPayload(BaseModel):
    calories: float = Field(ge=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)


class VLMFoodPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    confidence: float = Field(default=0.5, ge=0, le=1)
    bbox: list[float] | None = None
    estimated_grams: list[float] | None = None
    nutrition: VLMNutritionPayload
    note: str = ""


class VLMResponsePayload(BaseModel):
    foods: list[VLMFoodPayload] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
    long_term_note: str = ""
    disclaimer: str = "仅供学习参考，不构成医疗或营养建议。"
    warnings: list[str] = Field(default_factory=list)

    @field_validator("foods")
    @classmethod
    def limit_foods(cls, value: list[VLMFoodPayload]) -> list[VLMFoodPayload]:
        return value[:20]

    @model_validator(mode="after")
    def ensure_text(self):
        if not self.advice:
            self.advice = ["下一餐优先补充蛋白质和蔬菜，并保持正常饮食节奏。"]
        if not self.long_term_note:
            self.long_term_note = "单顿不决定结果，关注连续多天的整体趋势。"
        return self