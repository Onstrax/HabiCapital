"""FastAPI entry point; routers are added as use cases are implemented."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timezone

from app.core.idempotency import IdempotencyMiddleware
from app.modules.audit.adapters.controllers import router as audit_router
from app.modules.identity.adapters.controllers import limiter, router
from app.modules.ledger.adapters.controllers import router as ledger_router
from app.modules.payment_requests.adapters.controllers import router as charges_router

app = FastAPI(title="HabiCapital P2P API")
app.state.limiter = limiter


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(status_code=422, content={
        "code": "VALIDATION_ERROR", "message": "Datos de entrada inválidos",
        "details": {"errors": [
            {"field": list(item["loc"]), "message": item["msg"], "type": item["type"]}
            for item in exc.errors()
        ]},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.exception_handler(RateLimitExceeded)
async def rate_limit_error(request, exc):
    return JSONResponse(status_code=429, content={
        "code": "RATE_LIMIT_EXCEEDED", "message": "Demasiadas solicitudes",
        "details": {}, "timestamp": datetime.now(timezone.utc).isoformat(),
    })


app.add_middleware(IdempotencyMiddleware)
app.include_router(router)
app.include_router(ledger_router)
app.include_router(charges_router)
app.include_router(audit_router)
