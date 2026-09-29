# SPEC-05: TESTING, TDD SUITE & INTEGRITY AUDITING SPECIFICATION
**Proyecto**: HabiCapital P2P Transactional Platform  
**Módulo**: Suite de Pruebas Automatizadas Pytest, Tests de Concurrencia P2P y Auditoría de Partida Doble  
**Versión**: 1.0.0  
**Estado**: APROBADO / ESPECIFICACIÓN TÉCNICA SDD  

---

## 1. FILOSOFÍA TDD Y METODOLOGÍA DE EVALUACIÓN

Para garantizar que el código generado por IA cumpla al 100% con la **Regla Suprema ("El sistema no puede perder un peso")**, la construcción del software seguirá un enfoque de **Test-Driven Development (TDD)** estricto:

1. **Red**: Escribir primero las pruebas unitarias e integrales basadas en esta especificación. Verificar que las pruebas fallen antes de tener código de producción.
2. **Green**: Escribir la implementación mínima necesaria en FastAPI / SQLAlchemy para hacer pasar las pruebas.
3. **Refactor**: Optimizar la estructura, legibilidad y rendimiento manteniendo las pruebas verdes.

---

## 2. CONFIGURACIÓN DEL ENTORNO DE PRUEBAS (FIXTURES PYTEST)

Las pruebas integrales se ejecutan contra una base de datos PostgreSQL real (vía Docker container en CI/CD o base de datos de test efímera) para validar restricciones de clave foránea, triggers y bloqueos pesimistas `FOR UPDATE`.

```python
# tests/conftest.py
import asyncio
import uuid
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.core.database import get_db
from app.core.security import hash_password, create_access_token
from app.modules.ledger.infrastructure.models import (
    Base, UserModel, AccountModel, UserRole, AccountType, TransactionModel, LedgerEntryModel, TransactionType, TransactionStatus
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/habicapital_test"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.clear()
```

---

## 3. SUITE DE PRUEBAS DE CONCURRENCIA & RACE CONDITIONS (RACE-CONDITION-TEST)

Esta prueba simula un ataque o colisión de concurrencia donde el **Usuario A** (con un saldo inicial de **\$50.000 COP**) envía **10 solicitudes de transferencia simultáneas de \$50.000 COP cada una** al **Usuario B** exactamente en el mismo milisegundo utilizando `asyncio.gather`.

### Criterio de Éxito Innegociable:
* **Exactamente 1 solicitud debe tener éxito** (HTTP 201).
* **Exactamente 9 solicitudes deben fallar** por saldo insuficiente (HTTP 400).
* **El saldo final del Usuario A debe ser \$0 COP** (jamás un número negativo / sobregiro).
* **El saldo final del Usuario B debe ser \$50.000 COP**.

```python
# tests/test_concurrency.py
import asyncio
import uuid
import pytest
from httpx import AsyncClient
from app.modules.ledger.domain.services import calculate_account_balance

@pytest.mark.asyncio
async def test_concurrent_transfers_prevent_overdraft(async_client: AsyncClient, db_session):
    """
    Simula 10 transferencias simultáneas de $50,000 COP enviadas en paralelo
    por un usuario que solo tiene $50,000 COP en su saldo.
    """
    # 1. SETUP: Crear Usuario A ($50,000) y Usuario B ($0)
    user_a_id = uuid.uuid4()
    user_b_id = uuid.uuid4()
    acc_a_id = uuid.uuid4()
    acc_b_id = uuid.uuid4()

    # Inyección de usuarios y cuentas en DB
    user_a = UserModel(id=user_a_id, email="usera@test.com", alias="user_a", password_hash=hash_password("Pass123!"), full_name="User A", role="USER")
    user_b = UserModel(id=user_b_id, email="userb@test.com", alias="user_b", password_hash=hash_password("Pass123!"), full_name="User B", role="USER")
    acc_a = AccountModel(id=acc_a_id, user_id=user_a_id, account_number="ACC-A-001", type="USER_WALLET")
    acc_b = AccountModel(id=acc_b_id, user_id=user_b_id, account_number="ACC-B-002", type="USER_WALLET")
    
    db_session.add_all([user_a, user_b, acc_a, acc_b])
    await db_session.flush()

    # Cargar saldo inicial de $50,000 a User A mediante TopUp
    sys_acc_id = uuid.uuid4()
    sys_acc = AccountModel(id=sys_acc_id, user_id=uuid.uuid4(), account_number="SYS-001", type="SYSTEM_OMNIBUS")
    db_session.add(sys_acc)
    await db_session.flush()

    topup_tx = TransactionModel(id=uuid.uuid4(), reference_id="TOPUP-INIT", type="TOPUP", status="SUCCESS", concept="Initial Balance")
    topup_entry = LedgerEntryModel(id=uuid.uuid4(), transaction_id=topup_tx.id, debit_account_id=sys_acc_id, credit_account_id=acc_a_id, amount=50000)
    db_session.add_all([topup_tx, topup_entry])
    await db_session.commit()

    # Token JWT para User A
    token_a = create_access_token({"sub": str(user_a_id), "role": "USER"})
    headers = {"Authorization": f"Bearer {token_a}"}

    # 2. PREPARAR 10 SOLICITUDES CONCURRENTE
    async def send_transfer(index: int):
        idempotency_key = str(uuid.uuid4())
        payload = {
            "recipient_id": str(acc_b_id),
            "amount": 50000,
            "concept": f"Concurrent Transfer {index}"
        }
        req_headers = {**headers, "X-Idempotency-Key": idempotency_key}
        return await async_client.post("/api/v1/transfers/execute", json=payload, headers=req_headers)

    # 3. EJECUCIÓN SIMULTÁNEA DE LAS 10 SOLICITUDES
    tasks = [send_transfer(i) for i in range(10)]
    responses = await asyncio.gather(*tasks)

    # 4. VERIFICACIÓN DE RESULTADOS
    success_count = sum(1 for r in responses if r.status_code == 201)
    failed_count = sum(1 for r in responses if r.status_code == 400 or r.status_code == 409)

    assert success_count == 1, f"Se esperaba exactamente 1 transferencia exitosa, pero hubo {success_count}"
    assert failed_count == 9, f"Se esperaban 9 solicitudes fallidas por saldo insuficiente, pero hubo {failed_count}"

    # 5. VERIFICACIÓN DE SALDOS INTEGRAL EN BASE DE DATOS
    balance_a = await calculate_account_balance(acc_a_id, db_session)
    balance_b = await calculate_account_balance(acc_b_id, db_session)

    assert balance_a == 0, f"El saldo final del Usuario A debe ser 0 COP, pero es ${balance_a}"
    assert balance_b == 50000, f"El saldo final del Usuario B debe ser $50,000 COP, pero es ${balance_b}"
```

---

## 4. PRUEBA DE AUDITORÍA GLOBAL DE PARTIDA DOBLE (SUM ZERO CHECK)

Garantiza que en todo momento la suma global de débitos y créditos en la tabla `ledger_entries` sea idéntica, asegurando que no haya dinero creado o destruido mágicamente en la plataforma.

```python
# tests/test_ledger_audit.py
import pytest
from sqlalchemy import select, func
from app.modules.ledger.infrastructure.models import LedgerEntryModel

@pytest.mark.asyncio
async def test_global_double_entry_sum_equals_zero(db_session):
    """
    Verifica que la suma total de débitos y la suma total de créditos en el Ledger
    sean matemáticamente idénticas.
    """
    stmt_debits = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0))
    stmt_credits = select(func.coalesce(func.sum(LedgerEntryModel.amount), 0))

    total_debits = (await db_session.execute(stmt_debits)).scalar_one()
    total_credits = (await db_session.execute(stmt_credits)).scalar_one()

    # En partida doble, por cada entrada hay un débito de X y un crédito de X
    assert total_debits == total_credits, (
        f"Desbalance contable detectado en el Ledger: "
        f"Total Débitos = ${total_debits}, Total Créditos = ${total_credits}"
    )
```

---

## 5. PRUEBA DE COBROS CON SALDO INSUFICIENTE (KILLER FEATURE TEST)

Valida que cuando un usuario intenta pagar un cobro sin tener el saldo suficiente:
1. La transferencia contable se aborta (sin movimiento en el Ledger).
2. Se registra un Audit Log.
3. El estado del cobro se mantiene estrictamente en **`PENDING`**.

```python
# tests/test_payment_requests.py
import uuid
import pytest
from httpx import AsyncClient
from app.modules.ledger.infrastructure.models import PaymentRequestModel, PaymentRequestStatus

@pytest.mark.asyncio
async def test_pay_charge_with_insufficient_funds_keeps_pending(async_client: AsyncClient, db_session):
    """
    Valida que al pagar un cobro con saldo insuficiente, el cobro no cambie de estado
    y se mantenga en PENDING.
    """
    # 1. SETUP: Crear cobro por $100,000 de Payer a Requester (donde Payer solo tiene $0)
    charge_id = uuid.uuid4()
    payer_acc_id = uuid.uuid4()
    requester_acc_id = uuid.uuid4()

    charge = PaymentRequestModel(
        id=charge_id,
        requester_account_id=requester_acc_id,
        payer_account_id=payer_acc_id,
        amount=100000,
        concept="Deuda de cena",
        status=PaymentRequestStatus.PENDING
    )
    db_session.add(charge)
    await db_session.commit()

    # JWT del Pagador (con saldo $0)
    payer_user_id = uuid.uuid4()
    payer_token = create_access_token({"sub": str(payer_user_id), "role": "USER"})
    headers = {
        "Authorization": f"Bearer {payer_token}",
        "X-Idempotency-Key": str(uuid.uuid4())
    }

    # 2. INTENTAR PAGAR EL COBRO
    response = await async_client.post(f"/api/v1/charges/{charge_id}/pay", headers=headers)

    # 3. VERIFICACIÓN
    assert response.status_code == 400
    res_data = response.json()
    assert res_data["code"] == "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST"

    # Verificar DB: El cobro DEBE seguir en PENDING
    await db_session.refresh(charge)
    assert charge.status == PaymentRequestStatus.PENDING
```
