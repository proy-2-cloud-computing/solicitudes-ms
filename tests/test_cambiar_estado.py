import unittest
from unittest import mock

from src.common.responses import ApiError
from src.handlers import cambiar_estado
from tests.helpers import cuerpo, evento, item_solicitud


class CambiarEstadoTest(unittest.TestCase):
    def _ejecutar(
        self,
        item,
        body,
        grupos=("agente",),
        actualizado=None,
        error_db=None,
    ):
        actualizado = actualizado or item_solicitud(estado=body.get("estado", "nueva"))
        with mock.patch.object(
            cambiar_estado.db,
            "obtener_solicitud",
            side_effect=[item, actualizado],
        ), mock.patch.object(
            cambiar_estado.db,
            "cambiar_estado",
            side_effect=error_db,
        ) as cambiar, mock.patch.object(
            cambiar_estado.events, "publicar_evento", return_value=True
        ) as publicar:
            respuesta = cambiar_estado.handler(
                evento(
                    metodo="PUT",
                    path={"id": "REQ#000001"},
                    body=body,
                    grupos=grupos,
                ),
                None,
            )
        return respuesta, {"cambiar": cambiar, "publicar": publicar}

    def test_agente_completa_y_publica_evento(self):
        item = item_solicitud(estado="en_proceso")
        actualizado = item_solicitud(estado="completada")
        respuesta, mocks = self._ejecutar(
            item, {"estado": "completada", "comentario": "Listo"}, actualizado=actualizado
        )

        self.assertEqual(respuesta["statusCode"], 200)
        self.assertEqual(cuerpo(respuesta)["estado"], "completada")
        mocks["cambiar"].assert_called_once()
        mocks["publicar"].assert_called_once()
        self.assertEqual(
            mocks["publicar"].call_args[0][0], "solicitud-completada"
        )

    def test_aprobador_aprueba(self):
        item = item_solicitud(estado="en_aprobacion")
        actualizado = item_solicitud(estado="en_proceso")
        respuesta, mocks = self._ejecutar(
            item,
            {"estado": "en_proceso"},
            grupos=("aprobador",),
            actualizado=actualizado,
        )

        self.assertEqual(respuesta["statusCode"], 200)
        mocks["publicar"].assert_not_called()

    def test_solicitante_no_cambia_estado(self):
        item = item_solicitud(estado="en_proceso")
        respuesta, mocks = self._ejecutar(
            item, {"estado": "completada"}, grupos=("solicitante",)
        )

        self.assertEqual(respuesta["statusCode"], 403)
        mocks["cambiar"].assert_not_called()

    def test_transicion_invalida(self):
        item = item_solicitud(estado="nueva")
        respuesta, mocks = self._ejecutar(item, {"estado": "completada"})

        self.assertEqual(respuesta["statusCode"], 409)
        self.assertEqual(cuerpo(respuesta)["error"]["code"], "TRANSICION_INVALIDA")
        mocks["cambiar"].assert_not_called()

    def test_conflicto_de_concurrencia(self):
        item = item_solicitud(estado="en_proceso")
        respuesta, _ = self._ejecutar(
            item,
            {"estado": "completada"},
            error_db=ApiError(409, "CONFLICTO", "cambio"),
        )

        self.assertEqual(respuesta["statusCode"], 409)
        self.assertEqual(cuerpo(respuesta)["error"]["code"], "CONFLICTO")

    def test_no_existe(self):
        with mock.patch.object(
            cambiar_estado.db, "obtener_solicitud", return_value=None
        ):
            respuesta = cambiar_estado.handler(
                evento(
                    metodo="PUT",
                    path={"id": "REQ#000001"},
                    body={"estado": "en_proceso"},
                    grupos=("agente",),
                ),
                None,
            )

        self.assertEqual(respuesta["statusCode"], 404)

    def test_asignado_a_se_pasa_a_db(self):
        item = item_solicitud(estado="nueva")
        actualizado = item_solicitud(estado="en_proceso", asignado_a="u-90")
        respuesta, mocks = self._ejecutar(
            item,
            {"estado": "en_proceso", "asignado_a": "u-90"},
            actualizado=actualizado,
        )

        self.assertEqual(respuesta["statusCode"], 200)
        datos = mocks["cambiar"].call_args[0][1]
        self.assertEqual(datos["asignado_a"], "u-90")


if __name__ == "__main__":
    unittest.main()
