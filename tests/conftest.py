import os
import tempfile
import uuid
from pathlib import Path

import pytest

TEST_DB_PATH = Path(tempfile.gettempdir()) / f"foodcoach_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("JWT_SECRET", "test-secret-for-foodcoach-0123456789abcdef")


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_database():
    yield
    from app.db import close_db

    close_db()
    TEST_DB_PATH.unlink(missing_ok=True)