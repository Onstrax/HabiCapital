"""Read a bounded page of audit records, newest first."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.infrastructure.models import AuditLogModel


async def list_audit_logs(session: AsyncSession, limit: int, offset: int):
    return (await session.execute(
        select(AuditLogModel).order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())
        .offset(offset).limit(limit + 1)
    )).scalars().all()
