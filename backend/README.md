# Backend HabiCapital

Python 3.12+, PostgreSQL 16.

## Inicio rápido con Docker

Desde la raíz del repositorio, copia la plantilla de entorno y levanta todo:

```bash
cp backend/.env.example backend/.env
cd backend
python -m scripts.init_pii_keys
cd ..
docker compose up --build -d
```

La API queda en `http://localhost:8000/docs`. Compose espera a PostgreSQL,
ejecuta `alembic upgrade head` y luego inicia FastAPI. La contraseña local de
PostgreSQL está en `docker-compose.yml`; úsala solo para desarrollo.

Para probar rutas protegidas desde `/docs`, ejecuta `POST /api/v1/auth/login`,
copia `access_token` de la respuesta y pulsa **Authorize** arriba a la derecha.
Pega solo el token (sin `Bearer `); Swagger añade el encabezado en cada petición
protegida. Las operaciones financieras muestran además el campo obligatorio
`X-Idempotency-Key`: usa un UUIDv4 nuevo para cada operación distinta.

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

## Privacidad de datos existentes

Antes de levantar la API con esta versión, realiza un respaldo de PostgreSQL y
de `backend/.env`. Crea las dos claves PII **antes** de ejecutar Alembic:

```bash
cd backend
python -m scripts.init_pii_keys
cd ..
docker compose up --build -d
docker compose exec api alembic current
```

El inicio de la API aplica automáticamente la migración `c82e91d7a0f4` en una
transacción. Esta cifra los correos, nombres, alias, conceptos, payloads de
auditoría, IP y respuestas de idempotencia mediante AES-256-GCM, y agrega índices
ciegos HMAC para búsquedas exactas de correo y alias. Conserva estas claves sin
rotarlas ni perderlas: sin ellas la información cifrada no puede recuperarse.
El hash de contraseña Argon2id y los identificadores técnicos permanecen tal
como estaban. Los respaldos previos, WAL y volcados históricos pueden seguir
conteniendo los datos anteriores en texto plano y deben gestionarse aparte.
No ejecutes una versión vieja del backend sobre el esquema nuevo.

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

## Cobros y recargas administrativas

Después de aplicar las migraciones y configurar credenciales únicas en
`backend/.env`, crea el administrador y la cuenta ómnibus **una sola vez**:

```bash
docker compose exec api python -m app.core.bootstrap_admin
```

El comando es idempotente: no restablece la contraseña ni crea otra cuenta si ya
existen. `POST /api/v1/admin/topup` exige JWT de un `ADMIN` activo y llave
`X-Idempotency-Key` UUIDv4; recibe `target_user_alias`, `amount` entero en COP y
`concept`. El saldo nuevo se calcula con el libro mayor.

Si olvidaste la contraseña del administrador, vuelve a construir/iniciar la API
y ejecuta el asistente interactivo. Solicita la nueva contraseña dos veces sin
mostrarla, actualiza únicamente el hash Argon2id del administrador configurado
en `ADMIN_EMAIL` y registra el cambio en auditoría:

```bash
docker compose up -d --build api
docker compose exec -it api python -m app.core.admin_password_reset
```

El restablecimiento no cambia el libro mayor, el rol ni la cuenta ómnibus. La
contraseña nueva queda guardada en la base de datos; volver a ejecutar el
bootstrap no la modifica.

El cobro se crea en `POST /api/v1/charges` usando `payer_alias`, `amount` y
`concept`. El pagador puede usar `POST /api/v1/charges/{charge_id}/pay` (requiere
llave idempotente) o `/reject`; el solicitante puede usar `/cancel`. Las acciones
sobre estados terminales reciben 409. Un pago sin fondos devuelve 400, deja el
cobro en `PENDING` y guarda la auditoría del intento, sin crear asientos.

## Auditoría contable y cobertura

La suite incluye diez transferencias simultáneas desde una cuenta con 50.200 COP (50.000 de principal y 200 de GMF)
y comprueba que exactamente una resulte exitosa, así como una auditoría global
de débitos, créditos y saldos. Cada prueba usa un esquema PostgreSQL temporal y
sesiones independientes por solicitud concurrente.

Desde la raíz del repositorio, con la base de test en marcha:

```bash
docker compose --profile test run --build --rm tests pytest tests/ --cov=app --cov-report=term-missing
```

La configuración exige cobertura **superior al 90 %** cuando se ejecuta con
`--cov`. Si se usa pytest en el host, define `TEST_DATABASE_URL` apuntando a la
base `habicapital_p2p_test`; sin PostgreSQL se omiten las pruebas de integración
y la puerta de cobertura falla.


## Retención GMF 4x1000

Transferencias y pagos de cobros debitan principal más max(1, principal * 4 // 1000),
exclusivamente con enteros COP. Dos asientos balanceados acreditan el principal
al destinatario y el impuesto al colector SYSTEM_TAX_GMF. Recargas administrativas,
cancelaciones y rechazos están exentos.

La migración a41f0c9b2d63 conserva el historial y crea el colector sin usuario ni
credenciales. Las transacciones anteriores mantienen GMF cero. El UUID por defecto
es 00000000-0000-4000-8000-000000000004; SYSTEM_TAX_GMF_ACCOUNT_ID permite elegirlo
antes de inicializar el sistema. No cambiarlo después de registrar impuestos.

Las tres cuentas se bloquean en orden de UUID y ambos asientos se registran en
una única transacción. El colector compartido serializa parte de las operaciones
concurrentes, un compromiso explícito de simplicidad e integridad para este alcance.
La API devuelve gmf_tax y total_debit; lookup acepta amount opcional para cotizar.
El GMF de cada cobro se registra únicamente al pagar. Cada destinatario de un split
paga el impuesto de su propia parte, incluido el mínimo de un peso. La interfaz
muestra el desglose antes de confirmar. Esta regla del reto no implementa exenciones
ni procedimientos de declaración tributaria de un sistema real.
