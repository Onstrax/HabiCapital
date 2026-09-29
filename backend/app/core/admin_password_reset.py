"""Interactive recovery for the configured administrator account.

Run with ``python -m app.core.admin_password_reset`` from the backend container.
The command never prints or accepts the password as a command-line argument.
"""

import asyncio
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.field_encryption import blind_index
from app.core.database import get_session_factory
from app.core.security import hash_password, verify_password
from app.modules.ledger.infrastructure.models import AuditLogModel, UserModel, UserRole


async def rotate_admin_password(session: AsyncSession, email: str, new_password: str) -> None:
    if not isinstance(new_password, str) or not 12 <= len(new_password) <= 128:
        raise ValueError("La contraseña debe tener entre 12 y 128 caracteres")

    admin = (await session.execute(
        select(UserModel).where(UserModel.email_blind_index == blind_index(email)).with_for_update()
    )).scalar_one_or_none()
    if admin is None or admin.role != UserRole.ADMIN or not admin.is_active:
        raise RuntimeError("No existe un administrador activo para el ADMIN_EMAIL configurado")
    if verify_password(new_password, admin.password_hash):
        raise ValueError("La nueva contraseña debe ser diferente a la actual")

    admin.password_hash = hash_password(new_password)
    session.add(AuditLogModel(
        user_id=admin.id,
        action="ADMIN_PASSWORD_RESET",
        payload={"method": "cli"},
        ip_address=None,
    ))
    await session.flush()


async def _run() -> None:
    email = get_settings().ADMIN_EMAIL
    new_password = getpass(f"Nueva contraseña para {email} (no se mostrará): ")
    confirmation = getpass("Confirma la nueva contraseña: ")
    if new_password != confirmation:
        raise ValueError("Las contraseñas no coinciden")

    async with get_session_factory()() as session:
        async with session.begin():
            await rotate_admin_password(session, email, new_password)
    print(f"Contraseña restablecida para {email}. Inicia sesión con la nueva contraseña.")


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
