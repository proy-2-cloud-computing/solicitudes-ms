import unittest
from unittest import mock

from src.handlers import adjuntos
from tests.helpers import cuerpo, evento, item_solicitud

PREFIJO = "empresa-alfa/solicitudes/REQ-000001/"


class AdjuntosTest(unittest.TestCase):
    def test_firmar_como_dueno(self):
        item = item_solicitud()
        with mock.patch.object(
            adjuntos.db, "obtener_solicitud", return_value=item
        ), mock.patch.object(
            adjuntos.storage,
            "generar_url_prefirmada",
            return_value="https://s3/upload",
        ) as firmar:
            respuesta = adjuntos.handler(
                evento(
                    metodo="POST",
                    path={"id": "REQ#000001"},
                    body={
                        "nombre_archivo": "vpn.pdf",
                        "content_type": "application/pdf",
                    },
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 200)
        datos = cuerpo(respuesta)
        self.assertEqual(datos["upload_url"], "https://s3/upload")
        self.assertTrue(datos["key"].startswith(PREFIJO))
        self.assertTrue(datos["key"].endswith("-vpn.pdf"))
        self.assertEqual(datos["expires_in"], 300)
        self.assertEqual(datos["metodo"], "PUT")
        firmar.assert_called_once()
        self.assertEqual(firmar.call_args[0][1], "application/pdf")

    def test_agente_puede_firmar_para_otro(self):
        with mock.patch.object(
            adjuntos.db,
            "obtener_solicitud",
            return_value=item_solicitud(solicitante="u-9"),
        ), mock.patch.object(
            adjuntos.storage,
            "generar_url_prefirmada",
            return_value="https://s3/upload",
        ):
            respuesta = adjuntos.handler(
                evento(
                    metodo="POST",
                    path={"id": "REQ#000001"},
                    body={"nombre_archivo": "x.pdf"},
                    grupos=("agente",),
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 200)

    def test_otro_solicitante_no_puede(self):
        with mock.patch.object(
            adjuntos.db,
            "obtener_solicitud",
            return_value=item_solicitud(solicitante="u-9"),
        ), mock.patch.object(
            adjuntos.storage, "generar_url_prefirmada"
        ) as firmar:
            respuesta = adjuntos.handler(
                evento(
                    metodo="POST",
                    path={"id": "REQ#000001"},
                    body={"nombre_archivo": "x.pdf"},
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 403)
        firmar.assert_not_called()

    def test_tipo_no_permitido(self):
        with mock.patch.object(
            adjuntos.db, "obtener_solicitud", return_value=item_solicitud()
        ), mock.patch.object(
            adjuntos.storage, "generar_url_prefirmada"
        ) as firmar:
            respuesta = adjuntos.handler(
                evento(
                    metodo="POST",
                    path={"id": "REQ#000001"},
                    body={
                        "nombre_archivo": "x.exe",
                        "content_type": "application/x-msdownload",
                    },
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 400)
        firmar.assert_not_called()

    def test_confirmar_ok(self):
        key = f"{PREFIJO}abc-vpn.pdf"
        actualizado = item_solicitud(adjuntos=[key])
        with mock.patch.object(
            adjuntos.db, "obtener_solicitud", return_value=item_solicitud()
        ), mock.patch.object(
            adjuntos.storage, "existe_objeto", return_value=True
        ), mock.patch.object(
            adjuntos.db, "agregar_adjunto", return_value=actualizado
        ) as agregar:
            respuesta = adjuntos.handler(
                evento(
                    metodo="PUT",
                    path={"id": "REQ#000001"},
                    body={"key": key},
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 200)
        self.assertEqual(cuerpo(respuesta)["adjuntos"], [key])
        agregar.assert_called_once_with("empresa-alfa", "REQ#000001", key)

    def test_confirmar_key_de_otro_tenant(self):
        with mock.patch.object(
            adjuntos.db, "obtener_solicitud", return_value=item_solicitud()
        ), mock.patch.object(
            adjuntos.storage, "existe_objeto"
        ) as existe:
            respuesta = adjuntos.handler(
                evento(
                    metodo="PUT",
                    path={"id": "REQ#000001"},
                    body={"key": "empresa-beta/solicitudes/REQ-000001/x.pdf"},
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 400)
        existe.assert_not_called()

    def test_confirmar_sin_objeto_en_s3(self):
        with mock.patch.object(
            adjuntos.db, "obtener_solicitud", return_value=item_solicitud()
        ), mock.patch.object(
            adjuntos.storage, "existe_objeto", return_value=False
        ), mock.patch.object(
            adjuntos.db, "agregar_adjunto"
        ) as agregar:
            respuesta = adjuntos.handler(
                evento(
                    metodo="PUT",
                    path={"id": "REQ#000001"},
                    body={"key": f"{PREFIJO}no-existe.pdf"},
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 400)
        self.assertEqual(cuerpo(respuesta)["error"]["code"], "ADJUNTO_NO_ENCONTRADO")
        agregar.assert_not_called()

    def test_metodo_no_permitido(self):
        respuesta = adjuntos.handler(
            evento(metodo="DELETE", path={"id": "REQ#000001"}), None
        )
        self.assertEqual(respuesta["statusCode"], 405)


if __name__ == "__main__":
    unittest.main()
