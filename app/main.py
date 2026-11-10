from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import get_current_user, router as auth_router
from app.catalog import catalog_payload
from app.config import settings
from app.db import get_db, init_db
from app.history import persist_assessment, router as history_router
from app.models import User
from app.rule_engine import DISCLAIMER
from app.schemas import (
    AssessmentBundle,
    Goal,
    MealContext,
    MethodResult,
    UserProfile,
)
from app.services.comparison import build_comparison
from app.services.image_utils import InvalidImageError, decode_image
from app.services.traditional import TraditionalVisionService
from app.services.vlm import VLMService


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="FoodCoach PlateLens API",
    lifespan=lifespan,
    version=settings.app_version,
    description="同一餐盘图片的传统视觉方案与多模态大模型方案对比。",
)
app.include_router(auth_router)
app.include_router(history_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


@lru_cache(maxsize=1)
def get_traditional_service() -> TraditionalVisionService:
    return TraditionalVisionService()


@lru_cache(maxsize=1)
def get_vlm_service() -> VLMService:
    return VLMService()


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


@app.get("/api/v1/health")
def health():
    cuda_available = False
    try:
        import torch

        cuda_available = torch.cuda.is_available()
    except (ImportError, OSError, RuntimeError):
        cuda_available = False
    return {
        "status": "ok",
        "version": settings.app_version,
        "vlm_configured": settings.vlm_configured,
        "vlm_model": settings.vlm_model,
        "yolo_model_present": settings.yolo_model_path.exists(),
        "sam_model_present": settings.sam_model_path.exists(),
        "device": str(settings.resolved_device()),
        "cuda_available": cuda_available,
    }


@app.get("/api/v1/catalog")
def catalog():
    return {"foods": catalog_payload()}


@app.post("/api/v1/assess", response_model=AssessmentBundle)
async def assess_meal(
    image: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    height_cm: Annotated[float, Form()] = 170,
    weight_kg: Annotated[float, Form()] = 65,
    body_fat_pct: Annotated[float | None, Form()] = None,
    goal: Annotated[Goal, Form()] = Goal.MAINTAIN,
    context: Annotated[MealContext, Form()] = MealContext.REST_DAY,
    plate_diameter_cm: Annotated[float, Form()] = 26,
):
    request_id = uuid.uuid4().hex
    max_bytes = round(settings.max_upload_mb * 1024 * 1024)
    raw = await image.read(max_bytes + 1)
    if not raw:
        raise HTTPException(status_code=400, detail="上传文件为空。")
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f"图片不能超过 {settings.max_upload_mb:g} MB。")
    try:
        image_rgb = decode_image(raw)
    except InvalidImageError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    try:
        profile = UserProfile(
            height_cm=height_cm,
            weight_kg=weight_kg,
            body_fat_pct=body_fat_pct,
            goal=goal,
            context=context,
            plate_diameter_cm=plate_diameter_cm,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"用户信息不合法：{exc}") from exc

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

    bundle = AssessmentBundle(
        request_id=request_id,
        traditional=traditional_result,
        vlm=vlm_result,
        comparison=build_comparison(traditional_result, vlm_result),
        profile=profile,
    )
    persist_assessment(db, request_id, current_user.id, raw, profile, bundle)
    return bundle


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