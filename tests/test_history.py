import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main as main_module
from app.catalog import load_catalog
from app.config import settings
from app.main import app
from app.schemas import MethodResult
from helpers import build_food


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers(client: TestClient, username: str) -> dict[str, str]:
    password = "strong-password-123"
    register = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert register.status_code == 201
    login = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _method_result(method: str) -> MethodResult:
    rice = next(item for item in load_catalog() if item.food_id == "rice")
    return MethodResult(
        method=method,
        foods=[build_food(rice, 150)],
        totals={"calories": 195, "protein_g": 4, "carbs_g": 42, "fat_g": 0.5},
        verdict={
            "calorie_status": "ok",
            "protein_status": "ok",
            "carb_ratio": "ok",
            "summary": "test result",
        },
        advice=["test advice"],
        long_term_note="test note",
    )


class FakeService:
    def __init__(self, result: MethodResult):
        self.result = result

    def assess(self, image_rgb, profile):
        return self.result


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (220, 180, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_assess_persists_and_history_crud(client, monkeypatch):
    headers = _auth_headers(client, "history_owner")
    monkeypatch.setattr(main_module, "get_traditional_service", lambda: FakeService(_method_result("traditional")))
    monkeypatch.setattr(main_module, "get_vlm_service", lambda: FakeService(_method_result("vlm")))

    response = client.post(
        "/api/v1/assess",
        headers=headers,
        files={"image": ("meal.png", _png_bytes(), "image/png")},
    )
    assert response.status_code == 200
    assessment_id = response.json()["request_id"]
    image_path = settings.uploads_dir / f"{assessment_id}.jpg"
    assert image_path.is_file()

    listing = client.get("/api/v1/history", headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == assessment_id for item in listing.json()["items"])

    detail = client.get(f"/api/v1/history/{assessment_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"
    assert detail.json()["result"]["traditional"]["method"] == "traditional"

    updated = client.patch(
        f"/api/v1/history/{assessment_id}",
        headers=headers,
        json={"note": "reviewed"},
    )
    assert updated.status_code == 200
    assert updated.json()["note"] == "reviewed"

    other_headers = _auth_headers(client, "history_other")
    assert client.get(f"/api/v1/history/{assessment_id}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/history/{assessment_id}", headers=other_headers).status_code == 404

    deleted = client.delete(f"/api/v1/history/{assessment_id}", headers=headers)
    assert deleted.status_code == 204
    assert not image_path.exists()
    assert client.get(f"/api/v1/history/{assessment_id}", headers=headers).status_code == 404