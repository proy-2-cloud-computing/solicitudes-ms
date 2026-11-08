import unittest
from unittest import mock

from src.handlers import obtener
from tests.helpers import cuerpo, evento, item_solicitud


class ObtenerTest(unittest.TestCase):
    def test_obtener_existente(self):
        with mock.patch.object(
            obtener.db,
            "obtener_solicitud",
            return_value=item_solicitud(),
        ) as consultar:
            respuesta = obtener.handler(
                evento(path={"id": "REQ#000001"}), None
            )

        self.assertEqual(respuesta["statusCode"], 200)
        datos = cuerpo(respuesta)
        self.assertEqual(datos["solicitud_id"], "REQ#000001")
        self.assertFalse(datos["sla_vencido"])
        consultar.assert_called_once_with("empresa-alfa", "REQ#000001")

    def test_no_existe_o_es_de_otro_tenant(self):
        with mock.patch.object(
            obtener.db, "obtener_solicitud", return_value=None
        ):
            respuesta = obtener.handler(
                evento(path={"id": "REQ#000999"}), None
            )

        self.assertEqual(respuesta["statusCode"], 404)
        self.assertEqual(cuerpo(respuesta)["error"]["code"], "NO_ENCONTRADO")

    def test_id_invalido_no_consulta(self):
        with mock.patch.object(
            obtener.db, "obtener_solicitud"
        ) as consultar:
            respuesta = obtener.handler(
                evento(path={"id": "SVC#000001"}), None
            )

        self.assertEqual(respuesta["statusCode"], 404)
        consultar.assert_not_called()

    def test_sin_id(self):
        with mock.patch.object(
            obtener.db, "obtener_solicitud"
        ) as consultar:
            respuesta = obtener.handler(evento(path={}), None)

        self.assertEqual(respuesta["statusCode"], 404)
        consultar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
