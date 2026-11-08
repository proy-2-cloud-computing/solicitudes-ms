"""Cliente del Catalogo de Servicios.

Contrato: GET {CATALOGO_URL}/catalogo/{servicio_id} con el mismo
Authorization del usuario. El Catalogo obtiene el tenant del token.
"""

import json
import os
import socket
import urllib.error
import urllib.request
from urllib.parse import quote

from .responses import ApiError

TIMEOUT_POR_DEFECTO = 5.0


def obtener_servicio(servicio_id, authorization, tenant_id):
    base = (os.environ.get("CATALOGO_URL") or "").rstrip("/")
    if not base:
        raise ApiError(
            503,
            "CATALOGO_NO_DISPONIBLE",
            "El Catalogo no esta configurado",
        )

    url = f"{base}/catalogo/{quote(servicio_id, safe='')}"
    timeout = _timeout()

    ultimo_error = None
    for intento in range(2):
        try:
            solicitud = urllib.request.Request(
                url,
                headers={
                    "Authorization": authorization or "",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(solicitud, timeout=timeout) as respuesta:
                crudo = respuesta.read().decode("utf-8", "replace")
            try:
                datos = json.loads(crudo)
            except json.JSONDecodeError as error:
                raise ApiError(
                    502,
                    "CATALOGO_INVALIDO",
                    "El Catalogo respondio con JSON invalido",
                ) from error
            return _normalizar(datos, tenant_id, servicio_id)

        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise ApiError(
                    400,
                    "SERVICIO_INVALIDO",
                    "El servicio no existe en el Catalogo",
                ) from error
            if error.code in (401, 403):
                raise ApiError(
                    502,
                    "CATALOGO_NO_AUTORIZADO",
                    "El Catalogo rechazo el token del usuario",
                ) from error
            if error.code >= 500 or error.code in (408, 429):
                ultimo_error = error
                if intento == 0:
                    continue
                break
            raise ApiError(
                400,
                "SERVICIO_INVALIDO",
                "El Catalogo rechazo la consulta del servicio",
            ) from error

        except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
            ultimo_error = error
            if intento == 0:
                continue
            break

    raise ApiError(
        503,
        "CATALOGO_NO_DISPONIBLE",
        "El Catalogo no esta disponible; intenta de nuevo",
        detalle=str(ultimo_error) if ultimo_error else None,
    )


def _timeout():
    try:
        return float(os.environ.get("CATALOGO_TIMEOUT", TIMEOUT_POR_DEFECTO))
    except (TypeError, ValueError):
        return TIMEOUT_POR_DEFECTO


def _normalizar(datos, tenant_id, servicio_id):
    if not isinstance(datos, dict):
        raise ApiError(
            502, "CATALOGO_INVALIDO", "El Catalogo devolvio un formato invalido"
        )

    if datos.get("activo") is False:
        raise ApiError(
            400, "SERVICIO_INVALIDO", "El servicio esta inactivo en el Catalogo"
        )

    tenant_catalogo = datos.get("tenant_id")
    if tenant_catalogo and str(tenant_catalogo) != str(tenant_id):
        # No revelamos que el servicio existe en otro tenant.
        raise ApiError(
            400, "SERVICIO_INVALIDO", "El servicio no existe en el Catalogo"
        )

    nombre = datos.get("nombre") or datos.get("nombre_servicio")
    if not isinstance(nombre, str) or not nombre.strip():
        raise ApiError(
            502, "CATALOGO_INVALIDO", "El Catalogo no devolvio 'nombre'"
        )

    try:
        sla_horas = int(datos.get("sla_horas"))
    except (TypeError, ValueError) as error:
        raise ApiError(
            502, "CATALOGO_INVALIDO", "El Catalogo no devolvio 'sla_horas' valido"
        ) from error
    if sla_horas <= 0:
        raise ApiError(
            502, "CATALOGO_INVALIDO", "'sla_horas' debe ser mayor que cero"
        )

    requiere = datos.get("requiere_aprobacion", False)
    if not isinstance(requiere, bool):
        raise ApiError(
            502,
            "CATALOGO_INVALIDO",
            "'requiere_aprobacion' debe ser booleano",
        )

    return {
        "servicio_id": datos.get("servicio_id") or servicio_id,
        "nombre": nombre.strip(),
        "sla_horas": sla_horas,
        "requiere_aprobacion": requiere,
    }
