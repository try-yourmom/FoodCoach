from __future__ import annotations

import asyncio
from functools import lru_cache

import numpy as np

from app.rule_engine import DISCLAIMER
from app.schemas import AssessmentBundle, MethodResult, UserProfile
from app.services.comparison import build_comparison
from app.services.traditional import TraditionalVisionService
from app.services.vlm import VLMService


@lru_cache(maxsize=1)
def get_traditional_service() -> TraditionalVisionService:
    return TraditionalVisionService()


@lru_cache(maxsize=1)
def get_vlm_service() -> VLMService:
    return VLMService()


async def run_assessment(image_rgb: np.ndarray, profile: UserProfile, request_id: str) -> AssessmentBundle:
    traditional_service = get_traditional_service()
    vlm_service = get_vlm_service()
    traditional_task = asyncio.to_thread(traditional_service.assess, image_rgb, profile)
    vlm_task = asyncio.to_thread(vlm_service.assess, image_rgb, profile)
    traditional_result, vlm_result = await asyncio.gather(
        traditional_task, vlm_task, return_exceptions=True
    )
    if isinstance(traditional_result, Exception):
        traditional_result = _traditional_error_result(traditional_result)
    if isinstance(vlm_result, Exception):
        vlm_result = _vlm_error_result(vlm_result)

    return AssessmentBundle(
        request_id=request_id,
        traditional=traditional_result,
        vlm=vlm_result,
        comparison=build_comparison(traditional_result, vlm_result),
        profile=profile,
    )


def _traditional_error_result(exc: Exception) -> MethodResult:
    message = f"传统视觉模型调用失败：{type(exc).__name__}: {exc}"
    return MethodResult(
        method="traditional",
        status="error",
        foods=[],
        totals={"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0},
        verdict={
            "calorie_status": "无法判断",
            "protein_status": "无法判断",
            "carb_ratio": "无法判断",
            "summary": message,
        },
        advice=["确认模型权重和依赖已安装，再重新评估同一张图片。"],
        long_term_note="模型不可用时不应编造视觉或营养结论。",
        disclaimer=DISCLAIMER,
        warnings=[message],
        metadata={"pipeline": "YOLO-World -> MobileSAM"},
    )


def _vlm_error_result(exc: Exception) -> MethodResult:
    message = f"多模态模型调用异常：{type(exc).__name__}: {exc}"
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
        advice=["检查 API Key、网络和模型名称后重试；也可先查看传统方案。"],
        long_term_note="模型不可用时不应编造营养结论。",
        disclaimer=DISCLAIMER,
        warnings=[message],
        metadata={"pipeline": "Qwen3.8-Omni-Flash structured JSON"},
    )