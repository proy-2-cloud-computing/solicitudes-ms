"""Helpers para construir eventos de API Gateway en las pruebas."""

import json


def evento(
    metodo="GET",
    body=None,
    path=None,
    query=None,
    tenant="empresa-alfa",
    sub="u-1",
    grupos=("solicitante",),
    authorization="Bearer token-de-prueba",
):
    claims = {"sub": sub}
    if tenant is not None:
        claims["custom:tenant_id"] = tenant
    if grupos is not None:
        claims["cognito:groups"] = list(grupos)

    return {
        "httpMethod": metodo,
        "body": None if body is None else json.dumps(body),
        "pathParameters": path,
        "queryStringParameters": query,
        "headers": {"Authorization": authorization},
        "requestContext": {"authorizer": {"claims": claims}},
    }


def cuerpo(respuesta):
    return json.loads(respuesta["body"])


def item_solicitud(
    estado="nueva",
    tenant="empresa-alfa",
    solicitud_id="REQ#000001",
    solicitante="u-1",
    **extra,
):
    item = {
        "tenant_id": tenant,
        "sk": solicitud_id,
        "servicio_id": "SVC#000001",
        "titulo": "Acceso VPN",
        "descripcion": "Alta de acceso",
        "solicitante_id": solicitante,
        "estado": estado,
        "prioridad": "medio",
        "requiere_aprobacion": False,
        "nombre_servicio": "Acceso VPN",
        "sla_horas": 48,
        "sla_vence_en": "2099-01-01T00:00:00Z",
        "adjuntos": [],
        "creado_en": "2026-11-11T09:30:00Z",
        "actualizado_en": "2026-11-11T09:30:00Z",
        "estado_fecha": f"{estado}#2026-11-11T09:30:00Z",
    }
    item.update(extra)
    return item
