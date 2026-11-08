"""GET /solicitudes: listar y paginar solicitudes del tenant."""

from src.common import db
from src.common.auth import contexto
from src.common.responses import api_handler, ok
from src.common.validation import validar_estado_filtro, validar_limit


@api_handler
def handler(event, context):
    ctx = contexto(event)
    parametros = event.get("queryStringParameters") or {}

    estado = validar_estado_filtro(parametros.get("estado"))
    limit = validar_limit(parametros.get("limit"))

    items, siguiente = db.listar_solicitudes(
        ctx["tenant_id"],
        estado=estado,
        limit=limit,
        next_token=parametros.get("next"),
    )

    return ok(
        {
            "items": [db.serializar_solicitud(item) for item in items],
            "next": siguiente,
        }
    )
