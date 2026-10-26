import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

client = TestClient(app)


def test_health_and_catalog():
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    catalog = client.get("/api/v1/catalog")
    assert catalog.status_code == 200
    assert 15 <= len(catalog.json()["foods"]) <= 20


def test_rejects_non_image_upload():
    response = client.post(
        "/api/v1/assess",
        files={"image": ("not-image.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_generated_png_is_decodable():
    buffer = io.BytesIO()
    Image.new("RGB", (32, 32), (220, 180, 90)).save(buffer, format="PNG")
    assert buffer.getvalue().startswith(b"\x89PNG")