# SPEC-03: SECURITY, HARDENING & IDEMPOTENCY SPECIFICATION
**Proyecto**: HabiCapital P2P Transactional Platform  
**Módulo**: Ciberseguridad Bancaria, Hardening OWASP, Middleware de Idempotencia y Enmascaramiento de Datos  
**Versión**: 1.0.0  
**Estado**: APROBADO / ESPECIFICACIÓN TÉCNICA SDD  

---

## 1. AMENAZAS Y MITIGACIONES DE CIBERSEGURIDAD BANCARIA

Como sistema transaccional P2P, HabiCapital implementa mecanismos defensivos en profundidad orientados a **OWASP Financial Services Top 10**:

| Vector de Ataque | Amenaza | Mecanismo de Mitigación Implementado |
| :--- | :--- | :--- |
| **Doble Débito / Reintento de Red** | Reenvío de solicitudes mutativas (`POST /transfers`, `POST /charges`) | Middleware de Idempotencia basado en cabecera `X-Idempotency-Key` y hash de payload SHA-256. |
| **Race Conditions / Sobregiros** | Ejecución simultánea paralela para retirar más dinero del disponible | Bloqueo Pesimista en PostgreSQL (`SELECT ... FOR UPDATE`) ordenado alfabéticamente por UUID. |
| **Enumeración de Usuarios** | Cosecha de aliases/correos mediante búsquedas automatizadas | Coincidencia exacta obligatoria (sin wildcards `LIKE`), Rate Limiting estricto y *Name Masking*. |
| **Ataques de Fuerza Bruta (Auth)** | Vulneración de contraseñas de usuarios por diccionario/GPU | Hashing Argon2id (parámetros m=65536, t=3, p=4) y Rate Limiting de 5 req/min en `/auth/login`. |
| **Inyección SQL / Payload Inflado** | Manipulación de consultas DB o denegación de servicio (DoS) | ORM SQLAlchemy con binding estricto de parámetros y esquemas Pydantic v2 con `extra='forbid'`. |

---

## 2. PATRÓN DE IDEMPOTENCIA BANCARIA (`X-Idempotency-Key`)

El patrón de idempotencia garantiza que si un cliente o red reinterpreta y envía la misma solicitud mutativa múltiples veces, el servidor procesa la operación financiera **una sola vez** y retorna la respuesta original almacenada.

### Flujo del Middleware de Idempotencia

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.modules.ledger.infrastructure.models import IdempotencyRecordModel, IdempotencyStatus

MUTATIVE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Solo aplica a rutas mutativas que contengan la cabecera
        if request.method not in MUTATIVE_METHODS:
            return await call_next(request)

        idempotency_key_header = request.headers.get("X-Idempotency-Key")
        if not idempotency_key_header:
            # Si el endpoint requiere idempotencia obligatoria, se valida en las dependencias
            return await call_next(request)

        try:
            key_uuid = uuid.UUID(idempotency_key_header)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="La cabecera X-Idempotency-Key debe ser un UUIDv4 válido."
            )

        # Leer body sin consumirlo permanentemente
        body_bytes = await request.body()
        user_id = getattr(request.state, "user_id", None)  # Inyectado previamente por AuthMiddleware

        if not user_id:
            # Si no está autenticado, pasa a auth middleware
            return await call_next(request)

        # Calcular SHA-256 del path + method + payload
        payload_raw = f"{request.method}:{request.url.path}:{body_bytes.decode('utf-8', errors='ignore')}"
        request_hash = hashlib.sha256(payload_raw.encode('utf-8')).hexdigest()

        async with AsyncSessionLocal() as session:
            stmt = select(IdempotencyRecordModel).where(IdempotencyRecordModel.key == key_uuid)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()

            if record:
                # Validar reuso malicioso de la misma llave con distinto payload
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
                    # Retornar respuesta en caché
                    return Response(
                        content=record.response_body,
                        status_code=record.response_code,
                        media_type="application/json",
                        headers={"X-Cache": "HIT-IDEMPOTENCY"}
                    )

            # Insertar registro inicial en PROCESSING
            new_record = IdempotencyRecordModel(
                key=key_uuid,
                user_id=user_id,
                request_hash=request_hash,
                status=IdempotencyStatus.PROCESSING
            )
            session.add(new_record)
            await session.commit()

        # Ejecutar la solicitud real
        response = await call_next(request)

        # Si fue exitoso (2xx), almacenar respuesta
        if 200 <= response.status_code < 300:
            response_body = [section async for section in response.body_iterator]
            response.body_iterator = iterate_in_threadpool(iter(response_body))
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

## 3. HASHING DE CONTRASEÑAS CON ARGON2ID & JWT RS256

### A. Configuración de Hashing con Argon2id
Se prohíbe el uso de MD5, SHA256 crudo o Bcrypt sin sal. Se utiliza **Argon2id** (ganador del Password Hashing Competition) por su alta resistencia contra ataques por fuerza bruta acelerados por GPU/ASIC.

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

### B. Emisión y Validación de Tokens JWT (RS256 / HS256)
* **Algoritmo**: `HS256` (con clave secreta de 256 bits generada aleatoriamente) o `RS256` (par de claves RSA de 4096 bits).
* **Tiempo de Expiración**: Access Token de 15 minutos.
* **Claims Obligatorios**: `sub` (User ID UUID), `email`, `role`, `alias`, `exp`, `iat`, `nbf`.

---

## 4. ENMASCARAMIENTO DE NOMBRE (*NAME MASKING*) & SANITIZACIÓN ALIAS

Para cumplir con las decisiones de diseño sobre privacidad del destinatario, se implementa una función pura de enmascaramiento que oculta los nombres personales conservando únicamente la primera letra de cada término.

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
            # Palabras cortas (de, la, del) se muestran como inicial + *
            masked_words.append(word[0] + "*")
        else:
            masked_words.append(word[0] + "*" * (len(word) - 1))

    return " ".join(masked_words)

def sanitize_alias(alias: str) -> str:
    """
    Normaliza y sanitiza el alias ingresado.
    - Convierte a minúsculas.
    - Elimina espacios al inicio y final.
    """
    cleaned = alias.strip().lower()
    if not re.match(r"^[a-z0-9_]{3,20}$", cleaned):
        raise ValueError("El alias solo puede contener letras minúsculas, números y guiones bajos (3-20 caracteres).")
    return cleaned
```

---

## 5. RATE LIMITING FINANCIERO (SLOWAPI)

Para mitigar ataques de denegación de servicio (DoS) y prevenir raspado (*scraping*) o enumeración de alias, se establece la siguiente matriz de límites de velocidad:

| Endpoint Target | Límite Permitido | Clave de Control | Acción al Exceder |
| :--- | :--- | :--- | :--- |
| `POST /api/v1/auth/login` | **5 req / minuto** | IP remota | HTTP 429 Too Many Requests |
| `POST /api/v1/transfers/lookup` | **10 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |
| `POST /api/v1/transfers/execute` | **10 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |
| `POST /api/v1/charges/*` | **15 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |
| Endpoints de Lectura General | **60 req / minuto** | Token JWT + IP | HTTP 429 Too Many Requests |

---

## 6. SANITIZACIÓN Y VALIDACIÓN PYDANTIC V2

Todos los Esquemas DTO de la API se configuran con **Pydantic v2 estricto** para rechazar atributos desconocidos y prevenir inyecciones de payloads o ataques de desempaquetado de memoria:

```python
# app/shared/schemas.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
import re

class StrictBaseSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",            # Prohíbe campos no definidos en el JSON
        str_strip_whitespace=True, # Limpia espacios en blanco
        strict=True                # Exige coincidencia exacta de tipos
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
