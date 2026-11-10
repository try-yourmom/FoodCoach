from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
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
from app.job_routes import router as job_router
from app.models import User
from app.schemas import (
    AssessmentBundle,
    Goal,
    MealContext,
    UserProfile,
)
from app.services.image_utils import InvalidImageError, decode_image
from app.services.assessment_runner import run_assessment


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
app.include_router(job_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


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

    bundle = await run_assessment(image_rgb, profile, request_id)
    persist_assessment(db, request_id, current_user.id, raw, profile, bundle)
    return bundle
