import unittest
from unittest import mock

from src.common.responses import ApiError
from src.handlers import crear
from tests.helpers import cuerpo, evento

SERVICIO = {
    "servicio_id": "SVC#000001",
    "nombre": "Acceso VPN",
    "sla_horas": 48,
    "requiere_aprobacion": True,
}


class CrearTest(unittest.TestCase):
    def _ejecutar(self, body=None, grupos=("solicitante",), servicio=None):
        body = body or {
            "servicio_id": "SVC#000001",
            "titulo": "Acceso VPN para analista",
            "descripcion": "Alta de acceso remoto",
            "prioridad": "alto",
        }
        with mock.patch.object(
            crear.catalog,
            "obtener_servicio",
            return_value=servicio or dict(SERVICIO),
        ) as obtener, mock.patch.object(
            crear.db, "nuevo_id_solicitud", return_value=870
        ) as contador, mock.patch.object(
            crear.db, "crear_solicitud"
        ) as guardar, mock.patch.object(
            crear.events, "publicar_evento", return_value=True
        ) as publicar:
            respuesta = crear.handler(
                evento(
                    metodo="POST",
                    body=body,
                    grupos=grupos,
                    authorization="Bearer id-token",
                ),
                None,
            )
        return respuesta, {
            "obtener": obtener,
            "contador": contador,
            "guardar": guardar,
            "publicar": publicar,
        }

    def test_crear_con_aprobacion(self):
        respuesta, mocks = self._ejecutar()

        self.assertEqual(respuesta["statusCode"], 201)
        datos = cuerpo(respuesta)
        self.assertEqual(datos["solicitud_id"], "REQ#000870")
        self.assertEqual(datos["estado"], "en_aprobacion")
        self.assertEqual(datos["tenant_id"], "empresa-alfa")
        self.assertEqual(datos["solicitante_id"], "u-1")
        self.assertEqual(datos["nombre_servicio"], "Acceso VPN")
        self.assertEqual(datos["sla_horas"], 48)
        self.assertEqual(datos["adjuntos"], [])
        self.assertFalse(datos["sla_vencido"])

        mocks["obtener"].assert_called_once_with(
            "SVC#000001", "Bearer id-token", "empresa-alfa"
        )
        mocks["contador"].assert_called_once_with("empresa-alfa")

        item, historial = mocks["guardar"].call_args[0]
        self.assertEqual(item["sk"], "REQ#000870")
        self.assertEqual(item["prioridad"], "alto")
        self.assertEqual(historial["estado_nuevo"], "en_aprobacion")
        self.assertEqual(historial["solicitud_id"], "REQ#000870")
        self.assertTrue(historial["sk"].startswith("HIST#REQ#000870#"))

        mocks["publicar"].assert_called_once()
        self.assertEqual(mocks["publicar"].call_args[0][0], "solicitud-creada")

    def test_guarda_el_id_canonico_del_catalogo(self):
        body = {"servicio_id": "svc-000001", "titulo": "Acceso VPN para analista"}
        respuesta, mocks = self._ejecutar(body=body)

        self.assertEqual(respuesta["statusCode"], 201)
        self.assertEqual(cuerpo(respuesta)["servicio_id"], "SVC#000001")
        item, _ = mocks["guardar"].call_args[0]
        self.assertEqual(item["servicio_id"], "SVC#000001")
        self.assertEqual(
            mocks["publicar"].call_args.kwargs["datos"]["servicio_id"], "SVC#000001"
        )

    def test_sin_aprobacion_empieza_nueva(self):
        servicio = dict(SERVICIO, requiere_aprobacion=False)
        respuesta, mocks = self._ejecutar(servicio=servicio)

        self.assertEqual(respuesta["statusCode"], 201)
        self.assertEqual(cuerpo(respuesta)["estado"], "nueva")
        self.assertFalse(
            cuerpo(respuesta)["requiere_aprobacion"]
        )

    def test_catalogo_caido_no_escribe(self):
        with mock.patch.object(
            crear.catalog,
            "obtener_servicio",
            side_effect=ApiError(503, "CATALOGO_NO_DISPONIBLE", "caido"),
        ), mock.patch.object(
            crear.db, "nuevo_id_solicitud"
        ) as contador, mock.patch.object(
            crear.db, "crear_solicitud"
        ) as guardar:
            respuesta = crear.handler(
                evento(
                    metodo="POST",
                    body={"servicio_id": "SVC#1", "titulo": "Acceso"},
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 503)
        self.assertEqual(cuerpo(respuesta)["error"]["code"], "CATALOGO_NO_DISPONIBLE")
        contador.assert_not_called()
        guardar.assert_not_called()

    def test_sin_rol_no_consulta_catalogo(self):
        with mock.patch.object(
            crear.catalog, "obtener_servicio"
        ) as obtener:
            respuesta = crear.handler(
                evento(
                    metodo="POST",
                    body={"servicio_id": "SVC#1", "titulo": "Acceso"},
                    grupos=("invitado",),
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 403)
        obtener.assert_not_called()

    def test_validacion_antes_del_catalogo(self):
        with mock.patch.object(
            crear.catalog, "obtener_servicio"
        ) as obtener:
            respuesta = crear.handler(
                evento(metodo="POST", body={"servicio_id": "SVC#1"}),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 400)
        obtener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
