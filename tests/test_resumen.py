import unittest
from unittest import mock

from src.handlers import resumen
from tests.helpers import cuerpo, evento


class ResumenTest(unittest.TestCase):
    def test_resumen(self):
        conteos = {
            "nueva": 2,
            "en_aprobacion": 1,
            "en_proceso": 3,
            "completada": 4,
            "cancelada": 0,
        }
        with mock.patch.object(
            resumen.db,
            "contar_por_estado",
            return_value=(10, conteos),
        ) as contar:
            respuesta = resumen.handler(evento(), None)

        self.assertEqual(respuesta["statusCode"], 200)
        self.assertEqual(
            cuerpo(respuesta),
            {
                "tenant_id": "empresa-alfa",
                "total": 10,
                "por_estado": conteos,
            },
        )
        contar.assert_called_once_with("empresa-alfa")


if __name__ == "__main__":
    unittest.main()
