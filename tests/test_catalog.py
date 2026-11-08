import io
import json
import os
import unittest
import urllib.error
from unittest import mock

os.environ["CATALOGO_URL"] = "http://catalogo.test"
os.environ["CATALOGO_TIMEOUT"] = "1"

from src.common import catalog  # noqa: E402
from src.common.responses import ApiError  # noqa: E402


class RespuestaFalsa:
    def __init__(self, datos):
        self._datos = json.dumps(datos).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._datos


class CatalogoTest(unittest.TestCase):
    def test_200_normaliza(self):
        respuesta = RespuestaFalsa(
            {
                "tenant_id": "empresa-alfa",
                "servicio_id": "SVC#000012",
                "nombre": "Acceso VPN",
                "sla_horas": "48",
                "requiere_aprobacion": True,
                "activo": True,
            }
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", return_value=respuesta
        ) as urlopen:
            datos = catalog.obtener_servicio(
                "SVC#000012", "Bearer x", "empresa-alfa"
            )

        self.assertEqual(datos["nombre"], "Acceso VPN")
        self.assertEqual(datos["sla_horas"], 48)
        self.assertTrue(datos["requiere_aprobacion"])
        # El # debe ir URL-encoded.
        llamada = urlopen.call_args[0][0]
        self.assertIn("SVC%23000012", llamada.full_url)
        self.assertEqual(llamada.headers["Authorization"], "Bearer x")

    def test_404_servicio_invalido(self):
        error = urllib.error.HTTPError(
            "http://catalogo.test", 404, "Not Found", {}, io.BytesIO(b"")
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", side_effect=error
        ):
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#9", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.status, 400)
        self.assertEqual(capturado.exception.code, "SERVICIO_INVALIDO")

    def test_5xx_reintenta_y_devuelve_503(self):
        error = urllib.error.HTTPError(
            "http://catalogo.test", 500, "Error", {}, io.BytesIO(b"")
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", side_effect=error
        ) as urlopen:
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#9", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.status, 503)
        self.assertEqual(urlopen.call_count, 2)

    def test_timeout_reintenta_y_devuelve_503(self):
        with mock.patch.object(
            catalog.urllib.request,
            "urlopen",
            side_effect=TimeoutError("timeout"),
        ) as urlopen:
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#9", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.status, 503)
        self.assertEqual(urlopen.call_count, 2)

    def test_tenant_distinto_no_revela(self):
        respuesta = RespuestaFalsa(
            {
                "tenant_id": "empresa-beta",
                "nombre": "Acceso VPN",
                "sla_horas": 48,
                "requiere_aprobacion": False,
            }
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", return_value=respuesta
        ):
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio(
                    "SVC#1", "Bearer x", "empresa-alfa"
                )
        self.assertEqual(capturado.exception.status, 400)

    def test_activo_false(self):
        respuesta = RespuestaFalsa(
            {
                "nombre": "X",
                "sla_horas": 24,
                "requiere_aprobacion": False,
                "activo": False,
            }
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", return_value=respuesta
        ):
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#1", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.status, 400)

    def test_sla_invalido(self):
        respuesta = RespuestaFalsa(
            {"nombre": "X", "sla_horas": 0, "requiere_aprobacion": False}
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", return_value=respuesta
        ):
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#1", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.code, "CATALOGO_INVALIDO")

    def test_sin_url_configurada(self):
        with mock.patch.dict(os.environ, {"CATALOGO_URL": ""}):
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#1", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.status, 503)

    def test_401_del_catalogo(self):
        error = urllib.error.HTTPError(
            "http://catalogo.test", 401, "Unauthorized", {}, io.BytesIO(b"")
        )
        with mock.patch.object(
            catalog.urllib.request, "urlopen", side_effect=error
        ):
            with self.assertRaises(ApiError) as capturado:
                catalog.obtener_servicio("SVC#1", "Bearer x", "empresa-alfa")
        self.assertEqual(capturado.exception.status, 502)


if __name__ == "__main__":
    unittest.main()
