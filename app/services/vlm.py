from __future__ import annotations

import hashlib
import json
import re
import time
from collections import OrderedDict
from typing import Any

import numpy as np
from pydantic import ValidationError

from app.catalog import find_food
from app.config import settings
from app.nutrition import provisional_verdict, total_nutrition
from app.prompts.meal_assessment import build_meal_prompt, build_repair_prompt
from app.rule_engine import DISCLAIMER, enrich_food_verdicts, evaluate_meal
from app.schemas import (
    FoodItem,
    MethodResult,
    NutritionEstimate,
    UserProfile,
    VLMResponsePayload,
)
from app.services.image_utils import image_to_data_url

BANNED_PHRASES = ("失败", "白练", "超标可耻", "自律失败")
LOCAL_IMAGE_CACHE: OrderedDict[str, Any] = OrderedDict()
MAX_CACHE_ITEMS = 32


class VLMService:
    def __init__(self) -> None:
        self.prompt_version = "plate-lens-v1"

    @property
    def configured(self) -> bool:
        return settings.vlm_configured

    def assess(self, image_rgb: np.ndarray, profile: UserProfile) -> MethodResult:
        started = time.perf_counter()
        cache_key = self._cache_key(image_rgb, profile)
        if cache_key in LOCAL_IMAGE_CACHE:
            cached = LOCAL_IMAGE_CACHE.pop(cache_key)
            LOCAL_IMAGE_CACHE[cache_key] = cached
            return cached.model_copy(update={"duration_ms": 0, "metadata": {**cached.metadata, "cache_hit": True}})

        if not self.configured:
            result = self._error_result(
                "未配置多模态 API Key。请设置 DASHSCOPE_API_KEY 后重试；当前不会伪造大模型结果。",
                started,
            )
        else:
            try:
                result = self._call_with_repair(image_rgb, profile, started)
            except Exception as exc:  # noqa: BLE001
                result = self._error_result(f"多模态模型调用失败：{type(exc).__name__}: {exc}", started)

        LOCAL_IMAGE_CACHE[cache_key] = result
        while len(LOCAL_IMAGE_CACHE) > MAX_CACHE_ITEMS:
            LOCAL_IMAGE_CACHE.popitem(last=False)
        return result

    def _call_with_repair(self, image_rgb: np.ndarray, profile: UserProfile, started: float) -> MethodResult:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.vlm_api_key,
            base_url=settings.vlm_base_url,
            timeout=settings.vlm_timeout_seconds,
        )
        image_url = image_to_data_url(image_rgb, max_side=settings.max_image_side)
        prompt = build_meal_prompt(profile)
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        last_error = "未知错误"
        raw = ""
        for attempt in range(1, 3):
            response = self._request(client, messages)
            raw = self._response_text(response)
            try:
                payload = self._parse_payload(raw)
                return self._to_method_result(payload, profile, started, attempt, settings.vlm_model)
            except (ValueError, ValidationError) as exc:
                last_error = str(exc)
                if attempt == 1:
                    messages = [{"role": "user", "content": [{"type": "text", "text": build_repair_prompt(raw, last_error)}]}]
        return self._error_result(f"多模态模型连续两次返回无效 JSON：{last_error}", started)
    def _request(self, client, messages: list[dict[str, Any]]):
        kwargs = {
            "model": settings.vlm_model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2400,
        }
        if "omni" in settings.vlm_model.lower():
            # Omni models distinguish output modalities; PlateLens only needs text.
            kwargs["modalities"] = ["text"]
            # The model's default thinking mode is unnecessarily slow for a
            # bounded JSON extraction task.
            kwargs["extra_body"] = {"enable_thinking": False}
        try:
            return client.chat.completions.create(response_format={"type": "json_object"}, **kwargs)
        except Exception as exc:
            text = str(exc).lower()
            if "response_format" not in text and "json_object" not in text and "bad request" not in text:
                raise
            return client.chat.completions.create(**kwargs)

    @staticmethod
    def _response_text(response) -> str:
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
                elif hasattr(item, "text"):
                    chunks.append(str(item.text))
            return "".join(chunks).strip()
        return str(content).strip()

    @staticmethod
    def _parse_payload(raw: str) -> VLMResponsePayload:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end < start:
            raise ValueError("响应中没有 JSON 对象")
        data = json.loads(cleaned[start : end + 1])
        return VLMResponsePayload.model_validate(data)

    def _to_method_result(
        self,
        payload: VLMResponsePayload,
        profile: UserProfile,
        started: float,
        attempts: int,
        model: str,
    ) -> MethodResult:
        warnings = list(payload.warnings)
        foods: list[FoodItem] = []
        for item in payload.foods:
            bbox = None
            if item.bbox and len(item.bbox) == 4 and all(0 <= value <= 1 for value in item.bbox):
                bbox = item.bbox
            nutrition = NutritionEstimate(
                calories=round(item.nutrition.calories),
                protein_g=round(item.nutrition.protein_g, 1),
                carbs_g=round(item.nutrition.carbs_g, 1),
                fat_g=round(item.nutrition.fat_g, 1),
                note=item.note or "多模态大模型估算值",
            )
            record = find_food(item.name)
            confidence = min(1.0, max(0.0, item.confidence))
            foods.append(
                FoodItem(
                    name=record.name if record else item.name,
                    confidence=round(confidence, 3),
                    bbox=bbox,
                    mask_area_ratio=None,
                    estimated_grams=item.estimated_grams,
                    nutrition=nutrition,
                    verdict=provisional_verdict(item.name, nutrition),
                    source_id=record.food_id if record else None,
                )
            )
        totals = total_nutrition(foods)
        verdict, fallback_advice, fallback_note, target_metadata = evaluate_meal(totals, profile, foods)
        enrich_food_verdicts(foods, verdict, profile)

        advice = [text.strip() for text in payload.advice if text.strip()]
        if any(phrase in text for text in advice for phrase in BANNED_PHRASES):
            warnings.append("模型建议含不适当措辞，已替换为规则引擎的安全建议。")
            advice = fallback_advice
        if not advice:
            advice = fallback_advice
        if len(advice) > 4:
            advice = advice[:4]

        if totals.calories > 5000:
            warnings.append("模型给出的总热量异常偏高，请谨慎参考。")
        macro_calories = totals.protein_g * 4 + totals.carbs_g * 4 + totals.fat_g * 9
        if totals.calories and abs(macro_calories - totals.calories) / totals.calories > 0.35:
            warnings.append("热量与三大营养素换算结果差异较大，属于模型估算不确定性。")

        return MethodResult(
            method="vlm",
            status="degraded" if warnings or not foods else "ok",
            foods=foods,
            totals=totals,
            verdict=verdict,
            advice=advice,
            long_term_note=payload.long_term_note or fallback_note,
            disclaimer=DISCLAIMER,
            warnings=warnings,
            duration_ms=round((time.perf_counter() - started) * 1000),
            metadata={
                **target_metadata,
                "pipeline": "Qwen3.8-Omni-Flash structured JSON -> Pydantic validation -> rules",
                "provider": "DashScope OpenAI-compatible",
                "model": model,
                "attempts": attempts,
                "prompt_version": self.prompt_version,
                "cache_hit": False,
            },
        )

    @staticmethod
    def _cache_key(image_rgb: np.ndarray, profile: UserProfile) -> str:
        digest = hashlib.sha256(image_rgb.tobytes()).hexdigest()
        return hashlib.sha256(
            f"{digest}|{profile.model_dump_json()}|{settings.vlm_model}|{settings.vlm_base_url}".encode()
        ).hexdigest()

    @staticmethod
    def _error_result(message: str, started: float) -> MethodResult:
        return MethodResult(
            method="vlm",
            status="error",
            foods=[],
            totals={"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0},
            verdict={
                "calorie_status": "无法判断",
                "protein_status": "无法判断",
                "carb_ratio": "无法判断",
                "summary": message,
            },
            advice=["配置 API Key 后重新评估；也可以先查看左侧传统方案结果。"],
            long_term_note="单顿不决定结果；模型不可用时不应编造营养结论。",
            disclaimer=DISCLAIMER,
            warnings=[message],
            duration_ms=round((time.perf_counter() - started) * 1000),
            metadata={"pipeline": "Qwen3.8-Omni-Flash structured JSON", "configured": False},
        )