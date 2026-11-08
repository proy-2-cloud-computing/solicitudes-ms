"""Maquina de estados y reglas de rol para cambiar el estado de una solicitud."""

from .auth import tiene_algun_rol
from .responses import ApiError

TRANSICIONES = {
    "nueva": {"en_aprobacion", "en_proceso", "cancelada"},
    "en_aprobacion": {"en_proceso", "cancelada"},
    "en_proceso": {"completada", "cancelada"},
    "completada": set(),
    "cancelada": set(),
}


def transicion_permitida(estado_actual, estado_nuevo):
    return estado_nuevo in TRANSICIONES.get(estado_actual, set())


def validar_cambio(ctx, estado_actual, estado_nuevo, solicitante_id):
    """Valida transicion y rol. Lanza ApiError 409 o 403."""
    if not transicion_permitida(estado_actual, estado_nuevo):
        raise ApiError(
            409,
            "TRANSICION_INVALIDA",
            f"{estado_actual} -> {estado_nuevo}",
        )

    if _puede_cambiar(ctx, estado_actual, estado_nuevo, solicitante_id):
        return

    raise ApiError(
        403,
        "SIN_PERMISO",
        f"El rol del usuario no permite {estado_actual} -> {estado_nuevo}",
    )


def _puede_cambiar(ctx, estado_actual, estado_nuevo, solicitante_id):
    if estado_nuevo == "cancelada":
        if estado_actual in ("nueva", "en_proceso"):
            if tiene_algun_rol(ctx, ("agente", "admin")):
                return True
            # El solicitante dueno solo puede cancelar mientras siga en "nueva".
            if (
                estado_actual == "nueva"
                and tiene_algun_rol(ctx, ("solicitante",))
                and str(solicitante_id) == ctx["usuario_id"]
            ):
                return True
            return False
        if estado_actual == "en_aprobacion":
            return tiene_algun_rol(ctx, ("aprobador", "admin"))
        return False

    if estado_actual == "nueva":
        # nueva -> en_aprobacion / en_proceso
        return tiene_algun_rol(ctx, ("agente", "admin"))

    if estado_actual == "en_aprobacion" and estado_nuevo == "en_proceso":
        return tiene_algun_rol(ctx, ("aprobador", "admin"))

    if estado_actual == "en_proceso" and estado_nuevo == "completada":
        return tiene_algun_rol(ctx, ("agente", "admin"))

    return False
