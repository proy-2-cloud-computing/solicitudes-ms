"""PUT /solicitudes/{id}/estado: cambiar estado y asignar responsable."""

from src.common import db, events, transitions
from src.common.auth import contexto
from src.common.responses import ApiError, api_handler, ok
from src.common.validation import (
    leer_cuerpo,
    normalizar_solicitud_id,
    validar_cambio_estado,
)


@api_handler
def handler(event, context):
    ctx = contexto(event)
    parametros = event.get("pathParameters") or {}
    solicitud_id = normalizar_solicitud_id(parametros.get("id"))
    datos = validar_cambio_estado(leer_cuerpo(event))

    item = db.obtener_solicitud(ctx["tenant_id"], solicitud_id)
    if not item:
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")

    transitions.validar_cambio(
        ctx,
        item["estado"],
        datos["estado"],
        item.get("solicitante_id"),
    )

    db.cambiar_estado(item, datos, ctx["usuario_id"])

    actualizado = db.obtener_solicitud(ctx["tenant_id"], solicitud_id)
    if not actualizado:
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")

    if datos["estado"] == "completada":
        events.publicar_evento(
            "solicitud-completada",
            ctx["tenant_id"],
            solicitud_id,
            datos["estado"],
            ctx["usuario_id"],
            datos={
                "asignado_a": actualizado.get("asignado_a"),
                "sla_vence_en": actualizado.get("sla_vence_en"),
            },
        )

    return ok(db.serializar_solicitud(actualizado))
