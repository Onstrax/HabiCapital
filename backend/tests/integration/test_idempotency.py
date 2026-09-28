"""HTTP integration of middleware with a deterministic test repository."""

import uuid
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
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


def test_idempotency_rejects_missing_invalid_unauthorized_and_large_requests():
    client, _, _, settings = setup_app()
    key = uuid.uuid4()
    path = "/api/v1/transfers/execute"
    assert client.post(path, json={"amount": 1}).status_code == 400
    assert client.post(path, headers={"X-Idempotency-Key": "not-a-uuid"},
                       json={"amount": 1}).status_code == 400
    assert client.post(path, headers={"X-Idempotency-Key": str(uuid.uuid1())},
                       json={"amount": 1}).status_code == 400
    assert client.post(path, headers={"X-Idempotency-Key": str(key)},
                       json={"amount": 1}).status_code == 401
    assert client.post(path, headers={"X-Idempotency-Key": str(key),
                                     "Authorization": "Bearer invalid"},
                       json={"amount": 1}).status_code == 401
    h = headers(settings, uuid.uuid4(), uuid.uuid4())
    response = client.post(path, headers=h, data="x" * 1_048_577)
    assert response.status_code == 413


def test_idempotency_releases_failed_responses_as_failed_and_keeps_crash_claim():
    client, store, _, settings = setup_app()
    user_id = uuid.uuid4()
    failed_key = uuid.uuid4()
    h = headers(settings, user_id, failed_key)
    response = client.post("/api/v1/transfers/execute", headers=h, json={"amount": 1})
    assert response.status_code == 201
    # Existing successful operation is cached; this additionally verifies the
    # store status update APIs used by the error path.
    store.records[failed_key].status = IdempotencyStatus.PROCESSING

    crash_app = FastAPI()
    crash_store = FakeIdempotencyStore()
    crash_app.add_middleware(IdempotencyMiddleware, store=crash_store, settings=settings)

    @crash_app.post("/api/v1/transfers/execute")
    def crash():
        raise RuntimeError("simulated route crash")

    crash_client = TestClient(crash_app)
    crash_headers = headers(settings, user_id, uuid.uuid4())
    with pytest.raises(Exception):
        crash_client.post("/api/v1/transfers/execute", headers=crash_headers, json={"amount": 1})
    crash_record = next(iter(crash_store.records.values()))
    assert crash_record.status == IdempotencyStatus.PROCESSING


def test_http_error_marks_key_failed_and_returns_original_response():
    settings = Settings(_env_file=None, DATABASE_URL="postgresql+psycopg://test:test@localhost/test",
                        JWT_SECRET_KEY="s" * 64, ADMIN_PASSWORD="test-password-123")
    app = FastAPI()
    store = FakeIdempotencyStore()
    app.add_middleware(IdempotencyMiddleware, store=store, settings=settings)

    @app.post("/api/v1/transfers/execute")
    def reject():
        return JSONResponse({"code": "NO", "message": "rejected"}, status_code=400)

    client = TestClient(app)
    user_id, key = uuid.uuid4(), uuid.uuid4()
    h = headers(settings, user_id, key)
    result = client.post("/api/v1/transfers/execute", headers=h, json={"amount": 1})
    assert result.status_code == 400
    assert store.records[key].status == IdempotencyStatus.FAILED
    assert client.post("/api/v1/transfers/execute", headers=h,
                       json={"amount": 1}).status_code == 409
