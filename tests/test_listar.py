import unittest
from decimal import Decimal
from unittest import mock

from src.handlers import listar
from tests.helpers import cuerpo, evento, item_solicitud


class ListarTest(unittest.TestCase):
    def test_listar_pagina(self):
        item = item_solicitud(sla_horas=Decimal("48"))
        with mock.patch.object(
            listar.db,
            "listar_solicitudes",
            return_value=([item], "siguiente-token"),
        ) as consultar:
            respuesta = listar.handler(
                evento(query={"estado": "nueva", "limit": "10", "next": "abc"}),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 200)
        datos = cuerpo(respuesta)
        self.assertEqual(datos["items"][0]["solicitud_id"], "REQ#000001")
        self.assertEqual(datos["items"][0]["sla_horas"], 48)
        self.assertEqual(datos["next"], "siguiente-token")
        consultar.assert_called_once_with(
            "empresa-alfa",
            estado="nueva",
            limit=10,
            next_token="abc",
        )

    def test_defaults(self):
        with mock.patch.object(
            listar.db, "listar_solicitudes", return_value=([], None)
        ) as consultar:
            respuesta = listar.handler(evento(), None)

        self.assertEqual(respuesta["statusCode"], 200)
        self.assertEqual(cuerpo(respuesta), {"items": [], "next": None})
        consultar.assert_called_once_with(
            "empresa-alfa", estado=None, limit=25, next_token=None
        )

    def test_estado_invalido(self):
        with mock.patch.object(
            listar.db, "listar_solicitudes"
        ) as consultar:
            respuesta = listar.handler(evento(query={"estado": "otro"}), None)

        self.assertEqual(respuesta["statusCode"], 400)
        consultar.assert_not_called()

    def test_limit_invalido(self):
        with mock.patch.object(
            listar.db, "listar_solicitudes"
        ) as consultar:
            respuesta = listar.handler(evento(query={"limit": "500"}), None)

        self.assertEqual(respuesta["statusCode"], 400)
        consultar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
