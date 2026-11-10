import asyncio
import io
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.job_routes as job_routes
import app.jobs as jobs
from app.catalog import load_catalog
from app.config import settings
from app.db import SessionLocal
from app.main import app
from app.models import Assessment
from app.schemas import AssessmentBundle, MethodResult
from helpers import build_food


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(client: TestClient, username: str) -> dict[str, str]:
    password = "strong-password-123"
    assert client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    ).status_code == 201
    response = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (220, 180, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def _method_result(method: str) -> MethodResult:
    rice = next(item for item in load_catalog() if item.food_id == "rice")
    return MethodResult(
        method=method,
        foods=[build_food(rice, 150)],
        totals={"calories": 195, "protein_g": 4, "carbs_g": 42, "fat_g": 0.5},
        verdict={"calorie_status": "ok", "protein_status": "ok", "carb_ratio": "ok", "summary": "test"},
        advice=["test advice"],
        long_term_note="test note",
    )


async def _fake_run_assessment(image_rgb, profile, request_id):
    return AssessmentBundle(
        request_id=request_id,
        traditional=_method_result("traditional"),
        vlm=_method_result("vlm"),
        comparison={
            "rows": [],
            "summary": "test comparison",
            "recommended_use": "test",
        },
        profile=profile,
    )


class FakeQueue:
    def __init__(self):
        self.enqueued = []

    def fetch_job(self, job_id):
        return None

    def enqueue(self, function, assessment_id, **kwargs):
        self.enqueued.append((function, assessment_id, kwargs))
        return object()


def test_job_creation_and_worker_processing(client, monkeypatch):
    headers = _auth_headers(client, "queue_owner")
    enqueued = []
    monkeypatch.setattr(job_routes, "enqueue_assessment", lambda assessment_id: enqueued.append(assessment_id))

    response = client.post(
        "/api/v1/assess/jobs",
        headers=headers,
        files={"image": ("meal.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 202
    assessment_id = response.json()["id"]
    assert response.json()["status"] == "queued"
    assert enqueued == [assessment_id]

    pending = client.get(f"/api/v1/assess/jobs/{assessment_id}", headers=headers)
    assert pending.status_code == 200
    assert pending.json()["status"] == "queued"
    assert pending.json()["result"] is None

    monkeypatch.setattr(jobs, "run_assessment", _fake_run_assessment)
    jobs.process_assessment(assessment_id)

    completed = client.get(f"/api/v1/assess/jobs/{assessment_id}", headers=headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"
    assert completed.json()["result"]["traditional"]["method"] == "traditional"

    deleted = client.delete(f"/api/v1/history/{assessment_id}", headers=headers)
    assert deleted.status_code == 204


def test_worker_recovers_queued_records(client):
    headers = _auth_headers(client, "recovery_owner")
    user = client.get("/api/v1/auth/me", headers=headers).json()
    assessment_id = "recovery-job-001"
    image_path = settings.uploads_dir / f"{assessment_id}.jpg"
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(_png_bytes())

    with SessionLocal() as db:
        db.add(
            Assessment(
                id=assessment_id,
                user_id=user["id"],
                status="running",
                image_path=str(image_path),
                profile_json='{"height_cm":170,"weight_kg":65,"goal":"maintain","context":"rest_day","plate_diameter_cm":26}',
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    fake_queue = FakeQueue()
    recovered = jobs.recover_pending_jobs(fake_queue)
    assert recovered >= 1
    assert any(item[1] == assessment_id for item in fake_queue.enqueued)
    with SessionLocal() as db:
        record = db.get(Assessment, assessment_id)
        assert record is not None
        assert record.status == "queued"
    image_path.unlink(missing_ok=True)
    with SessionLocal() as db:
        record = db.get(Assessment, assessment_id)
        if record is not None:
            db.delete(record)
            db.commit()