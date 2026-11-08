#!/usr/bin/env python3
"""Mock local del Catalogo de Servicios.

Uso:
    python3 scripts/mock_catalogo.py --puerto 8000

Expone:
    GET /health
    GET /catalogo/{servicio_id}

Lee el tenant del JWT sin verificar la firma (solo para desarrollo) desde el
claim `custom:tenant_id`. Si no hay token, usa `empresa-alfa`.
"""

import argparse
import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

SERVICIOS = {
    "SVC#000001": {
        "nombre": "Acceso VPN",
        "sla_horas": 48,
        "requiere_aprobacion": True,
        "activo": True,
    },
    "SVC#000002": {
        "nombre": "Instalacion de software",
        "sla_horas": 24,
        "requiere_aprobacion": False,
        "activo": True,
    },
    "SVC#000003": {
        "nombre": "Equipo portatil",
        "sla_horas": 72,
        "requiere_aprobacion": True,
        "activo": True,
    },
    "SVC#000004": {
        "nombre": "Alta de usuario",
        "sla_horas": 8,
        "requiere_aprobacion": False,
        "activo": True,
    },
    "SVC#INACTIVO": {
        "nombre": "Servicio retirado",
        "sla_horas": 24,
        "requiere_aprobacion": False,
        "activo": False,
    },
}


def tenant_del_token(authorization):
    try:
        token = (authorization or "").replace("Bearer ", "").strip()
        partes = token.split(".")
        if len(partes) != 3:
            return "empresa-alfa"
        payload = partes[1] + "=" * (-len(partes[1]) % 4)
        datos = json.loads(base64.urlsafe_b64decode(payload))
        return datos.get("custom:tenant_id") or datos.get("tenant_id") or "empresa-alfa"
    except Exception:
        return "empresa-alfa"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        ruta = urlparse(self.path).path

        if ruta == "/health":
            return self._responder(200, {"ok": True})

        if ruta.startswith("/catalogo/"):
            servicio_id = unquote(ruta[len("/catalogo/") :])
            servicio = SERVICIOS.get(servicio_id)
            if not servicio:
                return self._responder(
                    404,
                    {"error": {"code": "NO_ENCONTRADO", "message": "Servicio no existe"}},
                )

            tenant = tenant_del_token(self.headers.get("Authorization", ""))
            return self._responder(
                200,
                {
                    "tenant_id": tenant,
                    "servicio_id": servicio_id,
                    **servicio,
                },
            )

        self._responder(
            404,
            {"error": {"code": "NO_ENCONTRADO", "message": "Ruta no existe"}},
        )

    def _responder(self, estado, cuerpo):
        datos = json.dumps(cuerpo).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(datos)

    def log_message(self, formato, *args):
        print(f"[mock-catalogo] {self.address_string()} - {formato % args}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    servidor = ThreadingHTTPServer((args.host, args.puerto), Handler)
    print(f"Catalogo mock en http://localhost:{args.puerto}")
    print("Servicios: " + ", ".join(sorted(SERVICIOS)))
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nDetenido")


if __name__ == "__main__":
    main()
