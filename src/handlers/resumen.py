"""GET /solicitudes/resumen: contadores por estado para el dashboard."""

from src.common import db
from src.common.auth import contexto
from src.common.responses import api_handler, ok


@api_handler
def handler(event, context):
    ctx = contexto(event)
    total, conteos = db.contar_por_estado(ctx["tenant_id"])

    return ok(
        {
            "tenant_id": ctx["tenant_id"],
            "total": total,
            "por_estado": conteos,
        }
    )
