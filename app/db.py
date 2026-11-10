from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def _sqlite_connect_args() -> dict:
    if settings.database_url.startswith('sqlite'):
        return {'check_same_thread': False}
    return {}


engine = create_engine(settings.database_url, connect_args=_sqlite_connect_args())
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    # Import models before create_all so their tables are registered.
    import app.models  # noqa: F401

    if settings.database_url.startswith('sqlite'):
        db_path = settings.database_url.removeprefix('sqlite:///')
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with engine.begin() as connection:
            connection.execute(text('PRAGMA journal_mode=WAL'))
            connection.execute(text('PRAGMA busy_timeout=5000'))

    Base.metadata.create_all(bind=engine)


def close_db() -> None:
    engine.dispose()