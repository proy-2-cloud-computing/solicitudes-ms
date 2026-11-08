"""POST /solicitudes/{id}/adjuntos y PUT .../adjuntos (confirmacion).

POST firma una URL para que el navegador suba directo a S3.
PUT confirma que el objeto existe y recien entonces lo guarda en `adjuntos`.
"""

import uuid

from src.common import db, storage
from src.common.auth import (
    contexto,
    es_agente_o_admin,
    tiene_algun_rol,
)
from src.common.responses import ApiError, api_handler, ok
from src.common.validation import (
    expiracion_adjuntos,
    leer_cuerpo,
    max_adjunto_bytes,
    normalizar_solicitud_id,
    prefijo_adjuntos,
    validar_adjunto,
    validar_confirmacion_adjunto,
)


@api_handler
def handler(event, context):
    metodo = str(event.get("httpMethod", "")).upper()
    if metodo == "POST":
        return _firmar(event, context)
    if metodo == "PUT":
        return _confirmar(event, context)
    raise ApiError(405, "METODO_NO_PERMITIDO", "Metodo no permitido")


def _firmar(event, context):
    ctx = contexto(event)
    solicitud_id = normalizar_solicitud_id(
        (event.get("pathParameters") or {}).get("id")
    )
    item = _obtener_y_autorizar(ctx, solicitud_id)

    datos = validar_adjunto(leer_cuerpo(event))
    prefijo = prefijo_adjuntos(ctx["tenant_id"], solicitud_id)
    key = f"{prefijo}{uuid.uuid4().hex}-{datos['nombre_archivo']}"
    expiracion = expiracion_adjuntos()

    url = storage.generar_url_prefirmada(
        key, datos["content_type"], expiracion
    )

    return ok(
        {
            "upload_url": url,
            "key": key,
            "expires_in": expiracion,
            "metodo": "PUT",
            "content_type": datos["content_type"],
            "max_bytes": max_adjunto_bytes(),
            "solicitud_id": item["sk"],
        }
    )


def _confirmar(event, context):
    ctx = contexto(event)
    solicitud_id = normalizar_solicitud_id(
        (event.get("pathParameters") or {}).get("id")
    )
    _obtener_y_autorizar(ctx, solicitud_id)

    datos = validar_confirmacion_adjunto(leer_cuerpo(event))
    key = datos["key"]
    prefijo = prefijo_adjuntos(ctx["tenant_id"], solicitud_id)

    if not key.startswith(prefijo) or ".." in key:
        raise ApiError(
            400,
            "VALIDACION",
            "La key del adjunto no pertenece a esta solicitud",
        )

    if not storage.existe_objeto(key):
        raise ApiError(
            400,
            "ADJUNTO_NO_ENCONTRADO",
            "El archivo no se subio a S3; sube primero con la URL prefirmada",
        )

    actualizado = db.agregar_adjunto(ctx["tenant_id"], solicitud_id, key)
    if not actualizado:
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")

    return ok(db.serializar_solicitud(actualizado))


def _obtener_y_autorizar(ctx, solicitud_id):
    item = db.obtener_solicitud(ctx["tenant_id"], solicitud_id)
    if not item:
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")

    if es_agente_o_admin(ctx):
        return item

    es_dueno = str(item.get("solicitante_id")) == ctx["usuario_id"]
    if es_dueno and tiene_algun_rol(ctx, ("solicitante",)):
        return item

    raise ApiError(
        403, "SIN_PERMISO", "Solo el solicitante dueno o un agente puede adjuntar"
    )
