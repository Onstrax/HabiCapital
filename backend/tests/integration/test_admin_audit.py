"""Audit history is visible only to active administrators and never exposes IPs."""

import uuid

import pytest

from app.core.security import create_access_token
from app.modules.ledger.infrastructure.models import AuditLogModel, UserModel, UserRole


@pytest.mark.asyncio
async def test_admin_audit_is_authorized_paginated_and_decrypts_payload(sessions, async_client):
    async with sessions() as session, session.begin():
        admin = UserModel(email="auditor@example.test", alias="auditor", full_name="Admin Auditor",
                          password_hash="hash", role=UserRole.ADMIN)
        user = UserModel(email="regular@example.test", alias="regular", full_name="Regular User",
                         password_hash="hash")
        session.add_all([admin, user])
        await session.flush()
        session.add_all([
            AuditLogModel(user_id=user.id, action=f"ACTION_{i}",
                          payload={"detail": f"private-{i}"}, ip_address="192.0.2.4")
            for i in range(3)
        ])
        await session.flush()
        admin_id, user_id = admin.id, user.id

    url = "/api/v1/admin/audit?limit=2"
    assert (await async_client.get(url)).status_code == 401
    user_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}
    assert (await async_client.get(url, headers=user_headers)).status_code == 403

    admin_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin_id)})}"}
    first = await async_client.get(url, headers=admin_headers)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert first.json()["next_offset"] == 2
    assert all(item["payload"]["detail"].startswith("private-") for item in first.json()["items"])
    assert "ip_address" not in first.text

    second = await async_client.get(url + "&offset=2", headers=admin_headers)
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["next_offset"] is None
    assert len({item["id"] for item in first.json()["items"] + second.json()["items"]}) == 3
    assert (await async_client.get(url + "&limit=51", headers=admin_headers)).status_code == 422


@pytest.mark.asyncio
async def test_read_routes_share_an_actor_rate_limit(sessions, async_client):
    async with sessions() as session, session.begin():
        user = UserModel(email=f"rate-{uuid.uuid4()}@example.test", alias="rateuser",
                         full_name="Rate User", password_hash="hash")
        session.add(user)
        await session.flush()
        user_id = user.id
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(user_id)})}"}
    for _ in range(30):
        response = await async_client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200
    for _ in range(30):
        response = await async_client.get("/api/v1/charges", headers=headers)
        assert response.status_code == 200
    limited = await async_client.get("/api/v1/auth/me", headers=headers)
    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMIT_EXCEEDED"
