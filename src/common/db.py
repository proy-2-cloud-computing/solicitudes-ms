"""Acceso a DynamoDB: solicitudes, contador, historial y consultas.

Patrones de acceso:
  - Obtener:      GetItem(PK=tenant, SK=REQ#...)
  - Listar:       Query(PK=tenant, begins_with(sk, "REQ#"))
  - Por estado:   Query(GSI1, begins_with(estado_fecha, "estado#"))
  - Historial:    Query(PK=tenant, begins_with(sk, "HIST#REQ#..."))
  - Resumen:      Query(GSI1, Select=COUNT) por estado
Nunca se usa Scan.
"""

import base64
import json
import logging
import os
import uuid
from decimal import Decimal

from .responses import ApiError
from .timeutils import ahora_utc, esta_vencido
from .validation import ESTADOS

logger = logging.getLogger(__name__)

_recurso = None


# ---------------------------------------------------------------------------
# Conexion
# ---------------------------------------------------------------------------
def _recurso_dynamo():
    global _recurso
    if _recurso is None:
        import boto3

        _recurso = boto3.resource("dynamodb")
    return _recurso


def tabla():
    return _recurso_dynamo().Table(os.environ["TABLE"])


def cliente():
    return _recurso_dynamo().meta.client


def _item_dynamo(item):
    """Quita los None y deja los valores nativos de Python.

    cliente() es resource.meta.client: boto3 ya serializa los tipos nativos
    (tambien dentro de transact_write_items). Si se pasan valores ya
    serializados con TypeSerializer ({"S": ...}) se serializan DOS veces,
    tenant_id llega como mapa y DynamoDB cancela la transaccion.
    """
    return {clave: valor for clave, valor in item.items() if valor is not None}


_MOTIVOS_CONFLICTO = {"ConditionalCheckFailed", "TransactionConflict"}


def _es_conflicto(error):
    """True solo si DynamoDB rechazo por condicion o concurrencia.

    Una transaccion cancelada por otra causa (ValidationError, throttling...)
    no es un conflicto del usuario: se registra el motivo y se propaga (500).
    """
    respuesta = getattr(error, "response", {}) or {}
    codigo = respuesta.get("Error", {}).get("Code", "")
    if codigo == "ConditionalCheckFailedException":
        return True
    if codigo != "TransactionCanceledException":
        return False
    motivos = [
        motivo.get("Code")
        for motivo in respuesta.get("CancellationReasons") or []
        if motivo.get("Code") not in (None, "None")
    ]
    if motivos and set(motivos) <= _MOTIVOS_CONFLICTO:
        return True
    logger.error(
        "Transaccion cancelada: %s",
        respuesta.get("CancellationReasons") or respuesta.get("Error"),
    )
    return False


# ---------------------------------------------------------------------------
# Contador e IDs
# ---------------------------------------------------------------------------
def nuevo_id_solicitud(tenant_id):
    """Incrementa el contador atomico y devuelve el siguiente entero."""
    respuesta = tabla().update_item(
        Key={"tenant_id": tenant_id, "sk": "CONTADOR#REQ"},
        UpdateExpression="ADD ultimo_id :uno SET actualizado_en = :ahora",
        ExpressionAttributeValues={":uno": 1, ":ahora": ahora_utc()},
        ReturnValues="UPDATED_NEW",
    )
    return int(respuesta["Attributes"]["ultimo_id"])


# ---------------------------------------------------------------------------
# Crear
# ---------------------------------------------------------------------------
def crear_solicitud(item, historial):
    """Escribe solicitud + primer historial en una transaccion."""
    try:
        cliente().transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": os.environ["TABLE"],
                        "Item": _item_dynamo(item),
                        "ConditionExpression": "attribute_not_exists(sk)",
                    }
                },
                {
                    "Put": {
                        "TableName": os.environ["TABLE"],
                        "Item": _item_dynamo(historial),
                    }
                },
            ]
        )
    except Exception as error:
        if _es_conflicto(error):
            raise ApiError(
                409, "CONFLICTO", "No se pudo crear la solicitud; reintenta"
            ) from error
        raise


# ---------------------------------------------------------------------------
# Leer
# ---------------------------------------------------------------------------
def obtener_solicitud(tenant_id, solicitud_id):
    respuesta = tabla().get_item(
        Key={"tenant_id": tenant_id, "sk": solicitud_id}
    )
    item = respuesta.get("Item")
    if not item or not str(item.get("sk", "")).startswith("REQ#"):
        return None
    return item


def listar_solicitudes(tenant_id, estado=None, limit=25, next_token=None):
    kwargs = {"Limit": int(limit)}

    if estado:
        kwargs["IndexName"] = "GSI1"
        kwargs["KeyConditionExpression"] = (
            "tenant_id = :tenant AND begins_with(estado_fecha, :prefijo)"
        )
        kwargs["ExpressionAttributeValues"] = {
            ":tenant": tenant_id,
            ":prefijo": f"{estado}#",
        }
    else:
        kwargs["KeyConditionExpression"] = (
            "tenant_id = :tenant AND begins_with(sk, :prefijo)"
        )
        kwargs["ExpressionAttributeValues"] = {
            ":tenant": tenant_id,
            ":prefijo": "REQ#",
        }

    if next_token:
        kwargs["ExclusiveStartKey"] = decodificar_token(next_token)

    respuesta = tabla().query(**kwargs)
    return respuesta.get("Items", []), codificar_token(
        respuesta.get("LastEvaluatedKey")
    )


def obtener_historial(tenant_id, solicitud_id, limit=100, next_token=None):
    kwargs = {
        "KeyConditionExpression": (
            "tenant_id = :tenant AND begins_with(sk, :prefijo)"
        ),
        "ExpressionAttributeValues": {
            ":tenant": tenant_id,
            ":prefijo": f"HIST#{solicitud_id}#",
        },
        "Limit": int(limit),
        "ScanIndexForward": True,
    }
    if next_token:
        kwargs["ExclusiveStartKey"] = decodificar_token(next_token)

    respuesta = tabla().query(**kwargs)
    return respuesta.get("Items", []), codificar_token(
        respuesta.get("LastEvaluatedKey")
    )


def _contar(**kwargs):
    """Query con Select=COUNT sumando TODAS las paginas.

    DynamoDB tambien pagina los COUNT (1 MB evaluado por pagina): con 10,000
    solicitudes por tenant una sola llamada devuelve solo ~2,500.
    """
    kwargs["Select"] = "COUNT"
    total = 0
    while True:
        respuesta = tabla().query(**kwargs)
        total += int(respuesta.get("Count", 0))
        siguiente = respuesta.get("LastEvaluatedKey")
        if not siguiente:
            return total
        kwargs["ExclusiveStartKey"] = siguiente


def contar_por_estado(tenant_id):
    conteos = {}
    for estado in ESTADOS:
        conteos[estado] = _contar(
            IndexName="GSI1",
            KeyConditionExpression=(
                "tenant_id = :tenant AND begins_with(estado_fecha, :prefijo)"
            ),
            ExpressionAttributeValues={
                ":tenant": tenant_id,
                ":prefijo": f"{estado}#",
            },
        )

    total = _contar(
        KeyConditionExpression=(
            "tenant_id = :tenant AND begins_with(sk, :prefijo)"
        ),
        ExpressionAttributeValues={":tenant": tenant_id, ":prefijo": "REQ#"},
    )
    return total, conteos


# ---------------------------------------------------------------------------
# Cambiar estado
# ---------------------------------------------------------------------------
def cambiar_estado(item, datos, actor_id):
    """Actualiza estado + escribe historial en una transaccion.

    Usa ConditionExpression sobre el estado anterior (bloqueo optimista).
    """
    tenant_id = item["tenant_id"]
    solicitud_id = item["sk"]
    estado_anterior = item["estado"]
    estado_nuevo = datos["estado"]
    ahora = ahora_utc()
    estado_fecha = f"{estado_nuevo}#{item.get('creado_en', ahora)}"

    expresion = (
        "SET estado = :nuevo, actualizado_en = :ahora, estado_fecha = :ef"
    )
    valores = {
        ":nuevo": estado_nuevo,
        ":ahora": ahora,
        ":ef": estado_fecha,
        ":anterior": estado_anterior,
    }
    if datos.get("asignado_a"):
        expresion += ", asignado_a = :asignado"
        valores[":asignado"] = datos["asignado_a"]

    evento_id = uuid.uuid4().hex[:8]
    historial = {
        "tenant_id": tenant_id,
        "sk": f"HIST#{solicitud_id}#{ahora}#{evento_id}",
        "solicitud_id": solicitud_id,
        "estado_anterior": estado_anterior,
        "estado_nuevo": estado_nuevo,
        "actor_id": actor_id,
        "comentario": datos.get("comentario", ""),
        "evento_id": evento_id,
        "fecha": ahora,
    }

    # Valores nativos: cliente() (resource.meta.client) ya los serializa.
    try:
        cliente().transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": os.environ["TABLE"],
                        "Key": {"tenant_id": tenant_id, "sk": solicitud_id},
                        "UpdateExpression": expresion,
                        "ConditionExpression": (
                            "attribute_exists(sk) AND estado = :anterior"
                        ),
                        "ExpressionAttributeValues": valores,
                    }
                },
                {
                    "Put": {
                        "TableName": os.environ["TABLE"],
                        "Item": _item_dynamo(historial),
                    }
                },
            ]
        )
    except Exception as error:
        if _es_conflicto(error):
            raise ApiError(
                409,
                "CONFLICTO",
                "La solicitud cambio de estado; actualiza y reintenta",
            ) from error
        raise

    return historial


# ---------------------------------------------------------------------------
# Adjuntos
# ---------------------------------------------------------------------------
def agregar_adjunto(tenant_id, solicitud_id, key):
    try:
        respuesta = tabla().update_item(
            Key={"tenant_id": tenant_id, "sk": solicitud_id},
            UpdateExpression=(
                "SET adjuntos = list_append(if_not_exists(adjuntos, :vacio), "
                ":nuevo), actualizado_en = :ahora"
            ),
            ConditionExpression="attribute_exists(sk)",
            ExpressionAttributeValues={
                ":vacio": [],
                ":nuevo": [key],
                ":ahora": ahora_utc(),
            },
            ReturnValues="ALL_NEW",
        )
        return respuesta.get("Attributes")
    except Exception as error:
        if _es_conflicto(error):
            raise ApiError(
                404, "NO_ENCONTRADO", "Solicitud no encontrada"
            ) from error
        raise


# ---------------------------------------------------------------------------
# Serializacion para la API
# ---------------------------------------------------------------------------
def serializar_solicitud(item, ahora=None):
    salida = dict(item)
    solicitud_id = salida.pop("sk", None)
    salida.pop("estado_fecha", None)
    salida["solicitud_id"] = solicitud_id
    salida["sla_vencido"] = esta_vencido(salida.get("sla_vence_en"), ahora)
    return _normalizar_decimales(salida)


def serializar_historial(item):
    salida = dict(item)
    historial_id = salida.pop("sk", None)
    salida["historial_id"] = historial_id
    return _normalizar_decimales(salida)


def _normalizar_decimales(valor):
    if isinstance(valor, Decimal):
        if valor == valor.to_integral_value():
            return int(valor)
        return float(valor)
    if isinstance(valor, dict):
        return {k: _normalizar_decimales(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_normalizar_decimales(v) for v in valor]
    return valor


# ---------------------------------------------------------------------------
# Paginacion
# ---------------------------------------------------------------------------
def codificar_token(last_key):
    if not last_key:
        return None
    crudo = json.dumps(last_key, default=str, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(crudo).decode().rstrip("=")


def decodificar_token(token):
    try:
        token = str(token).rstrip("=")
        relleno = "=" * (-len(token) % 4)
        datos = json.loads(base64.urlsafe_b64decode(token + relleno))
        if not isinstance(datos, dict):
            raise ValueError("token no es objeto")
        return datos
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ApiError(
            400, "VALIDACION", "El token de paginacion no es valido"
        ) from error
