# HabiCapital frontend

Next.js 14 con App Router, React Query y Tailwind. La ruta `/api/v1/*` funciona como proxy hacia FastAPI; el navegador solo habla con Next.js.

## Desarrollo local

Desde la raíz, inicia PostgreSQL y la API: `docker compose up -d db api`. En otra terminal:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Abre http://localhost:3000/register. `BACKEND_URL` solo se lee en el servidor Next.js; apunta a `http://localhost:8000` en desarrollo local. Para ejecutar todo en Docker: `docker compose up --build -d` y abre http://localhost:3001. Compose publica el frontend en el puerto 3001 para evitar conflictos con procesos locales en 3000. Puedes elegir otro puerto, por ejemplo `FRONTEND_PORT=3002 docker compose up -d frontend`.

Los usuarios recién registrados comienzan sin saldo; el administrador puede abonarlo mediante `POST /api/v1/admin/topup`.

Comprobaciones: `npm test`, `npm run typecheck` y `npm run build`. Los movimientos y cobros se consultan con `/api/v1/ledger/movements` y `GET /api/v1/charges?status=PENDING`; ambos requieren JWT. El saldo se actualiza cada 15 segundos.

Desde el dashboard, **Solicitar cobro** envía una solicitud al alias indicado; el pagador la verá en **Cobros pendientes** y podrá pagarla o rechazarla. El historial y los cobros pendientes tienen desplazamiento interno con altura máxima de 26 rem. Cada consulta devuelve como máximo 50 registros recientes; acceder a registros anteriores requiere paginación en la API.
