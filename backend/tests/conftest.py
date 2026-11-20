from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.adapters.storage.factory import get_storage_adapter
from app.adapters.storage.local_storage import LocalFilesystemStorageAdapter
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import create_db_engine, get_db
from app.main import create_app


@pytest.fixture()
def test_context(tmp_path: Path):
    db_file = tmp_path / "test_parkvektor.db"
    storage_dir = tmp_path / "storage"
    engine = create_db_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    storage = LocalFilesystemStorageAdapter(str(storage_dir))

    with TestingSession() as db:
        seed_demo_data(db)

    app = create_app()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_adapter] = lambda: storage

    with TestClient(app) as client:
        yield {
            "client": client,
            "session_factory": TestingSession,
            "storage": storage,
            "admin_headers": {"X-Admin-API-Key": "dev-admin-key-change-in-prod"},
            "lane_secret": "dev-lane-secret-change-in-prod",
        }
    engine.dispose()
