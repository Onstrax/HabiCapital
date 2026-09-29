# SPEC-02: DATABASE & DOUBLE-ENTRY LEDGER SPECIFICATION
**Proyecto**: HabiCapital P2P Transactional Platform  
**Módulo**: Kernel Financiero, Base de Datos PostgreSQL & Libro Mayor de Partida Doble  
**Versión**: 1.0.0  
**Estado**: APORTADO / ESPECIFICACIÓN TÉCNICA SDD  

---

## 1. PRINCIPIOS ARQUITECTÓNICOS DEL LEDGER

1. **Regla Suprema de Integridad Financiera**: El saldo de un usuario jamás se almacena como un valor numérico estático editable (`UPDATE accounts SET balance = X`). El saldo es **exclusivamente un resultado derivado** calculado a partir del historial inmutable de asientos contables.
2. **Contabilidad de Partida Doble (Double-Entry Ledger)**: Todo movimiento monetario genera un registro en `ledger_entries` con una cuenta debitada (`debit_account_id`) y una cuenta acreditada (`credit_account_id`). La suma de todos los débitos y créditos en el sistema debe ser exactamente igual a cero ($\sum \text{Débitos} = \sum \text{Créditos}$).
3. **Unidad Monetaria Entera (Zero-Decimal COP)**: Los montos se representan como enteros de 64 bits (`BIGINT`). $1 \text{ unidad} = \$1 \text{ COP}$. Se prohíbe explícitamente el uso de tipos de datos en punto flotante (`FLOAT`, `DOUBLE`) o decimales arbitrarios para evitar errores de redondeo.
4. **Cuentas Ómnibus del Sistema (`SYSTEM_OMNIBUS`)**: Para operaciones de emisión/recarga de saldo (`TOPUP`) ejecutadas por el Administrador, se utiliza una cuenta ómnibus global del sistema. La recarga consiste en debitar a `SYSTEM_OMNIBUS` y acreditar a la cuenta del usuario.
5. **Aislamiento ACID & Bloqueo Pesimista**: Todas las transacciones monetarias ocurren bajo el nivel de aislamiento `READ COMMITTED` o `SERIALIZABLE`, utilizando bloqueos a nivel de fila (`SELECT ... FOR UPDATE`) ordenados alfabéticamente por UUID para evitar condiciones de carrera (*Race Conditions*) y interbloqueos (*Deadlocks*).

---

## 2. ESQUEMA DDL EN POSTGRESQL 16

```sql
-- HabiCapital P2P Database Schema - PostgreSQL 16
-- General Setup: Enable UUID Extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- 1. ENUMS & DOMAINS
-- -----------------------------------------------------------------------------
CREATE TYPE user_role AS ENUM ('ADMIN', 'USER');
CREATE TYPE account_type AS ENUM ('USER_WALLET', 'SYSTEM_OMNIBUS');
CREATE TYPE transaction_type AS ENUM ('TOPUP', 'P2P_TRANSFER', 'PAYMENT_REQUEST_PAYMENT');
CREATE TYPE transaction_status AS ENUM ('SUCCESS', 'FAILED');
CREATE TYPE payment_request_status AS ENUM ('PENDING', 'COMPLETED', 'REJECTED', 'CANCELLED');
CREATE TYPE idempotency_status AS ENUM ('PROCESSING', 'COMPLETED', 'FAILED');

-- -----------------------------------------------------------------------------
-- 2. USERS TABLE
-- -----------------------------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    alias VARCHAR(20) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    role user_role NOT NULL DEFAULT 'USER',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_alias_format CHECK (alias ~ '^[a-z0-9_]{3,20}$')
);

-- -----------------------------------------------------------------------------
-- 3. ACCOUNTS TABLE
-- -----------------------------------------------------------------------------
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    account_number VARCHAR(20) NOT NULL UNIQUE,
    type account_type NOT NULL DEFAULT 'USER_WALLET',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 4. TRANSACTIONS TABLE (Agrupador Operativo)
-- -----------------------------------------------------------------------------
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reference_id VARCHAR(50) NOT NULL UNIQUE,
    type transaction_type NOT NULL,
    status transaction_status NOT NULL,
    concept VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 5. LEDGER_ENTRIES TABLE (Libro Mayor Inmutable)
-- -----------------------------------------------------------------------------
CREATE TABLE ledger_entries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    transaction_id UUID NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
    debit_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    credit_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    amount BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_positive_amount CHECK (amount > 0),
    CONSTRAINT chk_different_accounts CHECK (debit_account_id <> credit_account_id)
);

-- -----------------------------------------------------------------------------
-- 6. PAYMENT_REQUESTS TABLE (Killer Feature: Cobros P2P)
-- -----------------------------------------------------------------------------
CREATE TABLE payment_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    requester_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    payer_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
    amount BIGINT NOT NULL,
    concept VARCHAR(255) NOT NULL,
    status payment_request_status NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_pr_positive_amount CHECK (amount > 0),
    CONSTRAINT chk_pr_different_accounts CHECK (requester_account_id <> payer_account_id)
);

-- -----------------------------------------------------------------------------
-- 7. IDEMPOTENCY_RECORDS TABLE
-- -----------------------------------------------------------------------------
CREATE TABLE idempotency_records (
    key UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_hash VARCHAR(64) NOT NULL,
    status idempotency_status NOT NULL DEFAULT 'PROCESSING',
    response_code SMALLINT NULL,
    response_body JSONB NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- -----------------------------------------------------------------------------
-- 8. AUDIT_LOGS TABLE
-- -----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address VARCHAR(45) NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- 9. STRATEGIC INDEXES FOR OPTIMIZATION
-- -----------------------------------------------------------------------------
-- Lookup rápido por usuario, alias y email
CREATE UNIQUE INDEX idx_users_email ON users(email);
CREATE UNIQUE INDEX idx_users_alias ON users(alias);

-- Índices de Ledger para cálculo veloz de saldo y extractos
CREATE INDEX idx_ledger_debit_acc ON ledger_entries(debit_account_id);
CREATE INDEX idx_ledger_credit_acc ON ledger_entries(credit_account_id);
CREATE INDEX idx_ledger_created_at ON ledger_entries(created_at DESC);

-- Índices para Payment Requests
CREATE INDEX idx_payment_requests_payer_status ON payment_requests(payer_account_id, status);
CREATE INDEX idx_payment_requests_requester_status ON payment_requests(requester_account_id, status);

-- Índice para limpieza y consulta de idempotencia
CREATE INDEX idx_idempotency_expires ON idempotency_records(expires_at);
```

---

## 3. MODELOS SQLALCHEMY 2.0 (PYTHON DTOs & ORM)

```python
# app/modules/ledger/infrastructure/models.py
import enum
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Boolean, BigInteger, SmallInteger, CheckConstraint, ForeignKey, Index, Text, Enum as SQLEnum
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class AccountType(str, enum.Enum):
    USER_WALLET = "USER_WALLET"
    SYSTEM_OMNIBUS = "SYSTEM_OMNIBUS"

class TransactionType(str, enum.Enum):
    TOPUP = "TOPUP"
    P2P_TRANSFER = "P2P_TRANSFER"
    PAYMENT_REQUEST_PAYMENT = "PAYMENT_REQUEST_PAYMENT"

class TransactionStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class PaymentRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

    account: Mapped[Optional["AccountModel"]] = relationship("AccountModel", back_populates="user", uselist=False)

class AccountModel(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False)
    account_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    type: Mapped[AccountType] = mapped_column(SQLEnum(AccountType), default=AccountType.USER_WALLET, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

    user: Mapped["UserModel"] = relationship("UserModel", back_populates="account")

class TransactionModel(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    type: Mapped[TransactionType] = mapped_column(SQLEnum(TransactionType), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(SQLEnum(TransactionStatus), nullable=False)
    concept: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

class LedgerEntryModel(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="RESTRICT"), nullable=False)
    debit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    credit_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("amount > 0", name="chk_positive_amount"),
        CheckConstraint("debit_account_id <> credit_account_id", name="chk_different_accounts"),
    )
```

---

## 4. CÁLCULO INMUTABLE DE SALDO CONTABLE

El saldo de una cuenta se calcula agregando los débitos (salidas) y créditos (entradas):

$$\text{Saldo}_{\text{cuenta}} = \sum \text{Créditos Recibidos} - \sum \text{Débitos Enviados}$$

### Función de Cálculo de Saldo en Python / SQLAlchemy

```python
# app/modules/ledger/domain/services.py
import uuid
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.ledger.infrastructure.models import LedgerEntryModel

async def calculate_account_balance(account_id: uuid.UUID, session: AsyncSession) -> int:
    """
    Calcula de forma exacta e inmutable el saldo actual de una cuenta en COP.
    Retorna un número entero (BIGINT).
    """
    stmt = select(
        func.coalesce(
            func.sum(
                case(
                    (LedgerEntryModel.credit_account_id == account_id, LedgerEntryModel.amount),
                    else_=0
                )
            ), 0
        ) - func.coalesce(
            func.sum(
                case(
                    (LedgerEntryModel.debit_account_id == account_id, LedgerEntryModel.amount),
                    else_=0
                )
            ), 0
        )
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())
```

---

## 5. ALGORITMO DE BLOQUEO PESIMISTA & PREVENCIÓN DE RACE CONDITIONS

Para garantizar que ningún usuario pueda sobregirar su cuenta enviando dos solicitudes concurrentes al mismo milisegundo:

### Algoritmo de Prevención de Deadlocks por Ordenamiento de UUIDs

Si el Usuario A (UUID `0000...2`) envía dinero al Usuario B (UUID `0000...1`), y simultáneamente el Usuario B envía dinero al Usuario A:
* Un intento ingenuo bloquearía A luego B en una llamada, y B luego A en la otra, causando un **Deadlock DB**.
* **Solución Innegociable**: Las cuentas involucradas en una transacción **SIEMPRE se bloquean en orden alfabético/numérico ascendente de sus UUIDs**.

```python
# app/modules/ledger/use_cases/transfer_money.py
import uuid
import logging
from typing import Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ledger.infrastructure.models import (
    AccountModel, TransactionModel, LedgerEntryModel,
    TransactionType, TransactionStatus
)
from app.modules.ledger.domain.services import calculate_account_balance
from app.shared.exceptions import InsufficientFundsException, AccountNotFoundException

logger = logging.getLogger(__name__)

async def execute_p2p_transfer_transactional(
    session: AsyncSession,
    sender_account_id: uuid.UUID,
    recipient_account_id: uuid.UUID,
    amount: int,
    concept: str,
    reference_id: str
) -> TransactionModel:
    """
    Ejecuta una transferencia P2P con bloqueo pesimista estricto y atomicidad ACID.
    """
    if amount <= 0:
        raise ValueError("El monto de la transferencia debe ser mayor a cero.")
    if sender_account_id == recipient_account_id:
        raise ValueError("No se permiten auto-transferencias.")

    # 1. ORDENAMIENTO DE UUIDs PARA EVITAR DEADLOCKS
    first_id, second_id = sorted([sender_account_id, recipient_account_id])

    # 2. BLOQUEO PESIMISTA (SELECT ... FOR UPDATE)
    stmt = (
        select(AccountModel)
        .where(AccountModel.id.in_([first_id, second_id]))
        .order_by(AccountModel.id.asc())
        .with_for_update()
    )
    result = await session.execute(stmt)
    locked_accounts = {acc.id: acc for acc in result.scalars().all()}

    if sender_account_id not in locked_accounts:
        raise AccountNotFoundException(f"Cuenta emisora {sender_account_id} no encontrada.")
    if recipient_account_id not in locked_accounts:
        raise AccountNotFoundException(f"Cuenta receptora {recipient_account_id} no encontrada.")

    # 3. VERIFICACIÓN DE SALDO DENTRO DE LA TRANSACCIÓN BLOQUEADA
    sender_balance = await calculate_account_balance(sender_account_id, session)

    if sender_balance < amount:
        logger.warning(
            f"Transferencia fallida por saldo insuficiente. Account: {sender_account_id}, "
            f"Saldo: {sender_balance}, Monto requerido: {amount}"
        )
        raise InsufficientFundsException(
            f"Saldo insuficiente. Saldo actual: ${sender_balance} COP, Intentado: ${amount} COP"
        )

    # 4. REGISTRO DE LA TRANSACCIÓN
    tx = TransactionModel(
        id=uuid.uuid4(),
        reference_id=reference_id,
        type=TransactionType.P2P_TRANSFER,
        status=TransactionStatus.SUCCESS,
        concept=concept
    )
    session.add(tx)
    await session.flush()  # Obtener tx.id

    # 5. INSERCIÓN DEL ASIENTO EN EL LEDGER (PARTIDA DOBLE)
    ledger_entry = LedgerEntryModel(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        debit_account_id=sender_account_id,    # Cuenta que sale el dinero
        credit_account_id=recipient_account_id, # Cuenta que recibe el dinero
        amount=amount
    )
    session.add(ledger_entry)

    # El COMMIT es manejado por el gestor de la unidad de trabajo / use case caller
    return tx
```

---

## 6. MATRIZ DE CRITERIOS DE ACEPTACIÓN & TDD QA GATES

| Test ID | Escenario de Prueba | Comportamiento Esperado | Criterio de Éxito DB |
| :--- | :--- | :--- | :--- |
| **TC-DB-01** | Transferencia con saldo suficiente | Asiento insertado correctamente | Balance del emisor disminuye exactamente `amount`, receptor incrementa `amount`. |
| **TC-DB-02** | Transferencia con saldo insuficiente | Aborta con `InsufficientFundsException` | Ninguna fila insertada en `ledger_entries` ni `transactions`. Transaction rollback. |
| **TC-DB-03** | Solicitudes simultáneas en paralelo (Race Condition) | Ejecución secuencial por `FOR UPDATE` | Una transacción se ejecuta con éxito, la segunda falla por saldo insuficiente sin sobregiro. |
| **TC-DB-04** | Inserción de monto negativo o cero | Rechazo a nivel de DB Check Constraint | Lanza `IntegrityError` por `chk_positive_amount`. |
| **TC-DB-05** | Intentar auto-transferencia (`debit_account == credit_account`) | Rechazo a nivel de DB Check Constraint | Lanza `IntegrityError` por `chk_different_accounts`. |
