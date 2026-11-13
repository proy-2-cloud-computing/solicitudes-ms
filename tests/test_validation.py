import base64
import json
import unittest

from src.common.responses import ApiError
from src.common.validation import (
    ESTADOS,
    leer_cuerpo,
    normalizar_solicitud_id,
    pedazo_id_sin_hash,
    prefijo_adjuntos,
    validar_adjunto,
    validar_cambio_estado,
    validar_confirmacion_adjunto,
    validar_creacion,
    validar_estado_filtro,
    validar_limit,
)


class ValidacionTest(unittest.TestCase):
    def test_leer_cuerpo_json(self):
        self.assertEqual(leer_cuerpo({"body": '{"a": 1}'}), {"a": 1})

    def test_leer_cuerpo_base64(self):
        crudo = base64.b64encode(b'{"a": 1}').decode()
        evento = {"body": crudo, "isBase64Encoded": True}
        self.assertEqual(leer_cuerpo(evento), {"a": 1})

    def test_leer_cuerpo_invalido(self):
        for evento in ({}, {"body": ""}, {"body": "{malo"}):
            with self.subTest(evento=evento):
                with self.assertRaises(ApiError) as error:
                    leer_cuerpo(evento)
                self.assertEqual(error.exception.status, 400)

    def test_creacion_minima(self):
        datos = validar_creacion(
            {"servicio_id": "SVC#000001", "titulo": "Acceso VPN"}
        )
        self.assertEqual(datos["prioridad"], "medio")
        self.assertEqual(datos["descripcion"], "")

    def test_creacion_completa(self):
        datos = validar_creacion(
            {
                "servicio_id": "SVC#000001",
                "titulo": "  Acceso VPN  ",
                "descripcion": " Detalle ",
                "prioridad": "ALTO",
            }
        )
        self.assertEqual(datos["titulo"], "Acceso VPN")
        self.assertEqual(datos["prioridad"], "alto")

    def test_creacion_errores(self):
        casos = [
            {},
            {"servicio_id": "SVC#1"},
            {"servicio_id": "SVC#1", "titulo": "ab"},
            {"servicio_id": "SVC#1", "titulo": "abc", "prioridad": "urgente"},
            {"servicio_id": "SVC#1", "titulo": "abc", "descripcion": "x" * 2001},
            {"servicio_id": 123, "titulo": "abc"},
        ]
        for caso in casos:
            with self.subTest(caso=caso):
                with self.assertRaises(ApiError) as error:
                    validar_creacion(caso)
                self.assertEqual(error.exception.status, 400)

    def test_cambio_estado(self):
        datos = validar_cambio_estado({"estado": "EN_PROCESO"})
        self.assertEqual(datos["estado"], "en_proceso")
        self.assertIsNone(datos["asignado_a"])
        self.assertEqual(datos["comentario"], "")

    def test_cambio_estado_invalido(self):
        for cuerpo in ({}, {"estado": "volando"}, {"estado": 1}):
            with self.subTest(cuerpo=cuerpo):
                with self.assertRaises(ApiError):
                    validar_cambio_estado(cuerpo)

    def test_adjunto_sanea_nombre(self):
        datos = validar_adjunto(
            {
                "nombre_archivo": "../../etc/passwd.pdf",
                "content_type": "application/pdf",
            }
        )
        self.assertEqual(datos["nombre_archivo"], "passwd.pdf")

    def test_adjunto_tipo_invalido(self):
        with self.assertRaises(ApiError) as error:
            validar_adjunto(
                {"nombre_archivo": "x.pdf", "content_type": "application/x-msdownload"}
            )
        self.assertEqual(error.exception.status, 400)

    def test_confirmacion_adjunto(self):
        self.assertEqual(
            validar_confirmacion_adjunto({"key": "a/b.pdf"}), {"key": "a/b.pdf"}
        )
        with self.assertRaises(ApiError):
            validar_confirmacion_adjunto({})

    def test_normalizar_id(self):
        self.assertEqual(
            normalizar_solicitud_id("req#000870"), "REQ#000870"
        )
        # API Gateway REST entrega el path parameter sin decodificar.
        for valor in ("REQ%23000870", "req%23000870", "REQ%2523000870", "REQ-000870"):
            with self.subTest(valor=valor):
                self.assertEqual(normalizar_solicitud_id(valor), "REQ#000870")
        for valor in (None, "", "REQ#", "000870", "SVC#000001", "SVC%23000001"):
            with self.subTest(valor=valor):
                with self.assertRaises(ApiError) as error:
                    normalizar_solicitud_id(valor)
                self.assertEqual(error.exception.status, 404)

    def test_prefijos(self):
        self.assertEqual(pedazo_id_sin_hash("REQ#000870"), "REQ-000870")
        self.assertEqual(
            prefijo_adjuntos("empresa-beta", "REQ#000870"),
            "empresa-beta/solicitudes/REQ-000870/",
        )

    def test_limit(self):
        self.assertEqual(validar_limit(None), 25)
        self.assertEqual(validar_limit("10"), 10)
        for valor in ("0", "101", "abc"):
            with self.subTest(valor=valor):
                with self.assertRaises(ApiError):
                    validar_limit(valor)

    def test_estado_filtro(self):
        self.assertIsNone(validar_estado_filtro(None))
        self.assertEqual(validar_estado_filtro("EN_PROCESO"), "en_proceso")
        with self.assertRaises(ApiError):
            validar_estado_filtro("otro")

    def test_estados_completos(self):
        self.assertEqual(
            set(ESTADOS),
            {"nueva", "en_aprobacion", "en_proceso", "completada", "cancelada"},
        )


if __name__ == "__main__":
    unittest.main()
