#!/usr/bin/env python3
"""Carga 30,000 solicitudes de demo (10,000 por tenant).

Uso:
    python3 scripts/seed_solicitudes.py --stage dev --region us-east-1

Requiere credenciales AWS y que la tabla ya exista (serverless deploy).

Los `servicio_id` son placeholders (`SVC#000001`...`SVC#000020`). Cuando el
Catalogo real exista, reemplaza SERVICIOS por los IDs sembrados alli.
"""

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone

import boto3

TENANTS = ("empresa-alfa", "empresa-beta", "empresa-gamma")

SERVICIOS = [
    (
        f"SVC#{n:06d}",
        f"Servicio {n}",
        (8, 24, 48, 72)[(n - 1) % 4],
        n % 3 == 0,
    )
    for n in range(1, 21)
]

ESTADOS = (
    ("nueva", 0.20),
    ("en_aprobacion", 0.10),
    ("en_proceso", 0.30),
    ("completada", 0.30),
    ("cancelada", 0.10),
)

PRIORIDADES = ("bajo", "medio", "alto", "critico")


def elegir_estado(rng):
    valor = rng.random()
    acumulado = 0.0
    for estado, probabilidad in ESTADOS:
        acumulado += probabilidad
        if valor <= acumulado:
            return estado
    return ESTADOS[-1][0]


def iso(fecha):
    return fecha.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generar_item(rng, tenant_id, numero):
    servicio_id, nombre, sla_horas, requiere = rng.choice(SERVICIOS)
    estado = elegir_estado(rng)

    ahora = datetime.now(timezone.utc)
    creado = ahora - timedelta(
        days=rng.randint(0, 60),
        hours=rng.randint(0, 23),
        minutes=rng.randint(0, 59),
    )
    actualizado = min(creado + timedelta(hours=rng.randint(1, 48)), ahora)
    vence = creado + timedelta(hours=sla_horas)

    item = {
        "tenant_id": tenant_id,
        "sk": f"REQ#{numero:06d}",
        "servicio_id": servicio_id,
        "titulo": f"{nombre} para usuario {numero:06d}",
        "descripcion": "Solicitud generada por el script de datos de demo",
        "solicitante_id": f"u-{rng.randint(1000, 9999)}",
        "estado": estado,
        "prioridad": rng.choice(PRIORIDADES),
        "requiere_aprobacion": requiere,
        "nombre_servicio": nombre,
        "sla_horas": sla_horas,
        "sla_vence_en": iso(vence),
        "adjuntos": [],
        "creado_en": iso(creado),
        "actualizado_en": iso(actualizado),
        "estado_fecha": f"{estado}#{iso(creado)}",
    }

    if estado in ("en_proceso", "completada"):
        item["asignado_a"] = f"u-{rng.randint(1000, 9999)}"

    return item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="dev")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--table", help="Nombre de la tabla (default: itsm-solicitudes-<stage>)")
    parser.add_argument("--por-tenant", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tabla_nombre = args.table or f"itsm-solicitudes-{args.stage}"
    session = boto3.Session(region_name=args.region)
    tabla = session.resource("dynamodb").Table(tabla_nombre)

    rng = random.Random(args.seed)
    total = args.por_tenant * len(TENANTS)

    print(f"Tabla:      {tabla_nombre}")
    print(f"Tenants:    {', '.join(TENANTS)}")
    print(f"Registros:  {total} ({args.por_tenant} por tenant)")

    if args.dry_run:
        ejemplo = generar_item(rng, TENANTS[0], 1)
        print("Dry-run, primer item:")
        print(ejemplo)
        return

    contador = 0
    with tabla.batch_writer(overwrite_by_pkeys=["tenant_id", "sk"]) as lote:
        for tenant_id in TENANTS:
            for numero in range(1, args.por_tenant + 1):
                lote.put_item(Item=generar_item(rng, tenant_id, numero))
                contador += 1
                if contador % 1000 == 0:
                    print(f"  {contador}/{total}")

    ahora = iso(datetime.now(timezone.utc))
    for tenant_id in TENANTS:
        tabla.update_item(
            Key={"tenant_id": tenant_id, "sk": "CONTADOR#REQ"},
            UpdateExpression="SET ultimo_id = :n, actualizado_en = :ahora",
            ExpressionAttributeValues={
                ":n": args.por_tenant,
                ":ahora": ahora,
            },
        )

    print(f"Listo: {contador} solicitudes y contador en {args.por_tenant} por tenant.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
