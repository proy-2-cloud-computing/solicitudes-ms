import unittest

from src.common.responses import ApiError
from src.common.transitions import TRANSICIONES, transicion_permitida, validar_cambio


def ctx(*grupos, usuario="u-1"):
    return {"tenant_id": "empresa-alfa", "usuario_id": usuario, "grupos": set(grupos)}


class TransicionesTest(unittest.TestCase):
    def test_matriz_de_transiciones(self):
        self.assertTrue(transicion_permitida("nueva", "en_aprobacion"))
        self.assertTrue(transicion_permitida("nueva", "en_proceso"))
        self.assertTrue(transicion_permitida("nueva", "cancelada"))
        self.assertTrue(transicion_permitida("en_aprobacion", "en_proceso"))
        self.assertTrue(transicion_permitida("en_aprobacion", "cancelada"))
        self.assertTrue(transicion_permitida("en_proceso", "completada"))
        self.assertTrue(transicion_permitida("en_proceso", "cancelada"))
        self.assertFalse(transicion_permitida("nueva", "completada"))
        self.assertEqual(TRANSICIONES["completada"], set())
        self.assertEqual(TRANSICIONES["cancelada"], set())

    def test_transicion_invalida_es_409(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("agente"), "nueva", "completada", "u-1")
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(error.exception.code, "TRANSICION_INVALIDA")

    def test_agente_puede_mover_nueva(self):
        validar_cambio(ctx("agente"), "nueva", "en_proceso", "u-1")
        validar_cambio(ctx("agente"), "nueva", "en_aprobacion", "u-1")

    def test_aprobador_no_mueve_nueva(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("aprobador"), "nueva", "en_proceso", "u-1")
        self.assertEqual(error.exception.status, 403)

    def test_aprobador_aprueba(self):
        validar_cambio(ctx("aprobador"), "en_aprobacion", "en_proceso", "u-1")

    def test_agente_no_aprueba(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("agente"), "en_aprobacion", "en_proceso", "u-1")
        self.assertEqual(error.exception.status, 403)

    def test_agente_completa(self):
        validar_cambio(ctx("agente"), "en_proceso", "completada", "u-1")

    def test_solicitante_dueno_cancela_nueva(self):
        validar_cambio(ctx("solicitante"), "nueva", "cancelada", "u-1")

    def test_solicitante_no_dueno_no_cancela(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("solicitante"), "nueva", "cancelada", "u-2")
        self.assertEqual(error.exception.status, 403)

    def test_solicitante_no_cancela_en_proceso(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("solicitante"), "en_proceso", "cancelada", "u-1")
        self.assertEqual(error.exception.status, 403)

    def test_aprobador_cancela_en_aprobacion(self):
        validar_cambio(ctx("aprobador"), "en_aprobacion", "cancelada", "u-1")

    def test_agente_no_cancela_en_aprobacion(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("agente"), "en_aprobacion", "cancelada", "u-1")
        self.assertEqual(error.exception.status, 403)

    def test_estado_terminal(self):
        with self.assertRaises(ApiError) as error:
            validar_cambio(ctx("admin"), "completada", "cancelada", "u-1")
        self.assertEqual(error.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
