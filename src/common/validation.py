"""Validacion de entradas y normalizacion de identificadores."""

import base64
import json
import os
import re
from urllib.parse import unquote

from .responses import ApiError

ESTADOS = (
    "nueva",
    "en_aprobacion",
    "en_proceso",
    "completada",
    "cancelada",
)
PRIORIDADES = ("bajo", "medio", "alto", "critico")

TIPOS_ADJUNTO = {
    "application/pdf",
    "application/zip",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
}

_ID_SOLICITUD = re.compile(r"^REQ#(\d{1,12})$")
_CARACTERES_SEGUROS = re.compile(r"[^A-Za-z0-9._-]+")


def leer_cuerpo(event):
    """Devuelve el body como dict, aceptando base64 de API Gateway."""
    crudo = event.get("body")
    if crudo in (None, ""):
        raise ApiError(400, "VALIDACION", "El cuerpo de la solicitud es obligatorio")

    if event.get("isBase64Encoded"):
        try:
            crudo = base64.b64decode(crudo).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise ApiError(
                400, "VALIDACION", "El cuerpo no es base64 valido"
            ) from error

    try:
        datos = json.loads(crudo)
    except (TypeError, json.JSONDecodeError) as error:
        raise ApiError(
            400, "VALIDACION", "El cuerpo debe ser JSON valido"
        ) from error

    if not isinstance(datos, dict):
        raise ApiError(400, "VALIDACION", "El cuerpo debe ser un objeto JSON")
    return datos


def _texto(datos, campo, obligatorio=False, maximo=None):
    valor = datos.get(campo)
    if valor is None:
        if obligatorio:
            raise ApiError(400, "VALIDACION", f"El campo '{campo}' es obligatorio")
        return None
    if not isinstance(valor, str):
        raise ApiError(400, "VALIDACION", f"El campo '{campo}' debe ser texto")
    valor = valor.strip()
    if obligatorio and not valor:
        raise ApiError(400, "VALIDACION", f"El campo '{campo}' es obligatorio")
    if maximo is not None and len(valor) > maximo:
        raise ApiError(
            400,
            "VALIDACION",
            f"El campo '{campo}' supera el maximo de {maximo} caracteres",
        )
    return valor


def validar_creacion(datos):
    servicio_id = _texto(datos, "servicio_id", obligatorio=True, maximo=100)
    titulo = _texto(datos, "titulo", obligatorio=True, maximo=200)
    if titulo is not None and len(titulo) < 3:
        raise ApiError(
            400, "VALIDACION", "El campo 'titulo' debe tener al menos 3 caracteres"
        )

    descripcion = _texto(datos, "descripcion", maximo=2000) or ""
    prioridad = (_texto(datos, "prioridad", maximo=20) or "medio").lower()

    if prioridad not in PRIORIDADES:
        raise ApiError(
            400,
            "VALIDACION",
            f"prioridad debe ser uno de: {', '.join(PRIORIDADES)}",
        )

    return {
        "servicio_id": servicio_id,
        "titulo": titulo,
        "descripcion": descripcion,
        "prioridad": prioridad,
    }


def validar_cambio_estado(datos):
    estado = _texto(datos, "estado", obligatorio=True, maximo=30)
    estado = estado.lower()
    if estado not in ESTADOS:
        raise ApiError(
            400,
            "VALIDACION",
            f"estado debe ser uno de: {', '.join(ESTADOS)}",
        )

    asignado_a = _texto(datos, "asignado_a", maximo=100)
    comentario = _texto(datos, "comentario", maximo=500) or ""

    return {
        "estado": estado,
        "asignado_a": asignado_a,
        "comentario": comentario,
    }


def validar_adjunto(datos):
    nombre = _texto(datos, "nombre_archivo", obligatorio=True, maximo=200)
    tipo = (_texto(datos, "content_type", maximo=120) or "application/octet-stream")
    tipo = tipo.lower()

    nombre = nombre.replace("\\", "/").split("/")[-1]
    nombre = _CARACTERES_SEGUROS.sub("_", nombre).strip("._")
    if not nombre:
        raise ApiError(
            400, "VALIDACION", "El nombre del archivo no es valido"
        )
    nombre = nombre[:120]

    if tipo not in TIPOS_ADJUNTO:
        raise ApiError(
            400,
            "VALIDACION",
            "content_type no permitido. Permitidos: "
            + ", ".join(sorted(TIPOS_ADJUNTO)),
        )

    return {"nombre_archivo": nombre, "content_type": tipo}


def validar_confirmacion_adjunto(datos):
    key = _texto(datos, "key", obligatorio=True, maximo=1024)
    return {"key": key}


def validar_limit(valor, por_defecto=25, maximo=100):
    if valor in (None, ""):
        return por_defecto
    try:
        numero = int(valor)
    except (TypeError, ValueError) as error:
        raise ApiError(400, "VALIDACION", "limit debe ser un numero") from error
    if numero < 1 or numero > maximo:
        raise ApiError(
            400, "VALIDACION", f"limit debe estar entre 1 y {maximo}"
        )
    return numero


def validar_estado_filtro(valor):
    if valor in (None, ""):
        return None
    estado = str(valor).strip().lower()
    if estado not in ESTADOS:
        raise ApiError(
            400,
            "VALIDACION",
            f"estado debe ser uno de: {', '.join(ESTADOS)}",
        )
    return estado


def normalizar_solicitud_id(valor):
    """Acepta REQ#000870, REQ%23000870 (sin decodificar) y REQ-000870.

    API Gateway REST entrega pathParameters SIN decodificar: un GET a
    /solicitudes/REQ%23000870 llega como "REQ%23000870". Se decodifica hasta
    dos veces para tolerar doble codificacion (%2523).
    """
    texto = str(valor or "").strip()
    for _ in range(2):
        decodificado = unquote(texto)
        if decodificado == texto:
            break
        texto = decodificado
    texto = texto.upper()
    if texto.startswith("REQ-"):
        texto = "REQ#" + texto[4:]
    if not _ID_SOLICITUD.match(texto):
        raise ApiError(404, "NO_ENCONTRADO", "Solicitud no encontrada")
    return texto


def pedazo_id_sin_hash(solicitud_id):
    return solicitud_id.replace("#", "-")


def prefijo_adjuntos(tenant_id, solicitud_id):
    return f"{tenant_id}/solicitudes/{pedazo_id_sin_hash(solicitud_id)}/"


def expiracion_adjuntos():
    try:
        return int(os.environ.get("ADJUNTOS_EXPIRACION", "300"))
    except ValueError:
        return 300


def max_adjunto_bytes():
    """Limite recomendado; con put_object no se puede imponer en la URL."""
    try:
        megas = int(os.environ.get("MAX_ADJUNTO_MB", "10"))
    except ValueError:
        megas = 10
    return megas * 1024 * 1024
