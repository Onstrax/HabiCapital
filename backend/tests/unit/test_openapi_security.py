"""Swagger must allow bearer authorization for protected API operations."""

from app.main import app


def test_swagger_declares_bearer_only_for_protected_routes():
    schema = app.openapi()
    bearer = schema["components"]["securitySchemes"]
    assert any(value.get("type") == "http" and value.get("scheme") == "bearer"
               for value in bearer.values())

    for path, method in [
        ("/api/v1/transfers/lookup", "post"),
        ("/api/v1/transfers/execute", "post"),
        ("/api/v1/ledger/balance", "get"),
        ("/api/v1/charges", "post"),
        ("/api/v1/charges", "get"),
        ("/api/v1/admin/topup", "post"),
    ]:
        assert any(name in bearer for requirement in schema["paths"][path][method]["security"]
                   for name in requirement)

    for path in ["/api/v1/auth/login", "/api/v1/auth/register"]:
        assert "security" not in schema["paths"][path]["post"]

    for path in ["/api/v1/transfers/execute", "/api/v1/admin/topup",
                 "/api/v1/charges/{charge_id}/pay"]:
        parameters = schema["paths"][path]["post"]["parameters"]
        assert any(item["name"] == "X-Idempotency-Key" and item["in"] == "header"
                   and item["required"]
                   for item in parameters)
