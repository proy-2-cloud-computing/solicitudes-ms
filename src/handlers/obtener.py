"""GET /solicitudes/{id}: detalle de una solicitud."""

from src.common import db
from src.common.auth import contexto
from src.common.responses import ApiError, api_handler, ok
from src.common.validation import normalizar_solicitud_id


@api_handler
def handler(event, context):
    ctx = contexto(event)
    parametros = event.get("pathParameters") or {}
    solicitud_id = normalizar_solicitud_id(parametros.get("id"))

    item = db.obtener_solicitud(ctx["tenant_id"], solicitud_id)
    if not item:
        # Mismo 404 si no existe o si pertenece a otro tenant.
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")

    return ok(db.serializar_solicitud(item))
