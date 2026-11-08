"""GET /solicitudes/{id}/historial: auditoria de cambios de estado."""

from src.common import db
from src.common.auth import contexto
from src.common.responses import ApiError, api_handler, ok
from src.common.validation import normalizar_solicitud_id, validar_limit


@api_handler
def handler(event, context):
    ctx = contexto(event)
    solicitud_id = normalizar_solicitud_id(
        (event.get("pathParameters") or {}).get("id")
    )

    if not db.obtener_solicitud(ctx["tenant_id"], solicitud_id):
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")

    parametros = event.get("queryStringParameters") or {}
    limit = validar_limit(parametros.get("limit"), por_defecto=100, maximo=100)

    items, siguiente = db.obtener_historial(
        ctx["tenant_id"],
        solicitud_id,
        limit=limit,
        next_token=parametros.get("next"),
    )

    return ok(
        {
            "solicitud_id": solicitud_id,
            "items": [db.serializar_historial(item) for item in items],
            "next": siguiente,
        }
    )
