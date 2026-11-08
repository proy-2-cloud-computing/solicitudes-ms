"""Utilidades de fecha y SLA (todo en UTC, formato ISO 8601 con Z)."""

from datetime import datetime, timedelta, timezone


def ahora_utc():
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parsear_iso(texto):
    if not texto:
        return None
    if isinstance(texto, datetime):
        return texto if texto.tzinfo else texto.replace(tzinfo=timezone.utc)
    valor = str(texto).strip()
    if valor.endswith("Z"):
        valor = valor[:-1] + "+00:00"
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    return fecha.astimezone(timezone.utc)


def sumar_horas(fecha_iso, horas):
    fecha = parsear_iso(fecha_iso)
    if fecha is None:
        return None
    return (
        (fecha + timedelta(hours=float(horas)))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def esta_vencido(fecha_iso, ahora=None):
    fecha = parsear_iso(fecha_iso)
    if fecha is None:
        return False
    referencia = parsear_iso(ahora) if ahora else datetime.now(timezone.utc)
    if referencia is None:
        referencia = datetime.now(timezone.utc)
    return fecha < referencia


def segundos_restantes(fecha_iso, ahora=None):
    fecha = parsear_iso(fecha_iso)
    if fecha is None:
        return None
    referencia = parsear_iso(ahora) if ahora else datetime.now(timezone.utc)
    if referencia is None:
        referencia = datetime.now(timezone.utc)
    return int((fecha - referencia).total_seconds())
