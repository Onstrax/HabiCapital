"""HTTP integration of middleware with a deterministic test repository."""

import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.idempotency import IdempotencyMiddleware
from app.core.security import create_access_token
from app.modules.ledger.infrastructure.models import IdempotencyStatus


@dataclass
class Record:
    user_id: uuid.UUID
    request_hash: str
    status: IdempotencyStatus = IdempotencyStatus.PROCESSING
    response_code: int | None = None
    response_body: dict | None = None


class FakeIdempotencyStore:
    def __init__(self):
        self.records = {}

    async def claim(self, key, user_id, request_hash):
        if key not in self.records:
            self.records[key] = Record(user_id, request_hash)
            return None
        return self.records[key]

    async def complete(self, key, response_code, response_body):
        item = self.records[key]
        item.status = IdempotencyStatus.COMPLETED
        item.response_code = response_code
        item.response_body = response_body

    async def fail(self, key):
        self.records[key].status = IdempotencyStatus.FAILED


def setup_app():
    settings = Settings(_env_file=None, DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
                        JWT_SECRET_KEY="s" * 64, ADMIN_PASSWORD="test-password-123")
    app = FastAPI()
    store = FakeIdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store, settings=settings)
    calls = []

    @app.post("/api/v1/transfers/execute", status_code=201)
    def execute(payload: dict):
        calls.append(payload)
        return {"reference_id": "once", "amount": payload["amount"]}

    return TestClient(app), store, calls, settings


def headers(settings, user_id, key):
    token = create_access_token({"sub": str(user_id), "email": "a@example.test", "alias": "tester",
                                 "role": "USER"}, settings=settings)
    return {"Authorization": f"Bearer {token}", "X-Idempotency-Key": str(key)}


def test_identical_second_request_returns_original_response_without_execution():
    client, store, calls, settings = setup_app()
    h = headers(settings, uuid.uuid4(), uuid.uuid4())
    first = client.post("/api/v1/transfers/execute", headers=h, json={"amount": 50000})
    second = client.post("/api/v1/transfers/execute", headers=h, json={"amount": 50000})
    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers["X-Cache"] == "HIT-IDEMPOTENCY"
    assert len(calls) == 1


def test_processing_mismatch_and_cross_user_are_rejected():
    client, store, calls, settings = setup_app()
    key, user_id = uuid.uuid4(), uuid.uuid4()
    h = headers(settings, user_id, key)
    assert client.post("/api/v1/transfers/execute", headers=h, json={"amount": 1}).status_code == 201
    assert client.post("/api/v1/transfers/execute", headers=h, json={"amount": 2}).status_code == 422
    assert client.post("/api/v1/transfers/execute", headers=headers(settings, uuid.uuid4(), key),
                       json={"amount": 1}).status_code == 409
    store.records[key].status = IdempotencyStatus.PROCESSING
    assert client.post("/api/v1/transfers/execute", headers=h, json={"amount": 1}).status_code == 409
    assert len(calls) == 1
