from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.history import _detail
from app.models import Assessment, User, utc_now
from app.queueing import enqueue_assessment
from app.schemas import (
    Goal,
    HistoryDetailResponse,
    JobCreatedResponse,
    MealContext,
    UserProfile,
)
from app.services.image_utils import InvalidImageError, decode_image

router = APIRouter(prefix='/api/v1/assess', tags=['assessment jobs'])


def _make_profile(
    height_cm: float,
    weight_kg: float,
    body_fat_pct: float | None,
    goal: Goal,
    context: MealContext,
    plate_diameter_cm: float,
) -> UserProfile:
    try:
        return UserProfile(
            height_cm=height_cm,
            weight_kg=weight_kg,
            body_fat_pct=body_fat_pct,
            goal=goal,
            context=context,
            plate_diameter_cm=plate_diameter_cm,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f'Invalid user profile: {exc}') from exc


@router.post('/jobs', response_model=JobCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_assessment_job(
    image: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    height_cm: Annotated[float, Form()] = 170,
    weight_kg: Annotated[float, Form()] = 65,
    body_fat_pct: Annotated[float | None, Form()] = None,
    goal: Annotated[Goal, Form()] = Goal.MAINTAIN,
    context: Annotated[MealContext, Form()] = MealContext.REST_DAY,
    plate_diameter_cm: Annotated[float, Form()] = 26,
) -> JobCreatedResponse:
    max_bytes = round(settings.max_upload_mb * 1024 * 1024)
    raw = await image.read(max_bytes + 1)
    if not raw:
        raise HTTPException(status_code=400, detail='Uploaded file is empty')
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail=f'Image exceeds {settings.max_upload_mb:g} MB')
    try:
        decode_image(raw)
    except InvalidImageError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    profile = _make_profile(height_cm, weight_kg, body_fat_pct, goal, context, plate_diameter_cm)
    assessment_id = uuid.uuid4().hex
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    image_path = settings.uploads_dir / f'{assessment_id}.jpg'
    image_path.write_bytes(raw)

    record = Assessment(
        id=assessment_id,
        user_id=current_user.id,
        status='queued',
        image_path=str(image_path),
        profile_json=profile.model_dump_json(),
        created_at=utc_now(),
        note='',
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        enqueue_assessment(assessment_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Assessment saved as {assessment_id}, but the queue is unavailable: {exc}',
        ) from exc

    return JobCreatedResponse(id=assessment_id, status=record.status)


@router.get('/jobs/{assessment_id}', response_model=HistoryDetailResponse)
def get_assessment_job(
    assessment_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HistoryDetailResponse:
    record = db.get(Assessment, assessment_id)
    if record is None or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail='Assessment not found')
    return _detail(record)