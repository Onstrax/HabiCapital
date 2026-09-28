# SPEC-03: SECURITY, HARDENING & IDEMPOTENCY SPECIFICATION (v2)
**Proyecto**: HabiCapital P2P Transactional Platform  
**Módulo**: Ciberseguridad Bancaria, Post-Quantum Readiness, Privacidad de Datos (Data Minimization & FLE), Middleware de Idempotencia y Enmascaramiento  
**Versión**: 2.1.0  
**Estado**: APROBADO / ESPECIFICACIÓN TÉCNICA SDD  

---

## 1. AMENAZAS Y MITIGACIONES DE CIBERSEGURIDAD BANCARIA

Como sistema transaccional P2P crítico, HabiCapital implementa mecanismos defensivos en profundidad orientados a **OWASP Financial Services Top 10** y resistencia ante atacantes clásicos y cuánticos:

| Vector de Ataque | Amenaza | Mecanismo de Mitigación Implementado |
| :--- | :--- | :--- |
| **Doble Débito / Reintento de Red** | Reenvío de solicitudes mutativas (`POST /transfers`, `POST /charges`) | Middleware de Idempotencia basado en cabecera `X-Idempotency-Key` y hash de payload SHA-256. |
| **Race Conditions / Sobregiros** | Ejecución simultánea paralela para retirar más dinero del disponible | Bloqueo Pesimista en PostgreSQL (`SELECT ... FOR UPDATE`) ordenado alfabéticamente por UUID. |
| **Enumeración de Usuarios** | Cosecha de aliases/correos mediante búsquedas automatizadas | Coincidencia exacta obligatoria (sin wildcards `LIKE`), Rate Limiting estricto y *Name Masking*. |
| **Ataques de Fuerza Bruta (Auth)** | Vulneración de contraseñas de usuarios por diccionario/GPU | Hashing Argon2id (parámetros m=65536, t=3, p=4) y Rate Limiting de 5 req/min en `/auth/login`. |
| **Amenaza Criptográfica Cuántica** | Vulneración de RSA/ECC por el Algoritmo de Shor en ordenadores cuánticos | Sustitución de RSA por **HMAC-SHA256 / Ed25519 + Preparación PQC (ML-DSA FIPS 204)** y **AES-256-GCM** para cifrado simétrico en reposo (resistente al Algoritmo de Grover). |
| **Filtración de Base de Datos (DB Leak / Data Breach)** | Exposición de PII, correos, nombres y conceptos de pago en un volcado SQL | **Field-Level Encryption (FLE)** con AES-256-GCM, **Blind Indexing (HMAC-SHA256)** y desasociación en el Ledger. |
| **Inyección SQL / Payload Inflado** | Manipulación de consultas DB o denegación de servicio (DoS) | ORM SQLAlchemy con binding estricto de parámetros y esquemas Pydantic v2 con `extra='forbid'`. |

---

## 2. ARQUITECTURA CRIPTOGRÁFICA QUANTUM-SAFE (POST-QUANTUM READINESS)

### A. Evaluación del Impacto Cuántico (Algoritmos de Shor y Grover)

1. **Impacto del Algoritmo de Shor (Criptografía Asimétrica Clásica)**:
   * **Vulnerabilidad**: Shor descompone factores primos y logaritmos discretos en tiempo polinómico, haciendo invulnerables RSA (RSA-2048/4096) y curvas elípticas clásicas (ECDSA/Secp256k1).
   * **Mitigación HabiCapital**: Eliminación total de RSA para la emisión de JWTs. Se migra a **HMAC-SHA256 (Llaves simétricas de 256 bits)** o esquema híbrido Post-Quantum Signature (**ML-DSA / Dilithium - NIST FIPS 204**).

2. **Impacto del Algoritmo de Grover (Criptografía Simétrica y Hashes)**:
   * **Vulnerabilidad**: Grover reduce la seguridad efectiva a la mitad de los bits de la llave ($\sqrt{N}$).
   * **Mitigación HabiCapital**:
     * **AES-256-GCM**: Con una llave de 256 bits, la resistencia poscuántica efectiva es de **128 bits**, lo cual permanece matemáticamente inquebrantable por la física computacional actual y futura.
     * **SHA-256 / SHA-512**: Ofrecen 128 a 256 bits de resistencia poscuántica contra colisiones.

### B. Matriz Criptográfica de HabiCapital

```text
+-----------------------------------------------------------------------------------+
|                        MATRIZ DE PROTECCIÓN CRIPTOGRÁFICA                         |
+---------------------+-------------------------------+-----------------------------+
| Dominio             | Algoritmo Clásico             | Estándar Post-Quantum (PQC) |
+---------------------+-------------------------------+-----------------------------+
| Auth Tokens (JWT)   | HMAC-SHA256 / Ed25519         | Hybrid / ML-DSA (FIPS 204)  |
| Password Hashing    | Argon2id (Memory Hardening)   | Argon2id (Quantum-Resistant)|
| Data-at-Rest        | AES-256-GCM                   | AES-256-GCM (128-bit Post)  |
| Data-in-Transit     | TLS 1.3                       | TLS 1.3 + ML-KEM (Kyber768) |
+---------------------+-------------------------------+-----------------------------+
```

---

## 3. PRIVACIDAD DE DATOS, MINIMIZACIÓN Y ZERO-LEAKAGE ARCHITECTURE

### A. Cifrado a Nivel de Campo (*Field-Level Encryption - FLE*)
Para garantizar que un volcado no autorizado de la base de datos (Data Breach / SQL Leak) no exponga información personal ni datos bancarios utilizables:

1. **Campos Sensibles Cifrados en Reposo**:
   * `users.full_name` $\rightarrow$ Cifrado con **AES-256-GCM** en la capa de aplicación antes de persistir.
   * `users.email` $\rightarrow$ Cifrado con **AES-256-GCM**.
   * `payment_requests.concept` $\rightarrow$ Cifrado con **AES-256-GCM** (los contextos sociales como "consulta médica" o "arriendo" quedan completamente inaccesibles).
2. **Desasociación en el Libro Mayor (Ledger Pseudonymization)**:
   * La tabla `ledger_entries` solo relaciona `debit_account_id` y `credit_account_id` mediante UUIDs aleatorios.
   * En caso de hackeo a la DB, el atacante solo observa un **grafo abstracto de transferencias entre UUIDs**. Sin la clave maestra de descifrado FLE (almacenada fuera de la base de datos en variables de entorno del backend), es computacionalmente imposible asociar esas operaciones a identidades del mundo real.

### B. Patrón de Búsqueda Ciega (*Blind Indexing*)
Pado que `users.email` se almacena cifrado con AES-256-GCM (lo cual produce un ciphertext distinto por cada inicialización debido al IV/Nonce aleatorio), no es posible ejecutar un `SELECT * FROM users WHERE email = :val` tradicional.

* **Mecanismo de Blind Indexing**:
  * Se añade la columna `users.email_blind_index = HMAC-SHA256(email, PEPPER_SECRET)`.
  * La consulta de coincidencia exacta computa el `HMAC-SHA256` en memoria en el backend y busca directamente el hash en el índice sin desencriptar la base de datos ni almacenar correos en texto plano.

### C. Soberanía del Usuario & Crypto-Shredding (Habeas Data / GDPR)
La regulación financiera exige conservar inmutable el Libro Mayor (`ledger_entries`) para auditorías contables. Para conciliar esto con el **Derecho al Olvido / Soberanía del Usuario**:

* **Algoritmo de Crypto-Shredding**:
  Si un usuario ejerce su derecho de supresión de datos, la aplicación no elimina los asientos contables de partida doble (lo que rompería el balance del sistema), sino que **elimina la clave de cifrado individual del usuario / sobrescribe sus campos PII cifrados con entropía aleatoria**.
  * **Resultado**: El historial transaccional permanece matemáticamente equilibrado en el Ledger, pero queda **irreversiblemente anónimo**, haciendo imposible asociar las transacciones pasadas a una persona física.

---

## 4. PATRÓN DE IDEMPOTENCIA BANCARIA (`X-Idempotency-Key`)

El patrón de idempotencia garantiza que si un cliente o red reinterpreta y envía la misma solicitud mutativa múltiples veces, el servidor procesa la operación financiera **una sola vez** y retorna la respuesta original almacenada.

```text
[Cliente] ---> Request con Header `X-Idempotency-Key: <UUIDv4>`
                     |
                     v
     [IdempotencyMiddleware (FastAPI)]
                     |
        1. Validar formato UUIDv4
        2. Calcular hash SHA-256(Method + Path + Body)
                     |
        +------------+------------+
        |                         |
  [Llave Existe]           [Llave No Existe]
        |                         |
+-------+-------+          Insertar registro en DB
| Status check  |          con Status = `PROCESSING`
+-------+-------+                 |
        |                  Procesar Use Case / Transacción
  +-----+-----+                   |
  |           |            +------+------+
[COMPLETED] [PROCESSING]   |             |
  |           |        [Exito]        [Fallo]
  |      HTTP 409      |                 |
  |      Conflict      Actualizar DB:    Actualizar DB:
  |                    Status=COMPLETED  Status=FAILED
Retornar               Save Response     Rollback
Response               Body & Code
Original               |
  |                    Retornar HTTP 200/201
  v
[Cliente]
```

### Código Especificación del Middleware de Idempotencia

```python
# app/core/idempotency.py
import hashlib
import json
import uuid
from typing import Callable, Awaitable
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.ledger.infrastructure.models import IdempotencyRecordModel, IdempotencyStatus

MUTATIVE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.method not in MUTATIVE_METHODS:
            return await call_next(request)

        idempotency_key_header = request.headers.get("X-Idempotency-Key")
        if not idempotency_key_header:
            return await call_next(request)

        try:
            key_uuid = uuid.UUID(idempotency_key_header)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La cabecera X-Idempotency-Key debe ser un UUIDv4 válido."
            )

        body_bytes = await request.body()
        user_id = getattr(request.state, "user_id", None)

        if not user_id:
            return await call_next(request)

        payload_raw = f"{request.method}:{request.url.path}:{body_bytes.decode('utf-8', errors='ignore')}"
        request_hash = hashlib.sha256(payload_raw.encode('utf-8')).hexdigest()

        async with AsyncSessionLocal() as session:
            stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.key == key_uuid)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                if record.request_hash != request_hash:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Reuso de X-Idempotency-Key detectado con un payload diferente."
                    )

                if record.status == IdempotencyStatus.PROCESSING:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Una solicitud idéntica con esta X-Idempotency-Key está en proceso actualmente."
                    )

                if record.status == IdempotencyStatus.COMPLETED:
                    return Response(
                        content=json.dumps(record.response_body),
                        status_code=record.response_code,
                        media_type="application/json",
                        headers={"X-Cache": "HIT-IDEMPOTENCY"}
                    )

            new_record = IdempotencyRecordModel(
                key=key_uuid,
                user_id=user_id,
                request_hash=request_hash,
                status=IdempotencyStatus.PROCESSING
            )
            session.add(new_record)
            await session.commit()

        response = await call_next(request)

        if 200 <= response.status_code < 300:
            response_body = [section async for section in response.body_iterator]
            body_str = b"".join(response_body).decode("utf-8")

            async with AsyncSessionLocal() as session:
                stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.key == key_uuid)
                rec = (await session.execute(stmt)).scalar_one()
                rec.status = IdempotencyStatus.COMPLETED
                rec.response_code = response.status_code
                rec.response_body = json.loads(body_str) if body_str else {}
                await session.commit()

        return response
```

---

## 5. HASHING DE CONTRASEÑAS Y TOKENS JWT QUANTUM-SAFE

### A. Hashing con Argon2id
Se utiliza **Argon2id** con configuración endurecida contra ataques por fuerza bruta en GPU/ASIC y computación cuántica.

```python
# app/core/security.py
from passlib.context import CryptContext

pw_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__memory_cost=65536,  # 64 MB RAM
    argon2__time_cost=3,        # 3 iteraciones
    argon2__parallelism=4       # 4 hilos
)

def hash_password(password: str) -> str:
    return pw_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pw_context.verify(plain_password, hashed_password)
```

### B. Emisión y Validación de Tokens JWT (HMAC-SHA256 / Post-Quantum Ready)
* **Algoritmo**: `HS256` con llave simétrica de 256 bits generada aleatoriamente mediante entropía criptográfica (`secrets.token_bytes(32)`). Ofrece 128 bits de seguridad efectiva contra el algoritmo de Grover.
* **Expiración**: Access Token de 15 minutos.
* **Claims Obligatorios**: `sub` (User ID UUID), `email`, `role`, `alias`, `exp`, `iat`, `nbf`.

---

## 6. ENMASCARAMIENTO DE NOMBRE (*NAME MASKING*) & SANITIZACIÓN ALIAS

```python
# app/shared/utils/security_utils.py
import re

def mask_full_name(full_name: str) -> str:
    """
    Transforma un nombre completo enmascarando los caracteres con asteriscos.
    Ejemplo: 'Juan Esteban Gómez Ávalos' -> 'J*** E******* G**** Á****'
    """
    if not full_name or not full_name.strip():
        return ""

    words = full_name.strip().split()
    masked_words = []

    for word in words:
        if len(word) <= 2:
            masked_words.append(word[0] + "*")
        else:
            masked_words.append(word[0] + "*" * (len(word) - 1))

    return " ".join(masked_words)

def sanitize_alias(alias: str) -> str:
    cleaned = alias.strip().lower()
    if not re.match(r"^[a-z0-9_]{3,20}$", cleaned):
        raise ValueError("El alias solo puede contener letras minúsculas, números y guiones bajos (3-20 caracteres).")
    return cleaned
```

---

## 7. RATE LIMITING FINANCIERO (SLOWAPI)

| Endpoint Target | Límite Permitido | Clave de Control | Acción al Exceder |
| :--- | :--- | :--- | :--- |
| `POST /api/v1/auth/login` | **5 req / minuto** | IP remota | HTTP 429 Too Many Requests |
| `POST /api/v1/transfers/lookup` | **10 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |
| `POST /api/v1/transfers/execute` | **10 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |
| `POST /api/v1/charges/*` | **15 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |
| Endpoints de Lectura General | **60 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |

---

## 8. SANITIZACIÓN Y VALIDACIÓN PYDANTIC V2

```python
# app/shared/schemas.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re

class StrictBaseSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        strict=True
    )

class TransferLookupRequest(StrictBaseSchema):
    recipient_alias: str = Field(..., min_length=3, max_length=20, description="Alias exacto del destinatario")

    @field_validator("recipient_alias")
    @classmethod
    def validate_alias_format(cls, v: str) -> str:
        cleaned = v.lower().strip()
        if not re.match(r"^[a-z0-9_]{3,20}$", cleaned):
            raise ValueError("Formato de alias inválido.")
        return cleaned
```
