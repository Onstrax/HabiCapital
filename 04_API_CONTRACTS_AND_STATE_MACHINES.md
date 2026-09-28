# SPEC-04: API CONTRACTS, DTOs & STATE MACHINES SPECIFICATION
**Proyecto**: HabiCapital P2P Transactional Platform  
**Módulo**: Especificación de Contratos OpenAPI v3, DTOs Pydantic v2 y Máquina de Estados de Cobros  
**Versión**: 1.0.0  
**Estado**: APROBADO / ESPECIFICACIÓN TÉCNICA SDD  

---

## 1. ESTÁNDAR GENERAL DE CONTRATOS Y RESPUESTAS HTTP

1. **Prefijo Base API**: `/api/v1`
2. **Formato de Payload**: JSON (`Content-Type: application/json`)
3. **Manejo Estándar de Errores**: Todas las respuestas de error retornan un objeto JSON con estructura fija:
   ```json
   {
     "code": "INSUFFICIENT_FUNDS",
     "message": "Saldo insuficiente para completar esta operación.",
     "details": {
       "current_balance": 10000,
       "required_amount": 50000
     },
     "timestamp": "2026-09-27T21:45:00Z"
   }
   ```
4. **Mapeo de Códigos de Estado HTTP**:
   * `200 OK`: Operación exitosa de lectura o actualización.
   * `201 Created`: Recurso creado exitosamente (Registro, Transferencia, Cobro).
   * `400 Bad Request`: Error de validación de sintaxis o reglas de negocio (Monto <= 0).
   * `401 Unauthorized`: Token JWT ausente, expirado o inválido.
   * `403 Forbidden`: Intento de acceso sin permisos (ej. Usuario estándar intentando TopUp).
   * `404 Not Found`: Recurso no encontrado (Alias de usuario o ID de cobro inexistente).
   * `409 Conflict`: Conflicto de estado o solicitud idempotente en proceso.
   * `422 Unprocessable Entity`: Error de validación de esquema Pydantic.
   * `429 Too Many Requests`: Superado el límite de Rate Limiting.

---

## 2. MÁQUINA DE ESTADOS DEL COBRO P2P (*PAYMENT REQUESTS*)

El flujo de cobros (*Killer Feature*) implementa una máquina de estados determinista e inmutable una vez alcanzado un estado final.

```text
               +-------------------+
               |  POST /charges    |
               +---------+---------+
                         |
                         v
                   +-----------+
                   |  PENDING  | <------------------------+
                   +-----+-----+                          |
                         |                                |
        +----------------+----------------+               | Intento de pago
        |                |                |               | con saldo insuficiente:
        v                v                v               | - Aborta transacción
  [Aceptar y Pagar]  [Rechazar]      [Cancelar]           | - Registra Audit Log
        |                |                |               | - Se MANTIENE en PENDING
        v                v                v               +------------------------+
  Verificar Saldo?      Estado:          Estado:
   /          \       REJECTED         CANCELLED
 [Suficiente] [Insuficiente]
      |              |
      v              +------------------------------------+
  Transacción DB:
  - Ledger Entry Debit/Credit
  - Audit Log
  - Estado: COMPLETED
```

### Tabla de Transiciones de Estado Permisibles

| Estado Actual | Acción / Endpoint | Rol Permitido | Estado Resultante | Efecto Contable en Ledger |
| :--- | :--- | :--- | :--- | :--- |
| **-** | `POST /api/v1/charges` | Solicitante (`requester`) | `PENDING` | Ninguno (Sin movimiento monetario). |
| `PENDING` | `POST /api/v1/charges/{id}/pay` | Pagador (`payer`) con saldo suficiente | `COMPLETED` | **Inmutable**: Débito a `payer`, Crédito a `requester`. |
| `PENDING` | `POST /api/v1/charges/{id}/pay` | Pagador (`payer`) con saldo insuficiente | `PENDING` | **Ninguno**. Aborta transacción DB y crea Audit Log de fallo. |
| `PENDING` | `POST /api/v1/charges/{id}/reject` | Pagador (`payer`) | `REJECTED` | Ninguno. |
| `PENDING` | `POST /api/v1/charges/{id}/cancel` | Solicitante (`requester`) | `CANCELLED` | Ninguno. |
| `COMPLETED` | Cualquier acción | N/A | **Bloqueado** | Estado terminal. No se permiten cambios. |
| `REJECTED` | Cualquier acción | N/A | **Bloqueado** | Estado terminal. No se permiten cambios. |
| `CANCELLED` | Cualquier acción | N/A | **Bloqueado** | Estado terminal. No se permiten cambios. |

---

## 3. ESPECIFICACIÓN DETALLADA DE ENDPOINTS & DTOs

### 1. Módulo de Autenticación (`/auth`)

#### `POST /api/v1/auth/register`
* **Descripción**: Crea una nueva cuenta de usuario y asigna automáticamente su billetera P2P.
* **Request Body**:
  ```json
  {
    "email": "usuario@ejemplo.com",
    "alias": "juan_p2p",
    "password": "PasswordSegura123!",
    "full_name": "Juan Esteban Gómez"
  }
  ```
* **Response (HTTP 201 Created)**:
  ```json
  {
    "id": "3a110a2b-1234-4a5b-8c6d-9e0f1a2b3c4d",
    "email": "usuario@ejemplo.com",
    "alias": "juan_p2p",
    "full_name": "Juan Esteban Gómez",
    "role": "USER",
    "created_at": "2026-09-27T21:00:00Z"
  }
  ```

#### `POST /api/v1/auth/login`
* **Descripción**: Autentica credenciales y emite un token JWT.
* **Request Body**:
  ```json
  {
    "email": "usuario@ejemplo.com",
    "password": "PasswordSegura123!"
  }
  ```
* **Response (HTTP 200 OK)**:
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```

---

### 2. Módulo de Administración (`/admin`)

#### `POST /api/v1/admin/topup`
* **Restricción de Seguridad**: Exclusivo para usuarios con `role == ADMIN`.
* **Headers**: `Authorization: Bearer <JWT_ADMIN>`, `X-Idempotency-Key: <UUIDv4>`
* **Request Body**:
  ```json
  {
    "target_user_alias": "juan_p2p",
    "amount": 100000,
    "concept": "Recarga de saldo inicial"
  }
  ```
* **Efecto Contable**: Débito a `SYSTEM_OMNIBUS` -> Crédito a la cuenta de `juan_p2p` por \$100.000 COP.
* **Response (HTTP 200 OK)**:
  ```json
  {
    "reference_id": "TOPUP-20260927-88A1B",
    "target_alias": "juan_p2p",
    "amount_credited": 100000,
    "new_target_balance": 100000,
    "timestamp": "2026-09-27T21:10:00Z"
  }
  ```

---

### 3. Módulo de Transferencias P2P (`/transfers`)

#### `POST /api/v1/transfers/lookup` (Paso 1: Pre-confirmación)
* **Descripción**: Busca un destinatario por su alias exacto y retorna su identificador con el nombre enmascarado (*Name Masking*).
* **Headers**: `Authorization: Bearer <JWT>`
* **Request Body**:
  ```json
  {
    "recipient_alias": "carlos_dev"
  }
  ```
* **Response (HTTP 200 OK)**:
  ```json
  {
    "recipient_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "recipient_alias": "carlos_dev",
    "masked_name": "C***** A****** R*****"
  }
  ```
* **Response (HTTP 404 Not Found)**:
  ```json
  {
    "code": "RECIPIENT_NOT_FOUND",
    "message": "El alias ingresado no corresponde a ningún usuario activo."
  }
  ```

#### `POST /api/v1/transfers/execute` (Paso 2: Ejecución Transaccional)
* **Headers**: `Authorization: Bearer <JWT>`, `X-Idempotency-Key: <UUIDv4>`
* **Request Body**:
  ```json
  {
    "recipient_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "amount": 50000,
    "concept": "Pago de cena"
  }
  ```
* **Response (HTTP 201 Created)**:
  ```json
  {
    "reference_id": "TRF-20260927-99F01",
    "status": "SUCCESS",
    "amount": 50000,
    "sender_alias": "juan_p2p",
    "recipient_alias": "carlos_dev",
    "concept": "Pago de cena",
    "created_at": "2026-09-27T21:15:00Z"
  }
  ```

---

### 4. Módulo de Cobros P2P / Payment Requests (`/charges`)

#### `POST /api/v1/charges` (Crear Cobro)
* **Headers**: `Authorization: Bearer <JWT>`
* **Request Body**:
  ```json
  {
    "payer_alias": "carlos_dev",
    "amount": 25000,
    "concept": "Cine y palomitas"
  }
  ```
* **Response (HTTP 201 Created)**:
  ```json
  {
    "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "requester_alias": "juan_p2p",
    "payer_alias": "carlos_dev",
    "amount": 25000,
    "concept": "Cine y palomitas",
    "status": "PENDING",
    "created_at": "2026-09-27T21:20:00Z"
  }
  ```

#### `POST /api/v1/charges/{id}/pay` (Pagar Cobro Pendiente)
* **Headers**: `Authorization: Bearer <JWT>`, `X-Idempotency-Key: <UUIDv4>`
* **Comportamiento Crítico**:
  * Si el saldo del pagador es **suficiente**: Ejecuta la transacción de transferencia en el Ledger, actualiza el cobro a `COMPLETED` y retorna HTTP 200.
  * Si el saldo del pagador es **insuficiente**: Aborta la transferencia monetaria, genera un Audit Log de fallo, **mantiene el cobro en estado `PENDING`** y retorna HTTP 400.
* **Response Exito (HTTP 200 OK)**:
  ```json
  {
    "charge_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "status": "COMPLETED",
    "transaction_reference": "TRF-20260927-77C02",
    "paid_at": "2026-09-27T21:25:00Z"
  }
  ```
* **Response Error por Saldo Insuficiente (HTTP 400 Bad Request)**:
  ```json
  {
    "code": "INSUFFICIENT_FUNDS_FOR_PAYMENT_REQUEST",
    "message": "Saldo insuficiente para completar este pago. El cobro se mantendrá en estado PENDING.",
    "details": {
      "current_balance": 10000,
      "required_amount": 25000,
      "charge_status": "PENDING"
    },
    "timestamp": "2026-09-27T21:25:00Z"
  }
  ```
