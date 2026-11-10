from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import settings
from app.db import get_db
from app.models import Assessment, User, utc_now
from app.schemas import (
    AssessmentBundle,
    HistoryDetailResponse,
    HistoryListResponse,
    HistoryNoteUpdate,
    HistorySummary,
    UserProfile,
)

router = APIRouter(prefix='/api/v1/history', tags=['history'])


def _summary(record: Assessment) -> HistorySummary:
    return HistorySummary(
        id=record.id,
        status=record.status,
        note=record.note,
        created_at=record.created_at,
        finished_at=record.finished_at,
        error_message=record.error_message,
    )


def _detail(record: Assessment) -> HistoryDetailResponse:
    profile = UserProfile.model_validate_json(record.profile_json)
    result = AssessmentBundle.model_validate_json(record.result_json) if record.result_json else None
    return HistoryDetailResponse(
        **_summary(record).model_dump(),
        profile=profile,
        result=result,
    )


def persist_assessment(
    db: Session,
    assessment_id: str,
    user_id: int,
    raw_image: bytes,
    profile: UserProfile,
    result: AssessmentBundle,
) -> Assessment:
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    image_path = settings.uploads_dir / f'{assessment_id}.jpg'
    image_path.write_bytes(raw_image)
    now = utc_now()
    record = Assessment(
        id=assessment_id,
        user_id=user_id,
        status='succeeded',
        image_path=str(image_path),
        profile_json=profile.model_dump_json(),
        result_json=result.model_dump_json(),
        note='',
        created_at=now,
        started_at=now,
        finished_at=now,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        image_path.unlink(missing_ok=True)
        raise
    db.refresh(record)
    return record


def _get_owned_record(db: Session, user_id: int, assessment_id: str) -> Assessment:
    record = db.scalar(
        select(Assessment).where(
            Assessment.id == assessment_id,
            Assessment.user_id == user_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Assessment not found')
    return record


@router.get('', response_model=HistoryListResponse)
def list_history(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HistoryListResponse:
    records = db.scalars(
        select(Assessment)
        .where(Assessment.user_id == current_user.id)
        .order_by(Assessment.created_at.desc())
    ).all()
    return HistoryListResponse(items=[_summary(record) for record in records])


@router.get('/{assessment_id}', response_model=HistoryDetailResponse)
def get_history_detail(
    assessment_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HistoryDetailResponse:
    return _detail(_get_owned_record(db, current_user.id, assessment_id))


@router.patch('/{assessment_id}', response_model=HistorySummary)
def update_history_note(
    assessment_id: str,
    payload: HistoryNoteUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HistorySummary:
    record = _get_owned_record(db, current_user.id, assessment_id)
    record.note = payload.note
    db.commit()
    db.refresh(record)
    return _summary(record)


@router.delete('/{assessment_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_history(
    assessment_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    record = _get_owned_record(db, current_user.id, assessment_id)
    image_path = Path(record.image_path)
    uploads_root = settings.uploads_dir.resolve()
    try:
        target = image_path.resolve()
        if uploads_root == target.parent or uploads_root in target.parents:
            target.unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(record)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)