import unittest
from unittest import mock

from src.handlers import historial
from tests.helpers import cuerpo, evento, item_solicitud


class HistorialTest(unittest.TestCase):
    def test_listar_historial(self):
        historial_item = {
            "tenant_id": "empresa-alfa",
            "sk": "HIST#REQ#000001#2026-11-11T09:30:00Z#abc",
            "solicitud_id": "REQ#000001",
            "estado_anterior": "",
            "estado_nuevo": "nueva",
            "actor_id": "u-1",
            "comentario": "Solicitud creada",
            "evento_id": "abc",
            "fecha": "2026-11-11T09:30:00Z",
        }
        with mock.patch.object(
            historial.db, "obtener_solicitud", return_value=item_solicitud()
        ), mock.patch.object(
            historial.db,
            "obtener_historial",
            return_value=([historial_item], None),
        ) as consultar:
            respuesta = historial.handler(
                evento(path={"id": "REQ#000001"}, query={"limit": "50"}),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 200)
        datos = cuerpo(respuesta)
        self.assertEqual(datos["solicitud_id"], "REQ#000001")
        self.assertEqual(datos["items"][0]["estado_nuevo"], "nueva")
        self.assertEqual(
            datos["items"][0]["historial_id"],
            "HIST#REQ#000001#2026-11-11T09:30:00Z#abc",
        )
        consultar.assert_called_once_with(
            "empresa-alfa", "REQ#000001", limit=50, next_token=None
        )

    def test_solicitud_no_existe(self):
        with mock.patch.object(
            historial.db, "obtener_solicitud", return_value=None
        ), mock.patch.object(
            historial.db, "obtener_historial"
        ) as consultar:
            respuesta = historial.handler(
                evento(path={"id": "REQ#000001"}), None
            )

        self.assertEqual(respuesta["statusCode"], 404)
        consultar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
