"""Extraccion de identidad y autorizacion a partir del token de Cognito."""

from .responses import ApiError

ROLES = {"solicitante", "agente", "aprobador", "admin"}


def obtener_authorization(event):
    """Devuelve el header Authorization sin importar mayusculas/minusculas."""
    headers = event.get("headers") or {}
    for nombre, valor in headers.items():
        if nombre.lower() == "authorization":
            return valor
    return ""


def contexto(event):
    """Extrae tenant, usuario y grupos de los claims del authorizer."""
    request_context = event.get("requestContext") or {}
    authorizer = request_context.get("authorizer") or {}
    claims = authorizer.get("claims") or {}

    tenant_id = claims.get("custom:tenant_id") or claims.get("tenant_id")
    usuario_id = claims.get("sub")

    if not tenant_id or not usuario_id:
        raise ApiError(
            401,
            "NO_AUTORIZADO",
            "Token invalido o sin tenant_id",
        )

    return {
        "tenant_id": str(tenant_id),
        "usuario_id": str(usuario_id),
        "grupos": _normalizar_grupos(claims.get("cognito:groups")),
        "claims": claims,
    }


def _normalizar_grupos(valor):
    """API Gateway puede entregar cognito:groups como lista o string.

    Formatos vistos: ["agente"], "agente", "agente,admin" y "[agente, admin]".
    """
    if not valor:
        return set()
    if isinstance(valor, str):
        limpio = valor.strip()
        if limpio.startswith("[") and limpio.endswith("]"):
            limpio = limpio[1:-1]
        return {
            parte.strip().strip('"').strip("'")
            for parte in limpio.split(",")
            if parte.strip()
        }
    return {str(grupo) for grupo in valor}


def tiene_algun_rol(ctx, roles):
    return bool(ctx["grupos"] & set(roles))


def requiere_roles(ctx, roles, mensaje="El rol del usuario no permite esta accion"):
    if not tiene_algun_rol(ctx, roles):
        raise ApiError(403, "SIN_PERMISO", mensaje)


def es_agente_o_admin(ctx):
    return tiene_algun_rol(ctx, ("agente", "admin"))


def es_admin(ctx):
    return "admin" in ctx["grupos"]
