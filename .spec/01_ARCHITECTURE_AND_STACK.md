# Especificación Técnica SDD - Documento 01: Arquitectura, Stack Tecnológico e Infraestructura ($0 USD)

**Proyecto:** HabiCapital - Sistema Transaccional P2P
**Versión:** 1.0.0
**Estado:** Aprobado por el Product Owner (P.O.)
**Autor:** Arquitecto de Soluciones Senior & Lead Software Engineer
**Público Objetivo:** Agente de Desarrollo IA / Desarrollador Fullstack Senior

---

## 1. Visión General de Arquitectura

El sistema HabiCapital P2P se diseña bajo el patrón de **Monolito Modular con Clean Architecture (Arquitectura Limpia)**. El objetivo primordial es garantizar la **Regla Suprema: "El sistema no puede perder un peso"**, priorizando la consistencia e integridad transaccional ACID, la mantenibilidad mediante desarrollo orientado a especificación (SDD) y TDD estricto, y el cumplimiento de la **Restricción de Costo Cero ($0 USD)** para despliegue y desarrollo.

```
+-----------------------------------------------------------------------+
|                         CAPA DE PRESENTACIÓN                          |
|                  Next.js 14 (App Router + TypeScript)                 |
+-----------------------------------------------------------------------+
                                    |
                                    | REST API / JSON + JWT + Idempotency
                                    v
+-----------------------------------------------------------------------+
|                          BACKEND FASTAPI                              |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  | Adapters / Controllers (FastAPI Endpoints + Pydantic DTOs)     |  |
|  +-----------------------------------------------------------------+  |
|                                   |                                   |
|  +-----------------------------------------------------------------+  |
|  | Use Cases / Application (Orquestación Transaccional & Rules)    |  |
|  +-----------------------------------------------------------------+  |
|                                   |                                   |
|  +-----------------------------------------------------------------+  |
|  | Domain Kernel (Entidades, Value Objects, Reglas Financieras)     |  |
|  +-----------------------------------------------------------------+  |
|                                   |                                   |
|  +-----------------------------------------------------------------+  |
|  | Infrastructure (SQLAlchemy 2.0 ORM, Postgres, Security Services) |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
                                    |
                                    v
+-----------------------------------------------------------------------+
|                    BASE DE DATOS RELACIONAL                            |
|             PostgreSQL 16 (Supabase / Neon.tech Free Tier)            |
|             - Bloqueos Pesimistas SELECT ... FOR UPDATE              |
|             - Asientos de Partida Doble (Ledger Inmutable)            |
+-----------------------------------------------------------------------+
```

---

## 2. Definición del Stack Tecnológico

### 2.1 Backend Stack
* **Lenguaje:** Python 3.12+ (Aprovechamiento de optimizaciones de performance y tipado fuerte).
* **Framework Web:** FastAPI (Alta velocidad, soporte nativo async, generación automática de OpenAPI/Swagger).
* **Validación & DTOs:** Pydantic v2 (`extra='forbid'`, strict mode, validadores custom).
* **ORM & Database Client:** SQLAlchemy 2.0 (patrón DeclarativeMapping + Session transaccional con `with_for_update`).
* **Migraciones de Base de Datos:** Alembic (control de versiones DDL inmutable).
* **Seguridad & Hashing:**
  * Hashing de Passwords: `passlib[argon2]` (Algoritmo Argon2id con parámetros OWASP recomendados).
  * Autenticación JWT: `python-jose[cryptography]` / `PyJWT` (RS256/HS256 con firmas HMAC-SHA256).
* **Rate Limiting:** `slowapi` (implementación en memoria basada en Token Bucket).
* **Suite de Pruebas (TDD):** `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, `factory-boy`.

### 2.2 Frontend Stack
* **Framework:** Next.js 14+ (React 18+, App Router, Server Components para vistas públicas, Client Components para Dashboard interactivo).
* **Lenguaje:** TypeScript 5.0+ (Modo estricto `strict: true` activado).
* **Estilos & UI:** Tailwind CSS v3 + `shadcn/ui` / componentes accesibles nativos.
* **Iconografía:** `lucide-react`.
* **Manejo de Formularios & Validación:** `react-hook-form` + `zod` (esquemas espejados con Pydantic).
* **Cliente HTTP & Estado Servidor:** TanStack Query v5 (`@tanstack/react-query`) con reintentos controlados y manejo explícito de cabecera `X-Idempotency-Key`.

### 2.3 Infraestructura & Base de Datos ($0 USD)
* **Base de Datos:** PostgreSQL 16 managed en **Supabase Free Tier** o **Neon.tech Serverless Postgres**.
* **Hosting Backend:** **Render.com Free Web Service** o **Koyeb / Fly.io Free Tier**.
* **Hosting Frontend:** **Vercel Free Tier**.
* **Integración Continua (CI):** **GitHub Actions** (2,000 minutos/mes gratuitos para repositorios públicos/privados).

---

## 3. Estructura Completa del Proyecto

El repositorio mantendrá la estructura de Monolito Modular tanto en Backend como en Frontend:

```text
habicapital-p2p/
├── .github/
│   └── workflows/
│       └── ci.yml                      # Pipeline de Integración Continua (Linter, Tests, Security)
├── backend/
│   ├── app/
│   │   ├── core/                       # Kernel global del sistema
│   │   │   ├── config.py               # Configuración centralizada Pydantic Settings
│   │   │   ├── database.py             # Engine SQLAlchemy, SessionLocal y Manejo de Transacciones
│   │   │   ├── security.py             # Argon2id password hashing, JWT generation & verification
│   │   │   ├── middlewares.py          # Idempotency Middleware, Rate Limiter, CORS & Security Headers
│   │   │   └── exceptions.py           # Excepciones globales del dominio y handlers HTTP
│   │   ├── modules/
│   │   │   ├── identity/               # Módulo de Autenticación, Usuarios y Roles
│   │   │   │   ├── domain/             # Entidades User, Role, Value Objects (Email, Alias)
│   │   │   │   ├── use_cases/          # RegisterUser, AuthenticateUser, LookupRecipient
│   │   │   │   ├── infrastructure/     # SQLAlchemyUserModel, UserRepository
│   │   │   │   └── adapters/           # AuthController, UserDTOs (Pydantic)
│   │   │   ├── ledger/                 # Módulo de Núcleo Financiero y Libro Mayor
│   │   │   │   ├── domain/             # Entidades Account, LedgerEntry, Transaction, Rules
│   │   │   │   ├── use_cases/          # CalculateBalance, ExecuteTransfer, AdminTopUp
│   │   │   │   ├── infrastructure/     # AccountModel, LedgerEntryModel, TransactionModel
│   │   │   │   └── adapters/           # LedgerController, TransferDTOs
│   │   │   ├── payment_requests/       # Módulo de Cobros P2P (Payment Requests)
│   │   │   │   ├── domain/             # Entidad PaymentRequest, PaymentRequestStatus Machine
│   │   │   │   ├── use_cases/          # CreateChargeRequest, ProcessChargePayment, RejectCharge
│   │   │   │   ├── infrastructure/     # PaymentRequestModel
│   │   │   │   └── adapters/           # PaymentRequestController, PaymentRequestDTOs
│   │   │   └── audit/                  # Módulo de Auditoría Inmutable
│   │   │       ├── domain/             # Entidad AuditLog, ActionTypes
│   │   │       ├── use_cases/          # RecordAuditLog
│   │   │       ├── infrastructure/     # AuditLogModel, AuditLogRepository
│   │   │       └── adapters/           # AuditController (Admin view)
│   │   ├── shared/                     # Kernel compartido sin dependencias externas
│   │   │   ├── domain/                 # BaseEntity, ValueObject, DomainException
│   │   │   └── utils/                  # MaskingUtils (Name masking), DateTimeUtils
│   │   ├── scripts/
│   │   │   └── seed_admin.py           # Script idóneo para inyección idempotente de Admin inicial
│   │   └── main.py                     # Punto de entrada FastAPI (Inclusión de Routers & Middlewares)
│   ├── alembic/                        # Archivos de migración DDL
│   ├── tests/                          # Suite de Pruebas TDD
│   │   ├── conftest.py                 # Fixtures Pytest (DB efímera, Clientes HTTP, Tokens JWT)
│   │   ├── unit/                       # Pruebas unitarias puras del Dominio y Reglas
│   │   ├── integration/                # Pruebas de integración con DB PostgreSQL real
│   │   └── concurrency/                # Pruebas de estrés y Race Conditions (SELECT FOR UPDATE)
│   ├── .env.example                    # Plantilla de variables de entorno
│   ├── Dockerfile                      # Contenedor optimizado de producción
│   ├── pyproject.toml                  # Configuración de dependencias (Poetry/Pipenv/Ruff/Pytest)
│   └── requirements.txt                # Lockfile de producción
└── frontend/
    ├── src/
    │   ├── app/                        # Next.js App Router (Páginas y Layouts)
    │   │   ├── (auth)/                 # Rutas de Autenticación (/login, /register)
    │   │   ├── (dashboard)/            # Rutas autenticadas (/dashboard, /transfer, /charges, /admin)
    │   │   ├── api/                    # BFF / Next.js API Routes (si aplica)
    │   │   └── layout.tsx              # Root Layout con Providers (QueryClientProvider, AuthProvider)
    │   ├── components/                 # Componentes UI reutilizables
    │   │   ├── ui/                     # Botones, Modales, Inputs, Badges, Skeleton Loader
    │   │   ├── transfer/               # Formulario 2-Step Transfer, Confirmation Modal
    │   │   └── charges/                # Payment Request Cards, Status Badges
    │   ├── lib/                        # Clientes API, Axios/Fetch Instance con Idempotency Header
    │   │   ├── api-client.ts
    │   │   └── utils.ts
    │   ├── hooks/                      # Custom Hooks (useAuth, useTransfer, useCharges)
    │   └── types/                      # TypeScript Interfaces espejadas con Backend DTOs
    ├── .env.example
    ├── package.json
    └── tailwind.config.js
```

---

## 4. Reglas Estrictas de Capas (Clean Architecture)

1. **Capa Domain (Dominio):**
   * Contiene únicamente código Python puro (clases estándar, dataclasses o Pydantic models de dominio).
   * **PROHIBIDO** importar FastAPI, SQLAlchemy, Alembic o librerías HTTP en esta capa.
   * Contiene las excepciones del negocio (`InsufficientBalanceException`, `SelfTransferForbiddenException`).

2. **Capa Use Cases (Aplicación):**
   * Orquesta la lógica del negocio. Recibe puertos (interfaces/repositorios) y ejecuta las reglas del dominio.
   * Maneja las transacciones explícitas de Base de Datos. Cada caso de uso mutativo ejecuta un bloque transaccional atómico:
     `BEGIN TRANSACTION` -> `Bloqueo Pesimista` -> `Modificación Ledger` -> `Audit Log` -> `COMMIT`.

3. **Capa Infrastructure (Infraestructura):**
   * Implementa el ORM SQLAlchemy, modelos de tablas SQL, llamadas a servicios de hash/crypto y conexión a PostgreSQL.

4. **Capa Adapters / Controllers (Presentación Backend):**
   * Puntos de entrada FastAPI (`APIRouter`). Valida parámetros de entrada mediante esquemas Pydantic y captura excepciones de dominio para mapearlas a respuestas HTTP estructuradas (`400 Bad Request`, `409 Conflict`, `422 Unprocessable Entity`).

---

## 5. Especificación de Configuración y Variables de Entorno

El backend cargará la configuración estrictamente desde variables de entorno validadas en el arranque del servidor mediante `pydantic-settings`.

### 5.1 Schema del Backend (`app/core/config.py`)
```python
from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "HabiCapital P2P API"
    ENVIRONMENT: str = Field("development", description="development | staging | production")
    DEBUG: bool = False
    
    # Base de Datos PostgreSQL
    DATABASE_URL: PostgresDsn = Field(..., description="PostgreSQL Connection String con SSL habilitado")
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    
    # Seguridad JWT & Crypto
    JWT_SECRET_KEY: str = Field(..., min_length=64, description="Secret Key estricta HMAC-SHA256")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    
    # Admin Seed Inicial
    ADMIN_EMAIL: str = Field("admin@habicapital.co")
    ADMIN_PASSWORD: str = Field(..., min_length=12)
    ADMIN_ALIAS: str = Field("admin_system")
    
    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "https://habicapital.vercel.app"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
```

### 5.2 Plantilla `.env.example` (Backend)
```env
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=postgresql://postgres:password@localhost:5432/habicapital_p2p?sslmode=prefer
JWT_SECRET_KEY=e83a9f02c91b4522810d2948e02d847129384729103847291029384729102938
ADMIN_EMAIL=admin@habicapital.co
ADMIN_PASSWORD=AdminSecurePassword2027!
ADMIN_ALIAS=admin_system
CORS_ORIGINS=["http://localhost:3000"]
```

---

## 6. Estrategia de Infraestructura y Despliegue Costo \$0 USD

Para asegurar que la solución no genere costos recurrentes ni al desarrollador ni a los usuarios evaluadores, se adopta la siguiente topología de despliegue gratuito:

| Componente | Proveedor Free Tier | Capacidades Incluidas | Estrategia de Mitigación / Cold-Start |
| :--- | :--- | :--- | :--- |
| **Database** | Supabase Postgres / Neon.tech | 500 MB almacenamiento, PostgreSQL 16, SSL nativo, Conneciton Pooling. | Auto-suspend tras inactividad. La primera petición realiza reconexión transparente. |
| **Backend API** | Render.com Free Web Service | 512 MB RAM, HTTPS automático, despliegue continuo desde GitHub. | Render apaga la instancia tras 15 min de inactividad. **Mitigación:** En la UI Frontend, se muestra un indicador "Despertando servidor seguro..." si el primer ping toma más de 3s. |
| **Frontend UI** | Vercel Free Tier | Edge Network global, Next.js optimizado, HTTPS, CDN ilimitado. | Alta disponibilidad continua (Sin sleep). |
| **CI/CD Pipeline**| GitHub Actions | 2,000 minutos/mes de ejecución de runners Ubuntu. | Pipeline efímero que levanta PostgreSQL via Docker Service para pruebas TDD. |

---

## 7. Pipeline CI/CD Automatizado (`.github/workflows/ci.yml`)

El pipeline garantiza que ningún código se fusione en `main` si rompe la consistencia financiera, no cumple con los linters o falla en las pruebas de concurrencia TDD.

```yaml
name: HabiCapital CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  backend-quality-and-tests:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
          POSTGRES_DB: habicapital_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - name: Checkout Código
        uses: actions/checkout@v4

      - name: Configurar Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Instalar Dependencias Backend
        run: |
          python -m pip install --upgrade pip
          pip install ruff pytest pytest-cov pytest-asyncio httpx alembic passlib[argon2] python-jose[cryptography] pydantic pydantic-settings sqlalchemy psycopg2-binary slowapi

      - name: Linter & Format Check (Ruff)
        run: |
          ruff check backend/app
          ruff format --check backend/app

      - name: Análisis de Seguridad SAST (Bandit)
        run: |
          pip install bandit
          bandit -r backend/app -x backend/tests

      - name: Ejecutar Migraciones Alembic en DB Test
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/habicapital_test
        run: |
          cd backend
          alembic upgrade head

      - name: Ejecutar Suite TDD & Concurrencia (Pytest)
        env:
          DATABASE_URL: postgresql://test_user:test_password@localhost:5432/habicapital_test
          JWT_SECRET_KEY: test_secret_key_must_be_very_long_and_secure_64_bytes_test_suite_key!
          ENVIRONMENT: test
        run: |
          cd backend
          pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=90

  frontend-quality:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Código
        uses: actions/checkout@v4

      - name: Configurar Node.js 20
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json

      - name: Instalar Dependencias Frontend
        run: |
          cd frontend
          npm ci

      - name: Typecheck TypeScript (tsc)
        run: |
          cd frontend
          npm run typecheck

      - name: ESLint Check
        run: |
          cd frontend
          npm run lint
