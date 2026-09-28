# Backend HabiCapital

Python 3.12+, PostgreSQL 16.

## Inicio rápido con Docker

Desde la raíz del repositorio, copia la plantilla de entorno y levanta todo:

```bash
cp backend/.env.example backend/.env
docker compose up --build -d
```

La API queda en `http://localhost:8000/docs`. Compose espera a PostgreSQL,
ejecuta `alembic upgrade head` y luego inicia FastAPI. La contraseña local de
PostgreSQL está en `docker-compose.yml`; úsala solo para desarrollo.

Ejecuta las pruebas también desde la raíz:

```bash
docker compose --profile test run --rm tests
```

Para correr pytest en el host, instala dependencias y levanta la base:

```bash
python -m pip install -r backend/requirements.txt
docker compose up -d db
TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/habicapital_p2p_test python -m pytest -q
```

La configuración de pytest en la raíz agrega `backend/` al `PYTHONPATH`, por lo
que `pytest -q` funciona desde la raíz si pytest está en el PATH. La base
`habicapital_p2p_test` se crea al inicializar el volumen de PostgreSQL.

Las pruebas HTTP de idempotencia usan un almacén determinista; la API utiliza
`idempotency_records` persistidos en PostgreSQL.

An uncertain operation remains `PROCESSING` and a failed operation remains
`FAILED`; a retry with the same key returns 409 until its result is reconciled.
Do not delete such records by age without reconciling any possible ledger entry.

The current schema from SPEC-02 persists email, full name and concepts without
field encryption. AES-256-GCM and blind indexing from SPEC-03 v2 require a
separate schema and data migration before handling real personal data.

## Transferencias P2P

`POST /api/v1/transfers/execute` requiere el JWT del emisor y una llave UUIDv4
en `X-Idempotency-Key`. Usa el `recipient_id` obtenido de
`POST /api/v1/transfers/lookup`, un monto entero COP positivo y `concept`.
`GET /api/v1/ledger/balance` requiere JWT y devuelve el saldo derivado del libro.
La migración `ff2163b57e21` impide modificar o eliminar asientos existentes.

Una vez levantada la base, las pruebas que necesitan PostgreSQL se ejecutan sin
reiniciar Compose:

```bash
docker compose --profile test run --rm tests
```

Desde el host, configura `TEST_DATABASE_URL` como se indica arriba para ejecutar
las pruebas de integración; sin esta variable se omiten las pruebas de BD.
