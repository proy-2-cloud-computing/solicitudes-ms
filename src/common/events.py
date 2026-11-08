"""Publicacion de eventos de dominio en SNS (best-effort)."""

import json
import logging
import os
import uuid

from .timeutils import ahora_utc

logger = logging.getLogger(__name__)
_sns = None


def _cliente():
    global _sns
    if _sns is None:
        import boto3
        from botocore.config import Config

        # SNS es best-effort: no debe colgar la respuesta HTTP.
        _sns = boto3.client(
            "sns",
            config=Config(
                connect_timeout=2,
                read_timeout=2,
                retries={"max_attempts": 1},
            ),
        )
    return _sns


def publicar_evento(tipo, tenant_id, solicitud_id, estado, actor_id, datos=None):
    evento_id = uuid.uuid4().hex
    mensaje = {
        "evento_id": evento_id,
        "tipo": tipo,
        "tenant_id": tenant_id,
        "id": solicitud_id,
        "estado": estado,
        "actor_id": actor_id,
        "fecha": ahora_utc(),
        "datos": datos or {},
    }

    try:
        _cliente().publish(
            TopicArn=os.environ["TOPIC_ARN"],
            Message=json.dumps(mensaje, ensure_ascii=False),
            MessageAttributes={
                "tenant_id": {"DataType": "String", "StringValue": tenant_id},
                "tipo": {"DataType": "String", "StringValue": tipo},
            },
        )
        return True
    except Exception:
        # La solicitud ya esta guardada: no se falla la peticion por SNS.
        logger.exception("No se pudo publicar el evento %s", tipo)
        return False
