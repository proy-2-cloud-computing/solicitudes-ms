"""POST /solicitudes: crear una solicitud de servicio."""

from src.common import catalog, db, events
from src.common.auth import (
    contexto,
    obtener_authorization,
    requiere_roles,
)
from src.common.responses import api_handler, creado
from src.common.timeutils import ahora_utc, sumar_horas
from src.common.validation import leer_cuerpo, validar_creacion

ROLES_CREAR = {"solicitante", "agente", "aprobador", "admin"}


@api_handler
def handler(event, context):
    ctx = contexto(event)
    requiere_roles(ctx, ROLES_CREAR)

    datos = validar_creacion(leer_cuerpo(event))

    servicio = catalog.obtener_servicio(
        datos["servicio_id"],
        obtener_authorization(event),
        ctx["tenant_id"],
    )

    # El Catalogo acepta variantes (SVC-000003, svc#3) y devuelve el ID
    # canonico (SVC#000003): se guarda ese para que la referencia coincida.
    servicio_id = servicio.get("servicio_id") or datos["servicio_id"]

    creado_en = ahora_utc()
    estado = "en_aprobacion" if servicio["requiere_aprobacion"] else "nueva"
    solicitud_id = f"REQ#{db.nuevo_id_solicitud(ctx['tenant_id']):06d}"

    item = {
        "tenant_id": ctx["tenant_id"],
        "sk": solicitud_id,
        "servicio_id": servicio_id,
        "titulo": datos["titulo"],
        "descripcion": datos["descripcion"],
        "solicitante_id": ctx["usuario_id"],
        "estado": estado,
        "prioridad": datos["prioridad"],
        "requiere_aprobacion": servicio["requiere_aprobacion"],
        "nombre_servicio": servicio["nombre"],
        "sla_horas": servicio["sla_horas"],
        "sla_vence_en": sumar_horas(creado_en, servicio["sla_horas"]),
        "adjuntos": [],
        "creado_en": creado_en,
        "actualizado_en": creado_en,
        "estado_fecha": f"{estado}#{creado_en}",
    }

    evento_id = _evento_id()
    historial = {
        "tenant_id": ctx["tenant_id"],
        "sk": f"HIST#{solicitud_id}#{creado_en}#{evento_id}",
        "solicitud_id": solicitud_id,
        "estado_anterior": "",
        "estado_nuevo": estado,
        "actor_id": ctx["usuario_id"],
        "comentario": "Solicitud creada",
        "evento_id": evento_id,
        "fecha": creado_en,
    }

    db.crear_solicitud(item, historial)

    events.publicar_evento(
        "solicitud-creada",
        ctx["tenant_id"],
        solicitud_id,
        estado,
        ctx["usuario_id"],
        datos={
            "servicio_id": servicio_id,
            "nombre_servicio": servicio["nombre"],
            "sla_vence_en": item["sla_vence_en"],
            "prioridad": datos["prioridad"],
        },
    )

    return creado(db.serializar_solicitud(item))


def _evento_id():
    import uuid

    return uuid.uuid4().hex[:8]
