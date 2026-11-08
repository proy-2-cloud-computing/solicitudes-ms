import unittest
from decimal import Decimal

from src.common import db
from src.common.responses import ApiError
from tests.helpers import item_solicitud


class SerializacionTest(unittest.TestCase):
    def test_serializar_solicitud(self):
        item = item_solicitud(sla_horas=Decimal("48"))
        salida = db.serializar_solicitud(item, ahora="2026-01-01T00:00:00Z")
        self.assertEqual(salida["solicitud_id"], "REQ#000001")
        self.assertNotIn("sk", salida)
        self.assertNotIn("estado_fecha", salida)
        self.assertEqual(salida["sla_horas"], 48)
        self.assertFalse(salida["sla_vencido"])

    def test_sla_vencido(self):
        item = item_solicitud(sla_vence_en="2020-01-01T00:00:00Z")
        salida = db.serializar_solicitud(item, ahora="2026-01-01T00:00:00Z")
        self.assertTrue(salida["sla_vencido"])

    def test_serializar_historial(self):
        item = {
            "tenant_id": "empresa-alfa",
            "sk": "HIST#REQ#000001#2026-01-01T00:00:00Z#abc",
            "solicitud_id": "REQ#000001",
            "estado_anterior": "nueva",
            "estado_nuevo": "en_proceso",
        }
        salida = db.serializar_historial(item)
        self.assertEqual(
            salida["historial_id"],
            "HIST#REQ#000001#2026-01-01T00:00:00Z#abc",
        )
        self.assertNotIn("sk", salida)

    def test_decimales_anidados(self):
        valor = {"a": [Decimal("1"), Decimal("2.5")], "b": Decimal("3")}
        self.assertEqual(
            db._normalizar_decimales(valor), {"a": [1, 2.5], "b": 3}
        )


class PaginacionTest(unittest.TestCase):
    def test_codificar_y_decodificar(self):
        key = {
            "tenant_id": "empresa-alfa",
            "sk": "REQ#000025",
            "estado_fecha": "nueva#2026-01-01T00:00:00Z",
        }
        token = db.codificar_token(key)
        self.assertIsNotNone(token)
        self.assertEqual(db.decodificar_token(token), key)

    def test_token_vacio(self):
        self.assertIsNone(db.codificar_token(None))

    def test_token_invalido(self):
        for token in ("%%%", "abc", "W10="):  # W10= es "[]"
            with self.subTest(token=token):
                with self.assertRaises(ApiError) as error:
                    db.decodificar_token(token)
                self.assertEqual(error.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
