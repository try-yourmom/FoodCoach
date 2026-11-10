import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth_headers(client):
    username = "auth_user"
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
    token = login.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health_and_catalog(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    catalog = client.get("/api/v1/catalog")
    assert catalog.status_code == 200
    assert 15 <= len(catalog.json()["foods"]) <= 20


def test_register_login_and_me(client):
    register = client.post(
        "/api/v1/auth/register",
        json={"username": "me_user", "password": "strong-password-123"},
    )
    assert register.status_code == 201
    assert register.json()["username"] == "me_user"

    login = client.post(
        "/api/v1/auth/login",
        data={"username": "me_user", "password": "strong-password-123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "me_user"


def test_duplicate_username_is_rejected(client):
    payload = {"username": "duplicate_user", "password": "strong-password-123"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409


def test_wrong_password_is_rejected(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "wrong_password_user", "password": "strong-password-123"},
    )
    response = client.post(
        "/api/v1/auth/login",
        data={"username": "wrong_password_user", "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_assess_requires_authentication(client):
    response = client.post(
        "/api/v1/assess",
        files={"image": ("not-image.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 401


def test_rejects_non_image_upload(client, auth_headers):
    response = client.post(
        "/api/v1/assess",
        headers=auth_headers,
        files={"image": ("not-image.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_generated_png_is_decodable():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (220, 180, 90)).save(buffer, format="PNG")
    assert buffer.getvalue().startswith(b"\x89PNG")