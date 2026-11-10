from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Assessment, utc_now
from app.schemas import UserProfile
from app.services.assessment_runner import run_assessment
from app.services.image_utils import decode_image


def process_assessment(assessment_id: str) -> None:
    db = SessionLocal()
    try:
        record = db.get(Assessment, assessment_id)
        if record is None or record.status == 'succeeded':
            return

        record.status = 'running'
        record.started_at = utc_now()
        record.error_message = None
        db.commit()

        raw_image = Path(record.image_path).read_bytes()
        image_rgb = decode_image(raw_image)
        profile = UserProfile.model_validate_json(record.profile_json)
        bundle = asyncio.run(run_assessment(image_rgb, profile, assessment_id))

        record.status = 'succeeded'
        record.result_json = bundle.model_dump_json()
        record.finished_at = utc_now()
        db.commit()
    except Exception as exc:
        db.rollback()
        record = db.get(Assessment, assessment_id)
        if record is not None:
            record.status = 'failed'
            record.error_message = f'{type(exc).__name__}: {exc}'[:2000]
            record.finished_at = utc_now()
            db.commit()
        raise
    finally:
        db.close()


def recover_pending_jobs(queue=None) -> int:
    from app.queueing import get_queue

    queue = queue or get_queue()
    recovered = 0
    with SessionLocal() as db:
        records = db.scalars(
            select(Assessment).where(Assessment.status.in_(['queued', 'running']))
        ).all()

    for record in records:
        try:
            existing = queue.fetch_job(record.id)
            if existing is not None:
                existing.delete()
            with SessionLocal() as db:
                current = db.get(Assessment, record.id)
                if current is None:
                    continue
                current.status = 'queued'
                current.started_at = None
                current.error_message = None
                db.commit()
            queue.enqueue(
                process_assessment,
                record.id,
                job_id=record.id,
                job_timeout=settings.job_timeout_seconds,
            )
            recovered += 1
        except Exception:
            continue
    return recovered