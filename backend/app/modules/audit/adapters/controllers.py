"""Administrator-only, bounded audit consultation."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.openapi_security import bearer_auth
from app.modules.audit.use_cases.list_audit_logs import list_audit_logs
from app.modules.identity.adapters.controllers import StrictSchema, api_error, current_user_id, read_limit
from app.modules.ledger.infrastructure.models import UserModel, UserRole

router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(bearer_auth)])


class AuditItem(StrictSchema):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    payload: dict
    created_at: datetime


class AuditPage(StrictSchema):
    items: list[AuditItem]
    next_offset: int | None


@router.get("/audit", response_model=AuditPage)
@read_limit
async def get_audit_log(request: Request, limit: int = Query(20, ge=1, le=50),
                        offset: int = Query(0, ge=0), session: AsyncSession = Depends(get_db)):
    actor_id = await current_user_id(request)
    if isinstance(actor_id, JSONResponse):
        return actor_id
    actor = await session.get(UserModel, actor_id)
    if actor is None or not actor.is_active:
        return api_error(401, "UNAUTHORIZED", "Token inválido")
    if actor.role != UserRole.ADMIN:
        return api_error(403, "FORBIDDEN", "Solo el administrador puede consultar la auditoría")
    records = await list_audit_logs(session, limit, offset)
    return AuditPage(items=[AuditItem(id=row.id, user_id=row.user_id, action=row.action,
                                      payload=row.payload, created_at=row.created_at)
                            for row in records[:limit]],
                     next_offset=offset + limit if len(records) > limit else None)
